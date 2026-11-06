"""Every sales document is saved, posted and audited through here.

Posting locks the document, then the customer, then the rows it draws on (order lines for an
invoice, invoices for a receipt, invoice lines for a credit note) in primary-key order, then the
stock levels and number series further down. The customer lock is what makes the credit limit
hold: two invoices for one customer can't both pass the check on the same balance. Everything a
post writes, including its stock moves and journal entries, commits or rolls back together.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, cast

from django.db import models, transaction
from django.db.models import DecimalField, F, OuterRef, QuerySet, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.accounting import services as accounting
from apps.accounting.models import Account, TaxRate
from apps.accounts.models import User
from apps.core import posting
from apps.core.balances import AccountType
from apps.core.credit import over_limit
from apps.core.documents import line_amount, share
from apps.core.money import quantize_money, quantize_quantity
from apps.core.tax import is_valid_on, tax_on
from apps.inventory import services as inventory
from apps.inventory.models import Product, StockEntry, Unit, Warehouse
from apps.platform.locking import lock_rows, retry_on_deadlock
from apps.tenancy import audit
from apps.tenancy.models import AuditEvent

from .models import (
    CreditNote,
    CreditNoteLine,
    Customer,
    CustomerReceipt,
    Invoice,
    InvoiceLine,
    ReceiptAllocation,
    SalesOrder,
    SalesOrderLine,
)

ZERO = Decimal(0)
Action = AuditEvent.Action
QUOTE_SERIES = ("QUO", "QUO-")
ORDER_SERIES = ("SO", "SO-")
INVOICE_SERIES = ("INV", "INV-")
RECEIPT_SERIES = ("RCT", "RCT-")
CREDIT_SERIES = ("CN", "CN-")


class SalesError(Exception):
    """A sales rule was broken. Subclasses carry a fixed message the API can show."""

    message = "That isn't allowed for sales."


class NoLinesError(SalesError):
    message = "Add at least one line."


class NotDraftError(SalesError):
    message = "Only drafts can be changed, deleted or posted."


class OrderNotOpenError(SalesError):
    message = "This can only be done on a confirmed, open order."


class OrderClosedError(SalesError):
    message = "This order is already confirmed or closed."


class WrongCustomerError(SalesError):
    message = "Every line must belong to the same customer."


class OverInvoicedError(SalesError):
    message = "This invoices more than is still outstanding on the order."


class OverReturnedError(SalesError):
    message = "This returns more than was sold and not yet returned."


class InvoiceNotPostedError(SalesError):
    message = "Only posted invoices can take a receipt or a return."


class EmptyDocumentError(SalesError):
    message = "The document total must be more than zero."


class OverAllocatedError(SalesError):
    message = "Allocations can't exceed the receipt or what an invoice still owes."


class BadAccountError(SalesError):
    message = "Choose an active asset account that is not a group, such as cash or bank."


class LineMismatchError(SalesError):
    message = "An invoice line must match its order line's product and unit."


class TaxRateNotValidError(SalesError):
    message = "That tax rate doesn't apply on this document's date."


class CreditLimitError(SalesError):
    message = "This would take the customer over their credit limit."


@dataclass(frozen=True)
class OrderLineInput:
    product: Product
    unit: Unit
    quantity: Decimal
    unit_price: Decimal
    tax_amount: Decimal = ZERO
    tax_rate: TaxRate | None = None


@dataclass(frozen=True)
class InvoiceLineInput:
    product: Product
    unit: Unit
    quantity: Decimal
    unit_price: Decimal
    tax_amount: Decimal = ZERO
    order_line: SalesOrderLine | None = None
    batch_number: str = ""
    tax_rate: TaxRate | None = None


@dataclass(frozen=True)
class AllocationInput:
    invoice: Invoice
    amount: Decimal


@dataclass(frozen=True)
class CreditLineInput:
    invoice_line: InvoiceLine
    quantity: Decimal


def _line_tax(line: OrderLineInput | InvoiceLineInput, on: date) -> Decimal:
    """A chosen rate decides the tax. Without one, the amount typed stands."""
    rate = line.tax_rate
    if rate is None:
        return line.tax_amount
    if not is_valid_on(rate.valid_from, rate.valid_to, on):
        raise TaxRateNotValidError
    return tax_on(line_amount(line.quantity, line.unit_price), rate.rate)


# Customers reuse the audited master-data helpers of inventory.
save_customer = inventory.save_master
delete_customer = inventory.delete_master


def customers() -> QuerySet[Customer]:
    """Customers with `balance`: what they owe, less advances and unused credit.

    Below zero means we are holding their money.
    """
    money: DecimalField[Decimal, Decimal] = DecimalField()
    posted = Invoice.Status.POSTED

    def total(query: QuerySet[Any], by: str, value: Any) -> Any:
        rows = query.values(by).annotate(total=Sum(value)).values("total")
        return Coalesce(Subquery(rows), ZERO, output_field=money)

    owner = OuterRef("pk")
    owed = total(
        Invoice.objects.filter(customer=owner, status=posted),
        "customer",
        F("total") - F("amount_paid") - F("amount_credited"),
    )
    received = total(
        CustomerReceipt.objects.filter(customer=owner, status=posted), "customer", "amount"
    )
    allocated = total(
        ReceiptAllocation.objects.filter(receipt__customer=owner, receipt__status=posted),
        "receipt__customer",
        "amount",
    )
    credit = total(
        CreditNote.objects.filter(customer=owner, status=posted),
        "customer",
        F("total") - F("applied"),
    )
    query: QuerySet[Customer] = Customer.objects.annotate(
        balance=owed - received + allocated - credit
    )
    return query


def _check_credit(customer_id: int, amount: Decimal) -> None:
    """Call with the customer locked, or two sales could both pass on the same balance."""
    locked: Customer = lock_rows(Customer.objects.filter(pk=customer_id))[0]
    balance: Decimal = cast(Any, customers().get(pk=customer_id)).balance
    if over_limit(balance, amount, locked.credit_limit):
        raise CreditLimitError


def _locked_draft[D: models.Model](model: type[D], document: D) -> D:
    locked: D = lock_rows(model.objects.filter(pk=document.pk))[0]  # type: ignore[attr-defined]
    if getattr(locked, "status") != "draft":  # noqa: B009
        raise NotDraftError
    return locked


def _apply(target: models.Model, header: dict[str, Any], keys: Iterable[str]) -> None:
    for key in keys:
        if key in header:
            setattr(target, key, header[key])


def _mark_posted(document: Any, actor: User, status: str = "posted") -> None:
    document.status = status
    document.posted_by = actor
    document.posted_at = timezone.now()


@transaction.atomic
def delete_draft(actor: User, document: Any) -> None:
    draft = _locked_draft(type(document), document)
    audit.record(Action.DELETE, draft, actor, {"status": [draft.status, None]})
    draft.delete()


def _cash_account(account_id: int) -> Account:
    account: Account = Account.objects.get(pk=account_id)
    if account.type != AccountType.ASSET or account.is_group or not account.is_active:
        raise BadAccountError
    return account


# Quotations and orders


@transaction.atomic
def save_order(
    actor: User,
    header: dict[str, Any],
    lines: list[OrderLineInput],
    order: SalesOrder | None = None,
) -> SalesOrder:
    if not lines:
        raise NoLinesError
    action = Action.UPDATE if order else Action.CREATE
    target = _locked_draft(SalesOrder, order) if order else SalesOrder(created_by=actor)
    _apply(target, header, ("customer", "warehouse", "date", "valid_until", "memo"))
    taxes = [_line_tax(line, target.date) for line in lines]
    target.total = sum(
        (line_amount(line.quantity, line.unit_price) for line in lines), sum(taxes, ZERO)
    )
    target.save()
    target.lines.all().delete()
    SalesOrderLine.objects.bulk_create(
        SalesOrderLine(
            tenant_id=target.tenant_id,
            order=target,
            product=line.product,
            unit=line.unit,
            quantity=line.quantity,
            unit_price=line.unit_price,
            tax_rate=line.tax_rate,
            tax_amount=tax,
        )
        for line, tax in zip(lines, taxes, strict=True)
    )
    audit.record(action, target, actor, {"total": [None, str(target.total)]})
    return target


@transaction.atomic
def quote_order(actor: User, order: SalesOrder) -> SalesOrder:
    locked = _locked_draft(SalesOrder, order)
    if not locked.lines.exists():
        raise NoLinesError
    locked.quote_number = accounting.next_number(*QUOTE_SERIES)
    locked.status = SalesOrder.Status.QUOTED
    locked.save(update_fields=["quote_number", "status"])
    audit.record(Action.UPDATE, locked, actor, {"quote_number": [None, locked.quote_number]})
    return locked


@transaction.atomic
def confirm_order(actor: User, order: SalesOrder) -> SalesOrder:
    locked: SalesOrder = lock_rows(SalesOrder.objects.filter(pk=order.pk))[0]
    if locked.status not in (SalesOrder.Status.DRAFT, SalesOrder.Status.QUOTED):
        raise OrderClosedError
    if not locked.lines.exists():
        raise NoLinesError
    _check_credit(locked.customer_id, locked.total)
    locked.number = accounting.next_number(*ORDER_SERIES)
    _mark_posted(locked, actor, SalesOrder.Status.CONFIRMED)
    locked.save(update_fields=["number", "status", "posted_by", "posted_at"])
    audit.record(Action.POST, locked, actor, {"number": [None, locked.number]})
    return locked


@transaction.atomic
def close_order(actor: User, order: SalesOrder) -> SalesOrder:
    locked: SalesOrder = lock_rows(SalesOrder.objects.filter(pk=order.pk))[0]
    if locked.status not in (SalesOrder.Status.QUOTED, SalesOrder.Status.CONFIRMED):
        raise OrderNotOpenError
    before = locked.status
    locked.status = SalesOrder.Status.CLOSED
    locked.save(update_fields=["status"])
    audit.record(Action.UPDATE, locked, actor, {"status": [before, "closed"]})
    return locked


# Invoices


def _net(lines: list[InvoiceLineInput]) -> Decimal:
    return sum((line_amount(line.quantity, line.unit_price) for line in lines), ZERO)


@transaction.atomic
def save_invoice(
    actor: User,
    header: dict[str, Any],
    lines: list[InvoiceLineInput],
    invoice: Invoice | None = None,
) -> Invoice:
    if not lines:
        raise NoLinesError
    action = Action.UPDATE if invoice else Action.CREATE
    target = _locked_draft(Invoice, invoice) if invoice else Invoice(created_by=actor)
    _apply(target, header, ("customer", "order", "warehouse", "date", "due_date", "memo"))
    taxes = [quantize_money(_line_tax(line, target.date)) for line in lines]
    target.net, target.tax = _net(lines), sum(taxes, ZERO)
    target.total = target.net + target.tax
    target.save()
    target.lines.all().delete()
    InvoiceLine.objects.bulk_create(
        InvoiceLine(
            tenant_id=target.tenant_id,
            invoice=target,
            order_line=line.order_line,
            product=line.product,
            unit=line.unit,
            quantity=line.quantity,
            unit_price=line.unit_price,
            amount=line_amount(line.quantity, line.unit_price),
            tax_rate=line.tax_rate,
            tax_amount=tax,
            batch_number=line.batch_number,
        )
        for line, tax in zip(lines, taxes, strict=True)
    )
    audit.record(action, target, actor, {"total": [None, str(target.total)]})
    return target


@transaction.atomic
def invoice_order(actor: User, order: SalesOrder, on: date) -> Invoice:
    """Start a draft invoice for everything still outstanding on a confirmed order."""
    locked: SalesOrder = lock_rows(SalesOrder.objects.filter(pk=order.pk))[0]
    if locked.status != SalesOrder.Status.CONFIRMED:
        raise OrderNotOpenError
    lines = [
        InvoiceLineInput(
            line.product,
            line.unit,
            line.quantity - line.invoiced_quantity,
            line.unit_price,
            share(
                line.tax_amount,
                line.invoiced_quantity,
                line.quantity - line.invoiced_quantity,
                line.quantity,
            ),
            line,
            tax_rate=line.tax_rate,
        )
        for line in locked.lines.select_related("product", "unit", "tax_rate")
        if line.invoiced_quantity < line.quantity
    ]
    header = {
        "customer": locked.customer,
        "order": locked,
        "warehouse": locked.warehouse,
        "date": on,
    }
    return save_invoice(actor, header, lines)


def _invoice_against_order(invoice: Invoice, lines: list[InvoiceLine]) -> None:
    if invoice.order_id is None:
        if any(line.order_line_id is not None for line in lines):
            raise WrongCustomerError
        return
    order: SalesOrder = lock_rows(SalesOrder.objects.filter(pk=invoice.order_id))[0]
    if order.status != SalesOrder.Status.CONFIRMED or order.customer_id != invoice.customer_id:
        raise OrderNotOpenError
    ids = {line.order_line_id for line in lines if line.order_line_id is not None}
    by_id = {row.pk: row for row in lock_rows(SalesOrderLine.objects.filter(pk__in=ids))}
    for line in lines:
        target = by_id.get(line.order_line_id or 0)
        if target is None or target.order_id != order.pk:
            raise WrongCustomerError
        if target.product_id != line.product_id or target.unit_id != line.unit_id:
            raise LineMismatchError
        if target.invoiced_quantity + line.quantity > target.quantity:
            raise OverInvoicedError
        target.invoiced_quantity = quantize_quantity(target.invoiced_quantity + line.quantity)
        target.save(update_fields=["invoiced_quantity"])
    if not order.lines.filter(invoiced_quantity__lt=F("quantity")).exists():
        order.status = SalesOrder.Status.CLOSED
        order.save(update_fields=["status"])


def post_invoice(actor: User, invoice: Invoice) -> Invoice:
    posted: Invoice = retry_on_deadlock(_post_invoice)(actor, invoice)
    return posted


@transaction.atomic
def _post_invoice(actor: User, invoice: Invoice) -> Invoice:
    locked = _locked_draft(Invoice, invoice)
    lines = list(locked.lines.select_related("product", "unit"))
    if not lines:
        raise NoLinesError
    if locked.total <= 0:
        raise EmptyDocumentError
    _check_credit(locked.customer_id, locked.total)
    _invoice_against_order(locked, lines)
    customer = Customer.objects.get(pk=locked.customer_id)
    # The goods leave through the inventory engine, so locking, batches and valuation work exactly
    # as for any stock issue, and it books their cost straight to cost of goods sold.
    stock = inventory.save_draft(
        actor,
        {
            "kind": StockEntry.Kind.ISSUE,
            "date": locked.date,
            "memo": locked.memo or f"Sold to {customer.name}",
            "warehouse": locked.warehouse,
            "contra_account": accounting.account_for_role("cogs"),
        },
        [
            inventory.LineInput(
                line.product, line.unit, line.quantity, None, line.batch_number, None
            )
            for line in lines
        ],
    )
    stock = inventory.post_entry(actor, stock)
    # An issue writes exactly one stock move per line, in line order.
    for line, move in zip(lines, stock.moves.order_by("id"), strict=True):
        line.cost = -move.value
        line.save(update_fields=["cost"])
    locked.cost = sum((line.cost for line in lines), ZERO)
    locked.stock_entry = stock
    locked.number = accounting.next_number(*INVOICE_SERIES)
    if locked.due_date is None:
        locked.due_date = locked.date + timedelta(days=customer.payment_terms_days)
    locked.journal_entry = accounting.post_rule_lines(
        actor,
        locked.date,
        locked.memo or f"Invoice {locked.number} to {customer.name}",
        posting.sale(locked.net, locked.tax),
        {},
        ("invoice", str(locked.pk)),
    )
    _mark_posted(locked, actor)
    locked.save()
    audit.record(Action.POST, locked, actor, {"number": [None, locked.number]})
    return locked


# Receipts


@transaction.atomic
def save_receipt(
    actor: User,
    header: dict[str, Any],
    allocations: list[AllocationInput],
    receipt: CustomerReceipt | None = None,
) -> CustomerReceipt:
    action = Action.UPDATE if receipt else Action.CREATE
    target = (
        _locked_draft(CustomerReceipt, receipt) if receipt else CustomerReceipt(created_by=actor)
    )
    _apply(target, header, ("customer", "date", "amount", "received_into", "reference", "memo"))
    target.save()
    target.allocations.all().delete()
    ReceiptAllocation.objects.bulk_create(
        ReceiptAllocation(
            tenant_id=target.tenant_id,
            receipt=target,
            invoice=allocation.invoice,
            amount=allocation.amount,
        )
        for allocation in allocations
    )
    audit.record(action, target, actor, {"amount": [None, str(target.amount)]})
    return target


def post_receipt(actor: User, receipt: CustomerReceipt) -> CustomerReceipt:
    posted: CustomerReceipt = retry_on_deadlock(_post_receipt)(actor, receipt)
    return posted


@transaction.atomic
def _post_receipt(actor: User, receipt: CustomerReceipt) -> CustomerReceipt:
    locked = _locked_draft(CustomerReceipt, receipt)
    if locked.amount <= 0:
        raise EmptyDocumentError
    account = _cash_account(locked.received_into_id)
    allocations = list(locked.allocations.all())
    if sum((row.amount for row in allocations), ZERO) > locked.amount:
        raise OverAllocatedError
    taking: dict[int, Decimal] = {}
    for row in allocations:
        taking[row.invoice_id] = taking.get(row.invoice_id, ZERO) + row.amount
    for invoice in lock_rows(Invoice.objects.filter(pk__in=taking)):
        if invoice.status != Invoice.Status.POSTED:
            raise InvoiceNotPostedError
        if invoice.customer_id != locked.customer_id:
            raise WrongCustomerError
        if invoice.amount_paid + invoice.amount_credited + taking[invoice.pk] > invoice.total:
            raise OverAllocatedError
        invoice.amount_paid += taking[invoice.pk]
        invoice.save(update_fields=["amount_paid"])
    locked.number = accounting.next_number(*RECEIPT_SERIES)
    customer = Customer.objects.get(pk=locked.customer_id)
    # Whatever isn't allocated stays on the customer's account as an advance.
    locked.journal_entry = accounting.post_rule_lines(
        actor,
        locked.date,
        locked.memo or f"Receipt {locked.number} from {customer.name}",
        posting.receipt(locked.amount, into="received_into"),
        {"received_into": account},
        ("customer_receipt", str(locked.pk)),
    )
    _mark_posted(locked, actor)
    locked.save()
    audit.record(Action.POST, locked, actor, {"number": [None, locked.number]})
    return locked


# Credit notes


def _credit_slice(line: InvoiceLine, quantity: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    """This return's part of a line's amount, tax and cost, so partial returns add up exactly."""
    done, whole = line.returned_quantity, line.quantity
    return (
        share(line.amount, done, quantity, whole),
        share(line.tax_amount, done, quantity, whole),
        share(line.cost, done, quantity, whole),
    )


@transaction.atomic
def save_credit_note(
    actor: User,
    header: dict[str, Any],
    lines: list[CreditLineInput],
    note: CreditNote | None = None,
) -> CreditNote:
    if not lines:
        raise NoLinesError
    action = Action.UPDATE if note else Action.CREATE
    target = _locked_draft(CreditNote, note) if note else CreditNote(created_by=actor)
    _apply(target, header, ("invoice", "date", "memo"))
    invoice = Invoice.objects.get(pk=target.invoice_id)
    if invoice.status != Invoice.Status.POSTED:
        raise InvoiceNotPostedError
    target.customer_id = invoice.customer_id
    rows = []
    for line in lines:
        if line.invoice_line.invoice_id != invoice.pk:
            raise WrongCustomerError
        if line.invoice_line.returned_quantity + line.quantity > line.invoice_line.quantity:
            raise OverReturnedError
        amount, tax, _ = _credit_slice(line.invoice_line, line.quantity)
        rows.append((line, amount, tax))
    target.net = sum((amount for _, amount, _ in rows), ZERO)
    target.tax = sum((tax for _, _, tax in rows), ZERO)
    target.total = target.net + target.tax
    target.save()
    target.lines.all().delete()
    CreditNoteLine.objects.bulk_create(
        CreditNoteLine(
            tenant_id=target.tenant_id,
            note=target,
            invoice_line=line.invoice_line,
            quantity=line.quantity,
            amount=amount,
            tax_amount=tax,
        )
        for line, amount, tax in rows
    )
    audit.record(action, target, actor, {"total": [None, str(target.total)]})
    return target


@transaction.atomic
def credit_invoice(actor: User, invoice: Invoice, on: date) -> CreditNote:
    """Start a draft credit note for everything on the invoice not yet returned."""
    lines = [
        CreditLineInput(line, line.quantity - line.returned_quantity)
        for line in invoice.lines.all()
        if line.returned_quantity < line.quantity
    ]
    return save_credit_note(actor, {"invoice": invoice, "date": on}, lines)


def post_credit_note(actor: User, note: CreditNote) -> CreditNote:
    posted: CreditNote = retry_on_deadlock(_post_credit_note)(actor, note)
    return posted


@transaction.atomic
def _post_credit_note(actor: User, note: CreditNote) -> CreditNote:
    locked = _locked_draft(CreditNote, note)
    lines = list(locked.lines.all())
    if not lines:
        raise NoLinesError
    invoice: Invoice = lock_rows(Invoice.objects.filter(pk=locked.invoice_id))[0]
    sold = {
        row.pk: row
        for row in lock_rows(
            InvoiceLine.objects.filter(pk__in={line.invoice_line_id for line in lines})
        )
    }
    stock_lines = []
    for line in lines:
        target = sold[line.invoice_line_id]
        if target.returned_quantity + line.quantity > target.quantity:
            raise OverReturnedError
        # Recomputed under the lock: another return may have posted since this draft was saved.
        line.amount, line.tax_amount, cost = _credit_slice(target, line.quantity)
        target.returned_quantity = quantize_quantity(target.returned_quantity + line.quantity)
        target.save(update_fields=["returned_quantity"])
        product = Product.objects.get(pk=target.product_id)
        stock_lines.append(
            inventory.LineInput(
                product,
                Unit.objects.get(pk=target.unit_id),
                line.quantity,
                cost / line.quantity,
                target.batch_number,
                None,
            )
        )
    customer = Customer.objects.get(pk=locked.customer_id)
    warehouse = Warehouse.objects.get(pk=invoice.warehouse_id)
    # Goods come back at what they cost when sold, not today's cost, so the sale's profit is
    # undone exactly. The credit side reverses cost of goods sold.
    stock = inventory.post_entry(
        actor,
        inventory.save_draft(
            actor,
            {
                "kind": StockEntry.Kind.RECEIPT,
                "date": locked.date,
                "memo": locked.memo or f"Returned by {customer.name}",
                "warehouse": warehouse,
                "contra_account": accounting.account_for_role("cogs"),
            },
            stock_lines,
        ),
    )
    for line, move in zip(lines, stock.moves.order_by("id"), strict=True):
        line.cost = move.value
        line.save(update_fields=["amount", "tax_amount", "cost"])
    locked.net = sum((line.amount for line in lines), ZERO)
    locked.tax = sum((line.tax_amount for line in lines), ZERO)
    locked.total = locked.net + locked.tax
    outstanding = invoice.total - invoice.amount_paid - invoice.amount_credited
    locked.applied = min(locked.total, outstanding)
    invoice.amount_credited += locked.applied
    invoice.save(update_fields=["amount_credited"])
    locked.stock_entry = stock
    locked.number = accounting.next_number(*CREDIT_SERIES)
    locked.journal_entry = accounting.post_rule_lines(
        actor,
        locked.date,
        locked.memo or f"Credit note {locked.number} to {customer.name}",
        posting.credit_note(locked.net, locked.tax),
        {},
        ("credit_note", str(locked.pk)),
    )
    _mark_posted(locked, actor)
    locked.save()
    audit.record(Action.POST, locked, actor, {"number": [None, locked.number]})
    return locked
