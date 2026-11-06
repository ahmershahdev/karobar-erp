"""Every purchase document is saved, posted and audited through here.

Posting locks the document first, then the rows it draws on (order lines for a receipt, receipt
lines for a bill, bills for a payment) in primary-key order, then the stock levels and number
series further down. Everything a post writes, including its stock moves and journal entry,
commits or rolls back together.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db import models, transaction
from django.utils import timezone

from apps.accounting import services as accounting
from apps.accounting.models import Account
from apps.accounts.models import User
from apps.core import posting
from apps.core.balances import AccountType
from apps.core.documents import line_amount, share
from apps.core.money import quantize_money, quantize_quantity
from apps.inventory import services as inventory
from apps.inventory.models import Product, StockEntry, Unit
from apps.platform.locking import lock_rows, retry_on_deadlock
from apps.tenancy import audit
from apps.tenancy.models import AuditEvent

from .models import (
    Bill,
    BillLine,
    GoodsReceipt,
    GoodsReceiptLine,
    PaymentAllocation,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierPayment,
)

ZERO = Decimal(0)
Action = AuditEvent.Action
ORDER_SERIES = ("PO", "PO-")
BILL_SERIES = ("BILL", "BILL-")
PAYMENT_SERIES = ("PAY", "PAY-")


class PurchasingError(Exception):
    """A purchasing rule was broken. Subclasses carry a fixed message the API can show."""

    message = "That isn't allowed for purchases."


class NoLinesError(PurchasingError):
    message = "Add at least one line."


class NotDraftError(PurchasingError):
    message = "Only drafts can be changed, deleted or posted."


class OrderNotOpenError(PurchasingError):
    message = "Goods can only be received against a confirmed, open purchase order."


class WrongSupplierError(PurchasingError):
    message = "Every document line must belong to the same supplier."


class OverReceivedError(PurchasingError):
    message = "This receives more than is still outstanding on the order."


class OverBilledError(PurchasingError):
    message = "This bills more than was received and not yet billed."


class ReceiptNotPostedError(PurchasingError):
    message = "Only posted goods receipts can be billed."


class EmptyDocumentError(PurchasingError):
    message = "The document total must be more than zero."


class OverAllocatedError(PurchasingError):
    message = "Allocations can't exceed the payment or what a bill still owes."


class BadAccountError(PurchasingError):
    message = "Choose an active asset account that is not a group, such as cash or bank."


class BadExpenseAccountError(PurchasingError):
    message = "Expense lines need an active account that is not a group."


class LineMismatchError(PurchasingError):
    message = "A receipt line must match its order line's product and unit."


@dataclass(frozen=True)
class OrderLineInput:
    product: Product
    unit: Unit
    quantity: Decimal
    unit_price: Decimal


@dataclass(frozen=True)
class ReceiptLineInput:
    product: Product
    unit: Unit
    quantity: Decimal
    unit_cost: Decimal
    order_line: PurchaseOrderLine | None = None
    batch_number: str = ""
    expiry_date: date | None = None


@dataclass(frozen=True)
class BillLineInput:
    quantity: Decimal
    unit_price: Decimal
    receipt_line: GoodsReceiptLine | None = None
    account: Account | None = None
    description: str = ""
    tax_amount: Decimal = ZERO


@dataclass(frozen=True)
class AllocationInput:
    bill: Bill
    amount: Decimal


# Suppliers reuse the audited master-data helpers of inventory.
save_supplier = inventory.save_master
delete_supplier = inventory.delete_master


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


# Purchase orders


@transaction.atomic
def save_order(
    actor: User,
    header: dict[str, Any],
    lines: list[OrderLineInput],
    order: PurchaseOrder | None = None,
) -> PurchaseOrder:
    target = _locked_draft(PurchaseOrder, order) if order else PurchaseOrder(created_by=actor)
    _apply(target, header, ("supplier", "date", "expected_date", "warehouse", "memo"))
    target.total = sum((line_amount(ln.quantity, ln.unit_price) for ln in lines), ZERO)
    target.save()
    target.lines.all().delete()
    PurchaseOrderLine.objects.bulk_create(
        PurchaseOrderLine(
            tenant=target.tenant,
            order=target,
            product=line.product,
            unit=line.unit,
            quantity=quantize_quantity(line.quantity),
            unit_price=quantize_quantity(line.unit_price),
        )
        for line in lines
    )
    audit.record(
        Action.UPDATE if order else Action.CREATE,
        target,
        actor,
        {"total": [None, str(target.total)], "lines": [None, len(lines)]},
    )
    return target


@transaction.atomic
def confirm_order(actor: User, order: PurchaseOrder) -> PurchaseOrder:
    locked = _locked_draft(PurchaseOrder, order)
    if not locked.lines.exists():
        raise NoLinesError
    locked.number = accounting.next_number(*ORDER_SERIES)
    _mark_posted(locked, actor, PurchaseOrder.Status.CONFIRMED)
    locked.save(update_fields=["number", "status", "posted_by", "posted_at"])
    audit.record(Action.POST, locked, actor, {"number": [None, locked.number]})
    return locked


@transaction.atomic
def close_order(actor: User, order: PurchaseOrder) -> PurchaseOrder:
    locked: PurchaseOrder = lock_rows(PurchaseOrder.objects.filter(pk=order.pk))[0]
    if locked.status != PurchaseOrder.Status.CONFIRMED:
        raise OrderNotOpenError
    locked.status = PurchaseOrder.Status.CLOSED
    locked.save(update_fields=["status"])
    audit.record(Action.UPDATE, locked, actor, {"status": ["confirmed", "closed"]})
    return locked


@transaction.atomic
def receive_order(actor: User, order: PurchaseOrder, on: date) -> GoodsReceipt:
    """A draft goods receipt for everything still outstanding on a confirmed order."""
    if order.status != PurchaseOrder.Status.CONFIRMED:
        raise OrderNotOpenError
    lines = [
        ReceiptLineInput(
            line.product,
            line.unit,
            line.quantity - line.received_quantity,
            line.unit_price,
            order_line=line,
        )
        for line in order.lines.select_related("product", "unit")
        if line.received_quantity < line.quantity
    ]
    if not lines:
        raise OverReceivedError
    header = {
        "supplier": order.supplier,
        "purchase_order": order,
        "date": on,
        "warehouse": order.warehouse,
        "memo": "",
    }
    return save_receipt(actor, header, lines)


# Goods receipts


@transaction.atomic
def save_receipt(
    actor: User,
    header: dict[str, Any],
    lines: list[ReceiptLineInput],
    receipt: GoodsReceipt | None = None,
) -> GoodsReceipt:
    target = _locked_draft(GoodsReceipt, receipt) if receipt else GoodsReceipt(created_by=actor)
    _apply(target, header, ("supplier", "purchase_order", "date", "warehouse", "memo"))
    order = target.purchase_order
    if order is not None:
        if order.status != PurchaseOrder.Status.CONFIRMED:
            raise OrderNotOpenError
        if order.supplier_id != target.supplier_id:
            raise WrongSupplierError
    if any(
        line.order_line is not None and (order is None or line.order_line.order_id != order.pk)
        for line in lines
    ):
        raise WrongSupplierError
    target.save()
    target.lines.all().delete()
    GoodsReceiptLine.objects.bulk_create(
        GoodsReceiptLine(
            tenant=target.tenant,
            receipt=target,
            order_line=line.order_line,
            product=line.product,
            unit=line.unit,
            quantity=quantize_quantity(line.quantity),
            unit_cost=quantize_quantity(line.unit_cost),
            batch_number=line.batch_number.strip(),
            expiry_date=line.expiry_date,
        )
        for line in lines
    )
    audit.record(
        Action.UPDATE if receipt else Action.CREATE, target, actor, {"lines": [None, len(lines)]}
    )
    return target


def _receive_against_order(receipt: GoodsReceipt, lines: list[GoodsReceiptLine]) -> None:
    order: PurchaseOrder = lock_rows(PurchaseOrder.objects.filter(pk=receipt.purchase_order_id))[0]
    if order.status != PurchaseOrder.Status.CONFIRMED:
        raise OrderNotOpenError
    if order.supplier_id != receipt.supplier_id:
        raise WrongSupplierError
    order_lines = {
        line.pk: line for line in lock_rows(PurchaseOrderLine.objects.filter(order=order))
    }
    taking: dict[int, Decimal] = defaultdict(Decimal)
    for line in lines:
        if line.order_line_id is None:
            continue
        source = order_lines.get(line.order_line_id)
        if source is None:
            raise WrongSupplierError
        if (source.product_id, source.unit_id) != (line.product_id, line.unit_id):
            raise LineMismatchError
        taking[source.pk] += line.quantity
    for pk, quantity in taking.items():
        source = order_lines[pk]
        if source.received_quantity + quantity > source.quantity:
            raise OverReceivedError
        source.received_quantity = quantize_quantity(source.received_quantity + quantity)
        source.save(update_fields=["received_quantity"])
    if all(line.received_quantity >= line.quantity for line in order_lines.values()):
        order.status = PurchaseOrder.Status.CLOSED
        order.save(update_fields=["status"])


def post_receipt(actor: User, receipt: GoodsReceipt) -> GoodsReceipt:
    posted: GoodsReceipt = retry_on_deadlock(_post_receipt)(actor, receipt)
    return posted


@transaction.atomic
def _post_receipt(actor: User, receipt: GoodsReceipt) -> GoodsReceipt:
    locked = _locked_draft(GoodsReceipt, receipt)
    lines = list(locked.lines.select_related("product", "unit"))
    if not lines:
        raise NoLinesError
    if locked.purchase_order_id is not None:
        _receive_against_order(locked, lines)
    elif any(line.order_line_id is not None for line in lines):
        raise WrongSupplierError
    supplier = Supplier.objects.get(pk=locked.supplier_id)
    # The goods move through the inventory engine, so locking, batches and valuation work
    # exactly as for any stock receipt. The credit side is GRNI until the supplier's bill.
    stock = inventory.save_draft(
        actor,
        {
            "kind": StockEntry.Kind.RECEIPT,
            "date": locked.date,
            "memo": locked.memo or f"Goods from {supplier.name}",
            "warehouse": locked.warehouse,
            "contra_account": accounting.account_for_role("grni"),
        },
        [
            inventory.LineInput(
                line.product,
                line.unit,
                line.quantity,
                line.unit_cost,
                line.batch_number,
                line.expiry_date,
            )
            for line in lines
        ],
    )
    stock = inventory.post_entry(actor, stock)
    # A receipt writes exactly one stock move per line, in line order.
    moves = list(stock.moves.order_by("id"))
    for line, move in zip(lines, moves, strict=True):
        line.value = move.value
        line.save(update_fields=["value"])
    locked.stock_entry = stock
    locked.number = stock.number
    _mark_posted(locked, actor)
    locked.save()
    audit.record(Action.POST, locked, actor, {"number": [None, locked.number]})
    return locked


# Bills


def _bill_totals(lines: list[BillLineInput]) -> tuple[Decimal, Decimal]:
    net = sum((line_amount(line.quantity, line.unit_price) for line in lines), ZERO)
    tax = sum((quantize_money(line.tax_amount) for line in lines), ZERO)
    return net, tax


@transaction.atomic
def save_bill(
    actor: User,
    header: dict[str, Any],
    lines: list[BillLineInput],
    bill: Bill | None = None,
) -> Bill:
    target = _locked_draft(Bill, bill) if bill else Bill(created_by=actor)
    _apply(target, header, ("supplier", "supplier_reference", "date", "due_date", "memo"))
    for line in lines:
        source = line.receipt_line
        if source is None:
            if line.account is None:
                raise BadExpenseAccountError
            continue
        receipt = GoodsReceipt.objects.get(pk=source.receipt_id)
        if receipt.status != GoodsReceipt.Status.POSTED:
            raise ReceiptNotPostedError
        if receipt.supplier_id != target.supplier_id:
            raise WrongSupplierError
    if target.due_date is None:
        terms = Supplier.objects.get(pk=target.supplier_id).payment_terms_days
        target.due_date = target.date + timedelta(days=terms)
    target.net, target.tax = _bill_totals(lines)
    target.total = target.net + target.tax
    target.save()
    target.lines.all().delete()
    BillLine.objects.bulk_create(
        BillLine(
            tenant=target.tenant,
            bill=target,
            receipt_line=line.receipt_line,
            account=None if line.receipt_line else line.account,
            description=line.description,
            quantity=quantize_quantity(line.quantity),
            unit_price=quantize_quantity(line.unit_price),
            amount=line_amount(line.quantity, line.unit_price),
            tax_amount=quantize_money(line.tax_amount),
        )
        for line in lines
    )
    audit.record(
        Action.UPDATE if bill else Action.CREATE,
        target,
        actor,
        {"total": [None, str(target.total)], "lines": [None, len(lines)]},
    )
    return target


@transaction.atomic
def bill_receipt(actor: User, receipt: GoodsReceipt, on: date) -> Bill:
    """A draft bill for whatever of a posted receipt hasn't been billed yet."""
    if receipt.status != GoodsReceipt.Status.POSTED:
        raise ReceiptNotPostedError
    lines = [
        BillLineInput(
            line.quantity - line.billed_quantity,
            line.unit_cost,
            receipt_line=line,
            description=f"{line.product.sku} {line.product.name}",
        )
        for line in receipt.lines.select_related("product")
        if line.billed_quantity < line.quantity
    ]
    if not lines:
        raise OverBilledError
    header = {"supplier": receipt.supplier, "date": on, "memo": ""}
    return save_bill(actor, header, lines)


