"""Customer and supplier statements, and how long money has been owed.

Both work the same way for receivables and payables. `charged` is anything that raises what is
owed, an invoice or a supplier's bill; `paid` is anything that lowers it, money or a return.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .money import quantize_money

ZERO = Decimal(0)
BUCKETS = ("current", "days_1_30", "days_31_60", "days_61_90", "over_90")


@dataclass(frozen=True)
class Entry:
    date: date
    number: str
    kind: str
    charged: Decimal = ZERO
    paid: Decimal = ZERO


@dataclass(frozen=True)
class StatementLine:
    entry: Entry
    balance: Decimal


@dataclass(frozen=True)
class Statement:
    opening: Decimal
    lines: list[StatementLine]
    closing: Decimal


def build_statement(entries: Sequence[Entry], start: date | None, end: date) -> Statement:
    """The entries from `start` to `end` with a running balance, after an opening balance.

    Entries before `start` become the opening balance, so the first line continues from what the
    customer already owed. No `start` means the whole history.
    """
    ordered = sorted(entries, key=lambda entry: (entry.date, entry.number))
    balance = ZERO
    lines: list[StatementLine] = []
    opening = ZERO
    for entry in ordered:
        if entry.date > end:
            break
        balance = quantize_money(balance + entry.charged - entry.paid)
        if start is not None and entry.date < start:
            opening = balance
        else:
            lines.append(StatementLine(entry, balance))
    return Statement(opening, lines, balance)


def bucket_for(due: date, on: date) -> str:
    """Which column an amount due on `due` falls in, looking from `on`."""
    days = (on - due).days
    if days <= 0:
        return "current"
    if days <= 30:
        return "days_1_30"
    if days <= 60:
        return "days_31_60"
    if days <= 90:
        return "days_61_90"
    return "over_90"


def age(items: Iterable[tuple[date, Decimal]], on: date) -> dict[str, Decimal]:
    """Add up (due date, amount) pairs into the ageing columns."""
    totals = dict.fromkeys(BUCKETS, ZERO)
    for due, amount in items:
        key = bucket_for(due, on)
        totals[key] = quantize_money(totals[key] + amount)
    return totals
