from decimal import Decimal

from apps.core import posting
from apps.core.credit import over_limit
from apps.core.journal import Line

D = Decimal


def test_no_limit_means_any_amount() -> None:
    assert not over_limit(D("1000000"), D("1000000"), None)


def test_the_limit_itself_is_allowed() -> None:
    assert not over_limit(D("600"), D("400"), D("1000"))
    assert over_limit(D("600"), D("400.01"), D("1000"))


def test_a_zero_limit_is_cash_only() -> None:
    assert over_limit(D(0), D("0.01"), D(0))


def test_an_advance_adds_to_what_a_customer_may_buy() -> None:
    assert not over_limit(D("-500"), D("1400"), D("1000"))


def test_credit_note_reverses_a_sale_through_returns() -> None:
    assert posting.credit_note(D("100"), D("18")) == [
        Line("sales_returns", D("100.00"), D("0.00")),
        Line("tax_output", D("18.00"), D("0.00")),
        Line("receivables", D("0.00"), D("118.00")),
    ]


def test_credit_note_without_tax_has_no_tax_line() -> None:
    assert [line.account for line in posting.credit_note(D("100"))] == [
        "sales_returns",
        "receivables",
    ]


def test_cash_difference_books_short_and_over_the_right_way_round() -> None:
    assert posting.cash_difference(D("-10")) == [
        Line("cash_over_short", D("10.00"), D("0.00")),
        Line("cash", D("0.00"), D("10.00")),
    ]
    assert posting.cash_difference(D("5")) == [
        Line("cash", D("5.00"), D("0.00")),
        Line("cash_over_short", D("0.00"), D("5.00")),
    ]