def _clear_receipt_lines(bill: Bill, lines: list[BillLine]) -> tuple[Decimal, Decimal]:
    """Take billed quantities off their receipt lines; returns (GRNI cleared, goods billed)."""
    ids = {line.receipt_line_id for line in lines if line.receipt_line_id is not None}
    sources = {
        line.pk: line
        for line in lock_rows(
            GoodsReceiptLine.objects.filter(pk__in=ids).select_related("receipt")
        )
    }
    received = billed = ZERO
    for line in lines:
        if line.receipt_line_id is None:
            continue
        source = sources[line.receipt_line_id]
        if source.receipt.status != GoodsReceipt.Status.POSTED:
            raise ReceiptNotPostedError
        if source.receipt.supplier_id != bill.supplier_id:
            raise WrongSupplierError
        if source.billed_quantity + line.quantity > source.quantity:
            raise OverBilledError
        received += share(source.value, source.billed_quantity, line.quantity, source.quantity)
        billed += line.amount
        source.billed_quantity = quantize_quantity(source.billed_quantity + line.quantity)
        source.save(update_fields=["billed_quantity"])
    return received, billed


def post_bill(actor: User, bill: Bill) -> Bill:
    posted: Bill = retry_on_deadlock(_post_bill)(actor, bill)
    return posted


