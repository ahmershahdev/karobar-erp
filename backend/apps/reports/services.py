"""Reports read the books and documents; nothing here writes.

Money figures that must agree with the books come from the journal. Sales and margin come from
documents, because only an invoice knows which product was sold at what cost.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Q, Sum

from apps.accounting.models import Account, JournalEntry, JournalLine
from apps.accounting.reports import trial_balance
from apps.core.financials import (
    AccountBalance,
    BalanceSheet,
    ProfitAndLoss,
    balance_sheet,
    margin_percent,
    profit_and_loss,
)
from apps.core.money import quantize_money
from apps.inventory.models import StockLevel
from apps.purchasing.models import Bill
from apps.sales.models import CreditNote, CreditNoteLine, Invoice, InvoiceLine

ZERO = Decimal("0.00")
POSTED = "posted"
CASH_ROLES = ("cash", "bank")
TOP_PRODUCTS = 5
TREND_DAYS = 30


def _balances(end: date, start: date | None = None) -> list[AccountBalance]:
    roles = dict(Account.objects.values_list("code", "role"))
    return [
        AccountBalance(
            row.code, row.name, row.type, roles.get(row.code) or "", row.debit, row.credit
        )
        for row in trial_balance(end, start).rows
    ]


def profit_loss(start: date, end: date) -> ProfitAndLoss:
    return profit_and_loss(_balances(end, start))


def position(on: date) -> BalanceSheet:
    return balance_sheet(_balances(on))


def _role_net(role: str, start: date | None, end: date) -> Decimal:
    """Debits minus credits on the accounts playing `role`, in the window."""
    window = Q(entry__status=JournalEntry.Status.POSTED, entry__date__lte=end, account__role=role)
    if start is not None:
        window &= Q(entry__date__gte=start)
    totals = JournalLine.objects.filter(window).aggregate(
        debits=Sum("debit"), credits=Sum("credit")
    )
    return quantize_money((totals["debits"] or ZERO) - (totals["credits"] or ZERO))


@dataclass(frozen=True)
class CashFlow:
    opening: Decimal
    from_customers: Decimal
    to_suppliers: Decimal
    other: Decimal
    closing: Decimal


def cash_flow(start: date, end: date) -> CashFlow:
    """Where the money in cash and bank came from and went, by what moved it.

    Read straight from the cash and bank accounts, so it always ends on what they hold. A transfer
    from cash to bank is in and out of the same total, so it nets to nothing under `other`.
    """
    cash = Q(account__role__in=CASH_ROLES) | Q(account__parent__role__in=CASH_ROLES)
    posted = Q(entry__status=JournalEntry.Status.POSTED)

    def net(window: Q) -> Decimal:
        totals = JournalLine.objects.filter(cash & posted & window).aggregate(
            debits=Sum("debit"), credits=Sum("credit")
        )
        return quantize_money((totals["debits"] or ZERO) - (totals["credits"] or ZERO))

    period = Q(entry__date__gte=start, entry__date__lte=end)
    opening = net(Q(entry__date__lt=start))
    customers = net(period & Q(entry__source_type="customer_receipt"))
    suppliers = net(period & Q(entry__source_type="supplier_payment"))
    total = net(period)
    return CashFlow(opening, customers, suppliers, total - customers - suppliers, opening + total)


@dataclass(frozen=True)
class SalesTax:
    taxable_sales: Decimal
    output_tax: Decimal
    taxable_purchases: Decimal
    input_tax: Decimal
    payable: Decimal


def _total(query: Any, field: str) -> Decimal:
    return quantize_money(query.aggregate(total=Sum(field))["total"] or ZERO)


def sales_tax(start: date, end: date) -> SalesTax:
    """Tax collected against tax paid. Negative `payable` means it can be claimed back."""
    window = {"status": POSTED, "date__gte": start, "date__lte": end}
    sales = _total(Invoice.objects.filter(**window), "net") - _total(
        CreditNote.objects.filter(**window), "net"
    )
    output = -_role_net("tax_output", start, end)
    recoverable = _role_net("tax_input", start, end)
    return SalesTax(
        sales,
        output,
        _total(Bill.objects.filter(**window), "net"),
        recoverable,
        output - recoverable,
    )


def _net_by_day(first: date, last: date) -> dict[date, Decimal]:
    window = {"status": POSTED, "date__gte": first, "date__lte": last}
    days = dict(Invoice.objects.filter(**window).values_list("date").annotate(total=Sum("net")))
    returns = CreditNote.objects.filter(**window).values_list("date").annotate(total=Sum("net"))
    for day, amount in returns:
        days[day] = days.get(day, ZERO) - amount
    return days


def dashboard(on: date) -> dict[str, Any]:
    month = on.replace(day=1)
    window = {"status": POSTED, "date__gte": month, "date__lte": on}
    sold = Invoice.objects.filter(**window)
    returned = CreditNote.objects.filter(**window)
    sales = _total(sold, "net") - _total(returned, "net")
    returned_cost = _total(
        CreditNoteLine.objects.filter(
            note__status=POSTED, note__date__gte=month, note__date__lte=on
        ),
        "cost",
    )
    cost = _total(sold, "cost") - returned_cost

    # Every sales figure here is net of returns, so they all agree with each other.
    first_day = on - timedelta(days=TREND_DAYS - 1)
    by_day = _net_by_day(first_day, on)
    sold_lines = (
        InvoiceLine.objects.filter(
            invoice__status=POSTED, invoice__date__gte=month, invoice__date__lte=on
        )
        .values_list("product__name")
        .annotate(amount=Sum("amount"))
    )
    returned_lines = (
        CreditNoteLine.objects.filter(
            note__status=POSTED, note__date__gte=month, note__date__lte=on
        )
        .values_list("invoice_line__product__name")
        .annotate(amount=Sum("amount"))
    )
    products = dict(sold_lines)
    for name, amount in returned_lines:
        products[name] = products.get(name, ZERO) - amount
    top = sorted(
        ({"name": name, "amount": amount} for name, amount in products.items() if amount > 0),
        key=lambda row: row["amount"],
        reverse=True,
    )[:TOP_PRODUCTS]
    return {
        "sales_today": by_day.get(on, ZERO),
        "sales_month": sales,
        "gross_profit_month": sales - cost,
        "margin_percent": margin_percent(sales, cost),
        "stock_value": _total(StockLevel.objects.all(), "value"),
        "receivable": _role_net("receivables", None, on),
        "payable": -_role_net("payables", None, on),
        "sales_by_day": [
            {"date": day, "amount": by_day.get(day, ZERO)}
            for day in (first_day + timedelta(days=offset) for offset in range(TREND_DAYS))
        ],
        "top_products": top,
    }
