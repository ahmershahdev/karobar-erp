"""Customer statements and receivables ageing."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from django.db.models import F

from apps.core.ledgers import Entry, Statement, build_statement
from apps.purchasing.reports import ageing_rows

from . import services
from .models import CreditNote, Customer, CustomerReceipt, Invoice


def statement(customer: Customer, start: date | None, end: date) -> Statement:
    posted = {"customer": customer, "status": "posted"}
    return build_statement(
        [
            *(
                Entry(row.date, row.number or "", "invoice", charged=row.total)
                for row in Invoice.objects.filter(**posted)
            ),
            *(
                Entry(row.date, row.number or "", "receipt", paid=row.amount)
                for row in CustomerReceipt.objects.filter(**posted)
            ),
            *(
                Entry(row.date, row.number or "", "return", paid=row.total)
                for row in CreditNote.objects.filter(**posted)
            ),
        ],
        start,
        end,
    )


def ageing(on: date) -> list[dict[str, Any]]:
    open_items: dict[int, list[tuple[date, Decimal]]] = defaultdict(list)
    invoices = Invoice.objects.filter(
        status=Invoice.Status.POSTED, total__gt=F("amount_paid") + F("amount_credited")
    )
    for invoice in invoices:
        open_items[invoice.customer_id].append(
            (
                invoice.due_date or invoice.date,
                invoice.total - invoice.amount_paid - invoice.amount_credited,
            )
        )
    return ageing_rows(services.customers(), open_items, on)