@transaction.atomic
def _post_bill(actor: User, bill: Bill) -> Bill:
    locked = _locked_draft(Bill, bill)
    lines = list(locked.lines.select_related("account"))
    if not lines:
        raise NoLinesError
    if locked.total <= 0:
        raise EmptyDocumentError
    received, billed = _clear_receipt_lines(locked, lines)
    expenses: dict[str, Decimal] = defaultdict(Decimal)
    accounts: dict[str, Account] = {}
    for line in lines:
        if line.account is None:
            continue
        if line.account.is_group or not line.account.is_active:
            raise BadExpenseAccountError
        key = f"account:{line.account.pk}"
        expenses[key] += line.amount
        accounts[key] = line.account
    locked.number = accounting.next_number(*BILL_SERIES)
    supplier = Supplier.objects.get(pk=locked.supplier_id)
    locked.journal_entry = accounting.post_rule_lines(
        actor,
        locked.date,
        locked.memo or f"Bill {locked.number} from {supplier.name}",
        posting.supplier_bill(received, billed, sorted(expenses.items()), locked.tax),
        accounts,
        ("bill", str(locked.pk)),
    )
    _mark_posted(locked, actor)
    locked.save()
    audit.record(Action.POST, locked, actor, {"number": [None, locked.number]})
    return locked


