from decimal import Decimal

import pytest

from apps.core import posting
from apps.core.documents import DocumentError, line_amount, percent_of, share, spread
from apps.core.journal import Line

D = Decimal


def test_line_amount_rounds_once_per_line() -> None:
    assert line_amount(D("3"), D("0.335")) == D("1.01")
    assert line_amount(D("0"), D("10")) == D("0.00")


@pytest.mark.parametrize(("quantity", "price"), [(D("-1"), D("1")), (D("1"), D("-1"))])
def test_line_amount_refuses_negatives(quantity: Decimal, price: Decimal) -> None:
    with pytest.raises(DocumentError):
        line_amount(quantity, price)


def test_shares_add_back_to_the_whole_value() -> None:
    parts = [share(D("10.00"), D(done), D(1), D(3)) for done in range(3)]
    assert parts == [D("3.33"), D("3.34"), D("3.33")]
    assert sum(parts) == D("10.00")
    assert share(D("10.00"), D(0), D(3), D(3)) == D("10.00")


@pytest.mark.parametrize(
    ("done", "part", "whole"),
    [(D(0), D(1), D(0)), (D(0), D(-1), D(3)), (D(-1), D(1), D(3)), (D(2), D(2), D(3))],
)
def test_share_refuses_parts_outside_the_whole(
    done: Decimal, part: Decimal, whole: Decimal
) -> None:
    with pytest.raises(DocumentError):
        share(D(10), done, part, whole)


def tuples(lines: list[Line]) -> list[tuple[str, Decimal, Decimal]]:
    return [(line.account, line.debit, line.credit) for line in lines]


def test_bill_clears_grni_and_books_tax() -> None:
    assert tuples(posting.supplier_bill(D("1000"), D("1000"), tax=D("180"))) == [
        ("grni", D("1000.00"), D("0.00")),
        ("tax_input", D("180.00"), D("0.00")),
        ("payables", D("0.00"), D("1180.00")),
    ]


def test_bill_above_and_below_the_order_price_posts_a_variance() -> None:
    dearer = tuples(posting.supplier_bill(D("1000"), D("1050")))
    assert ("purchase_variance", D("50.00"), D("0.00")) in dearer
    assert dearer[-1] == ("payables", D("0.00"), D("1050.00"))
    cheaper = tuples(posting.supplier_bill(D("1000"), D("990")))
    assert ("purchase_variance", D("0.00"), D("10.00")) in cheaper


def test_bill_with_expenses_only() -> None:
    lines = posting.supplier_bill(D(0), D(0), [("rent", D("500")), ("utilities", D("120"))])
    assert tuples(lines) == [
        ("rent", D("500.00"), D("0.00")),
        ("utilities", D("120.00"), D("0.00")),
        ("payables", D("0.00"), D("620.00")),
    ]


def test_bill_refuses_negative_amounts() -> None:
    with pytest.raises(ValueError, match="rent"):
        posting.supplier_bill(D(0), D(0), [("rent", D("-1"))])
    with pytest.raises(ValueError, match="tax"):
        posting.supplier_bill(D(0), D(0), tax=D("-1"))


def test_percent_of_rounds_once() -> None:
    assert percent_of(D("99.99"), D("12.5")) == D("12.50")
    assert percent_of(D("200"), D("0")) == D("0.00")
    assert percent_of(D("200"), D("100")) == D("200.00")


@pytest.mark.parametrize(
    ("amount", "percent"), [(D("-1"), D("10")), (D("10"), D("-1")), (D("10"), D("100.01"))]
)
def test_percent_of_refuses_strange_values(amount: Decimal, percent: Decimal) -> None:
    with pytest.raises(DocumentError):
        percent_of(amount, percent)


def test_a_bill_discount_is_spread_in_proportion_and_adds_back() -> None:
    assert spread(D("1.00"), [D("10"), D("10"), D("10")]) == [D("0.33"), D("0.34"), D("0.33")]
    assert spread(D("30"), [D("100"), D("200")]) == [D("10.00"), D("20.00")]
    parts = spread(D("17.77"), [D("3.33"), D("50"), D("0"), D("12.01")])
    assert sum(parts) == D("17.77")
    assert parts[2] == D("0.00")


def test_no_discount_spreads_zeros() -> None:
    assert spread(D("0"), [D("5"), D("0")]) == [D("0"), D("0")]


@pytest.mark.parametrize(
    ("amount", "weights"),
    [
        (D("-1"), [D("10")]),
        (D("1"), [D("-10"), D("20")]),
        (D("31"), [D("10"), D("20")]),
        (D("1"), []),
    ],
)
def test_spread_refuses_strange_values(amount: Decimal, weights: list[Decimal]) -> None:
    with pytest.raises(DocumentError):
        spread(amount, weights)
