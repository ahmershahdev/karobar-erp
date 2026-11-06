"""Supplier statements and payables ageing."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from django.db.models import F, QuerySet

from apps.core.ledgers import Entry, Statement, age, build_statement

from .models import Bill, Supplier, SupplierPayment

ZERO = Decimal(0)


def ageing_rows(
    parties: QuerySet[Any], open_items: dict[int, list[tuple[date, Decimal]]], on: date
) -> list[dict[str, Any]]:
    """One row per party with something open: what is owed by age, and any money held for them.

    `parties` must carry a `balance`. Open documents minus that balance is what they have paid in
    advance, which no document can claim yet, so it shows in its own column.
    """
    rows = []
    for party in parties:
        items = open_items.get(party.pk, [])
        owed = sum((amount for _, amount in items), ZERO)
        if not owed and not party.balance:
            continue
        rows.append(
            {
                "id": party.pk,
                "name": party.name,
                **age(items, on),
                "advance": owed - party.balance,
                "total": party.balance,
            }
        )
    return rows


def statement(supplier: Supplier, start: date | None, end: date) -> Statement:
    bills = Bill.objects.filter(supplier=supplier, status=Bill.Status.POSTED)
    payments = SupplierPayment.objects.filter(
        supplier=supplier, status=SupplierPayment.Status.POSTED
    )
    return build_statement(
        [
            *(Entry(row.date, row.number or "", "bill", charged=row.total) for row in bills),
            *(Entry(row.date, row.number or "", "payment", paid=row.amount) for row in payments),
        ],
        start,
        end,
    )


def ageing(parties: QuerySet[Supplier], on: date) -> list[dict[str, Any]]:
    open_items: dict[int, list[tuple[date, Decimal]]] = defaultdict(list)
    bills = Bill.objects.filter(status=Bill.Status.POSTED, amount_paid__lt=F("total"))
    for bill in bills:
        open_items[bill.supplier_id].append(
            (bill.due_date or bill.date, bill.total - bill.amount_paid)
        )
    return ageing_rows(parties, open_items, on)
