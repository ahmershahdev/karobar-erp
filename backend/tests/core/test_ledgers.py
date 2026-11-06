from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.core.ledgers import BUCKETS, Entry, age, bucket_for, build_statement

D = Decimal
ON = date(2026, 6, 30)


def entries() -> list[Entry]:
    return [
        Entry(date(2026, 3, 1), "RCT-1", "receipt", paid=D("40")),
        Entry(date(2026, 2, 1), "INV-1", "invoice", charged=D("100")),
        Entry(date(2026, 4, 1), "INV-2", "invoice", charged=D("50")),
        Entry(date(2026, 7, 1), "INV-3", "invoice", charged=D("999")),
    ]


def test_whole_history_runs_in_date_order_and_stops_at_the_end_date() -> None:
    statement = build_statement(entries(), None, ON)
    assert statement.opening == D(0)
    assert [(line.entry.number, line.balance) for line in statement.lines] == [
        ("INV-1", D("100.00")),
        ("RCT-1", D("60.00")),
        ("INV-2", D("110.00")),
    ]
    assert statement.closing == D("110.00")


def test_earlier_entries_become_the_opening_balance() -> None:
    statement = build_statement(entries(), date(2026, 3, 15), ON)
    assert statement.opening == D("60.00")
    assert [line.entry.number for line in statement.lines] == ["INV-2"]
    assert statement.closing == D("110.00")


def test_a_statement_with_nothing_in_it_is_all_zero() -> None:
    statement = build_statement([], None, ON)
    assert (statement.opening, statement.lines, statement.closing) == (D(0), [], D(0))


@pytest.mark.parametrize(
    ("days_late", "bucket"),
    [
        (-5, "current"),
        (0, "current"),
        (1, "days_1_30"),
        (30, "days_1_30"),
        (31, "days_31_60"),
        (60, "days_31_60"),
        (61, "days_61_90"),
        (90, "days_61_90"),
        (91, "over_90"),
    ],
)
def test_bucket_edges(days_late: int, bucket: str) -> None:
    assert bucket_for(ON - timedelta(days=days_late), ON) == bucket


def test_age_adds_up_and_always_has_every_column() -> None:
    totals = age([(ON, D("10")), (ON, D("5.50")), (ON - timedelta(days=45), D("7"))], ON)
    assert list(totals) == list(BUCKETS)
    assert totals["current"] == D("15.50")
    assert totals["days_31_60"] == D("7.00")
    assert totals["over_90"] == D(0)
