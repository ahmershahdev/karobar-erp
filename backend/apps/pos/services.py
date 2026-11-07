"""The counter. A sale here is an invoice and a receipt for the walk-in customer, so stock, the
books, reports and returns all work exactly as they do for any other sale.
"""

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounting import services as accounting
from apps.accounting.models import TaxRate
from apps.accounts.models import User
from apps.core import posting
from apps.core.money import quantize_money, quantize_quantity
from apps.inventory import services as inventory
from apps.inventory.models import Product, ProductUnit, Unit, Warehouse
from apps.platform.locking import lock_rows, retry_on_deadlock
from apps.sales import services as sales
from apps.sales.models import Customer
from apps.tenancy import audit
from apps.tenancy.models import AuditEvent

from .models import PosSale, PosSession

ZERO = Decimal(0)
Action = AuditEvent.Action
WALK_IN = "WALK-IN"
SEARCH_LIMIT = 12


class PosError(Exception):
    message = "That isn't allowed at the counter."


class TillAlreadyOpenError(PosError):
    message = "A till is already open for this store."


class TillClosedError(PosError):
    message = "This till is closed. Open a new one to carry on selling."


class EmptyCartError(PosError):
    message = "Add something to the sale first."


class NoPriceError(PosError):
    message = "One of these products has no selling price yet."


class ProductInactiveError(PosError):
    message = "One of these products is no longer on sale. Take it off the sale."


class NotEnoughCashError(PosError):
    message = "The cash given is less than the total."


@dataclass(frozen=True)
class CartLine:
    product: Product
    unit: Unit
    quantity: Decimal
    discount_percent: Decimal | None = None


@dataclass(frozen=True)
class Found:
    product: Product
    unit: Unit
    price: Decimal | None
    exact: bool


def _price(product: Product, factor: Decimal) -> Decimal | None:
    if product.sale_price is None:
        return None
    return quantize_quantity(product.sale_price * factor)


def find_products(term: str) -> list[Found]:
    """A scanned barcode gives that one pack at its pack price; anything else searches."""
    pack = (
        ProductUnit.objects.select_related("product__unit", "unit")
        .filter(barcode=term, product__is_active=True)
        .first()
    )
    if pack is not None:
        return [Found(pack.product, pack.unit, _price(pack.product, pack.factor), exact=True)]
    matches = Product.objects.select_related("unit").filter(is_active=True, sku__iexact=term)[:1]
    if matches:
        return [Found(matches[0], matches[0].unit, _price(matches[0], Decimal(1)), exact=True)]
    query = Product.objects.select_related("unit").filter(is_active=True, name__icontains=term)
    return [
        Found(product, product.unit, _price(product, Decimal(1)), exact=False)
        for product in query[:SEARCH_LIMIT]
    ]


def _walk_in() -> Customer:
    customer: Customer = Customer.objects.get_or_create(
        code=WALK_IN, defaults={"name": "Walk-in customer"}
    )[0]
    return customer


@transaction.atomic
def open_till(actor: User, warehouse: Warehouse, opening_float: Decimal) -> PosSession:
    session = PosSession(
        warehouse=warehouse,
        opening_float=opening_float,
        open_key=str(warehouse.pk),
        opened_by=actor,
    )
    try:
        with transaction.atomic():
            session.save()
    except IntegrityError as exc:
        raise TillAlreadyOpenError from exc
    audit.record(Action.CREATE, session, actor, {"opening_float": [None, str(opening_float)]})
    return session


def _open_session(session: PosSession) -> PosSession:
    locked: PosSession = lock_rows(PosSession.objects.filter(pk=session.pk))[0]
    if locked.status != PosSession.Status.OPEN:
        raise TillClosedError
    return locked


def _invoice_line(line: CartLine, tax_rate: TaxRate | None) -> sales.InvoiceLineInput:
    # The price always comes from here, never from the request, so nobody can sell at a price
    # they typed into the browser.
    price = _price(line.product, inventory.factor_for(line.product, line.unit))
    if price is None:
        raise NoPriceError
    return sales.InvoiceLineInput(
        line.product,
        line.unit,
        line.quantity,
        price,
        tax_rate=tax_rate,
        discount_percent=line.discount_percent,
    )