# Payments


@transaction.atomic
def save_payment(
    actor: User,
    header: dict[str, Any],
    allocations: list[AllocationInput],
    payment: SupplierPayment | None = None,
) -> SupplierPayment:
    target = (
        _locked_draft(SupplierPayment, payment) if payment else SupplierPayment(created_by=actor)
    )
    _apply(target, header, ("supplier", "date", "amount", "paid_from", "reference", "memo"))
    target.amount = quantize_money(target.amount)
    for allocation in allocations:
        bill = allocation.bill
        if bill.status != Bill.Status.POSTED or bill.supplier_id != target.supplier_id:
            raise WrongSupplierError
    target.save()
    target.allocations.all().delete()
    PaymentAllocation.objects.bulk_create(
        PaymentAllocation(
            tenant=target.tenant,
            payment=target,
            bill=allocation.bill,
            amount=quantize_money(allocation.amount),
        )
        for allocation in allocations
    )
    audit.record(
        Action.UPDATE if payment else Action.CREATE,
        target,
        actor,
        {"amount": [None, str(target.amount)], "bills": [None, len(allocations)]},
    )
    return target


def post_payment(actor: User, payment: SupplierPayment) -> SupplierPayment:
    posted: SupplierPayment = retry_on_deadlock(_post_payment)(actor, payment)
    return posted