def sell(
    actor: User,
    session: PosSession,
    lines: list[CartLine],
    method: str,
    tendered: Decimal | None = None,
    tax_rate: TaxRate | None = None,
    discount_percent: Decimal | None = None,
) -> PosSale:
    sale: PosSale = retry_on_deadlock(_sell)(
        actor, session, lines, method, tendered, tax_rate, discount_percent
    )
    return sale


@transaction.atomic
def _sell(
    actor: User,
    session: PosSession,
    lines: list[CartLine],
    method: str,
    tendered: Decimal | None,
    tax_rate: TaxRate | None,
    discount_percent: Decimal | None,
) -> PosSale:
    """Stock, the invoice, the money and the till record commit together or not at all.

    Prices come from the products; only discounts come from the request, and the role's limit
    is checked when the invoice is saved."""
    till = _open_session(session)
    # A product can be withdrawn or repriced while it sits in a cart, so its row is read and held
    # here, and the sale uses that copy. The lock keeps either change from landing mid-sale.
    chosen = lock_rows(Product.objects.filter(pk__in=[line.product.pk for line in lines]))
    if not all(product.is_active for product in chosen):
        raise ProductInactiveError
    current = {product.pk: product for product in chosen}
    lines = [replace(line, product=current[line.product.pk]) for line in lines]
    if not lines:
        raise EmptyCartError
    today = timezone.localdate()
    customer = _walk_in()
    invoice = sales.save_invoice(
        actor,
        {
            "customer": customer,
            "warehouse": till.warehouse,
            "date": today,
            "discount_percent": discount_percent,
        },
        [_invoice_line(line, tax_rate) for line in lines],
    )
    given = invoice.total if method == PosSale.Method.CARD or tendered is None else tendered
    if given < invoice.total:
        raise NotEnoughCashError
    posted = sales._post_invoice(actor, invoice)
    role = "cash" if method == PosSale.Method.CASH else "bank"
    receipt = sales.save_receipt(
        actor,
        {
            "customer": customer,
            "date": today,
            "amount": posted.total,
            "received_into": accounting.account_for_role(role),
            "memo": f"Counter sale {posted.number}",
        },
        [sales.AllocationInput(posted, posted.total)],
    )
    sale: PosSale = PosSale.objects.create(
        session=till,
        invoice=posted,
        receipt=sales._post_receipt(actor, receipt),
        method=method,
        amount=posted.total,
        tendered=given,
        change=quantize_money(given - posted.total),
    )
    audit.record(Action.POST, sale, actor, {"amount": [None, str(sale.amount)]})
    return sale


def takings(session: PosSession) -> dict[str, Any]:
    by_method = dict(session.sales.values_list("method").annotate(total=Sum("amount")))
    return {
        "sales_count": session.sales.count(),
        "cash_sales": quantize_money(by_method.get(PosSale.Method.CASH, ZERO)),
        "card_sales": quantize_money(by_method.get(PosSale.Method.CARD, ZERO)),
    }


@transaction.atomic
def close_till(actor: User, session: PosSession, counted: Decimal) -> PosSession:
    till = _open_session(session)
    till.expected_cash = quantize_money(till.opening_float + takings(till)["cash_sales"])
    till.counted_cash = quantize_money(counted)
    till.difference = till.counted_cash - till.expected_cash
    if till.difference:
        till.journal_entry = accounting.post_rule_lines(
            actor,
            timezone.localdate(),
            f"Till {till.pk} cash difference",
            posting.cash_difference(till.difference),
            {},
            ("pos_session", str(till.pk)),
        )
    till.status = PosSession.Status.CLOSED
    till.open_key = None
    till.closed_by = actor
    till.closed_at = timezone.now()
    till.save()
    audit.record(Action.POST, till, actor, {"difference": [None, str(till.difference)]})
    return till