@transaction.atomic
def _post_payment(actor: User, payment: SupplierPayment) -> SupplierPayment:
    locked = _locked_draft(SupplierPayment, payment)
    if locked.amount <= 0:
        raise EmptyDocumentError
    source = Account.objects.get(pk=locked.paid_from_id)
    if source.type != AccountType.ASSET or source.is_group or not source.is_active:
        raise BadAccountError
    allocations = list(locked.allocations.all())
    if sum((a.amount for a in allocations), ZERO) > locked.amount:
        raise OverAllocatedError
    taking: dict[int, Decimal] = defaultdict(Decimal)
    for allocation in allocations:
        taking[allocation.bill_id] += allocation.amount
    for bill in lock_rows(Bill.objects.filter(pk__in=taking)):
        if bill.status != Bill.Status.POSTED or bill.supplier_id != locked.supplier_id:
            raise WrongSupplierError
        if bill.amount_paid + taking[bill.pk] > bill.total:
            raise OverAllocatedError
        bill.amount_paid += taking[bill.pk]
        bill.save(update_fields=["amount_paid"])
    locked.number = accounting.next_number(*PAYMENT_SERIES)
    supplier = Supplier.objects.get(pk=locked.supplier_id)
    # Whatever isn't allocated stays on the supplier's account as an advance.
    locked.journal_entry = accounting.post_rule_lines(
        actor,
        locked.date,
        locked.memo or f"Payment {locked.number} to {supplier.name}",
        posting.payment(locked.amount, out_of="paid_from"),
        {"paid_from": source},
        ("supplier_payment", str(locked.pk)),
    )
    _mark_posted(locked, actor)
    locked.save()
    audit.record(Action.POST, locked, actor, {"number": [None, locked.number]})
    return locked


def outstanding_bills(supplier: Supplier) -> models.QuerySet[Bill]:
    return Bill.objects.filter(
        supplier=supplier, status=Bill.Status.POSTED, amount_paid__lt=models.F("total")
    ).order_by("due_date", "id")
