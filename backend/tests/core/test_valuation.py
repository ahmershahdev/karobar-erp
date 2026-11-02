from decimal import Decimal

import pytest

from apps.core import posting
from apps.core.valuation import (
    Consumption,
    Holding,
    InsufficientStockError,
    Layer,
    ValuationError,
    average_issue,
    average_receive,
    fifo_issue,
    to_base,
)

D = Decimal


def test_unit_conversion() -> None:
    assert to_base(D("2"), D("12")) == D("24.0000")
    assert to_base(D("1.5"), D("0.25")) == D("0.3750")
    with pytest.raises(ValuationError):
        to_base(D("1"), D("0"))


def test_moving_average_reaverages_on_receipt() -> None:
    holding = average_receive(Holding(D(0), D(0)), D("10"), D("100"))
    holding = average_receive(holding, D("10"), D("130"))
    assert holding == Holding(D("20.0000"), D("2300.00"))
    holding, cost = average_issue(holding, D("5"))
    assert cost == D("575.00")
    assert holding == Holding(D("15.0000"), D("1725.00"))


def test_issuing_everything_takes_all_the_value() -> None:
    holding = Holding(D("3"), D("100.00"))
    holding, first = average_issue(holding, D("1"))
    assert first == D("33.33")
    remaining, last = average_issue(holding, D("2"))
    assert remaining == Holding(D(0), D(0))
    assert first + last == D("100.00")


@pytest.mark.parametrize(
    "call",
    [
        lambda: average_receive(Holding(D(0), D(0)), D("0"), D("1")),
        lambda: average_receive(Holding(D(0), D(0)), D("1"), D("-1")),
        lambda: average_issue(Holding(D(1), D(1)), D("-1")),
    ],
)
def test_bad_quantities_and_costs(call: object) -> None:
    with pytest.raises(ValuationError):
        call()  # type: ignore[operator]


def test_cannot_issue_more_than_on_hand() -> None:
    with pytest.raises(InsufficientStockError):
        average_issue(Holding(D("2"), D("20")), D("3"))
    with pytest.raises(InsufficientStockError):
        fifo_issue([Layer(1, D("2"), D("10"))], D("3"))


def test_fifo_takes_oldest_layers_first() -> None:
    layers = [Layer(1, D("5"), D("10")), Layer(2, D("0"), D("99")), Layer(3, D("10"), D("12"))]
    taken, cost = fifo_issue(layers, D("8"))
    assert taken == [
        Consumption(1, D("5"), D("50.00")),
        Consumption(3, D("3.0000"), D("36.00")),
    ]
    assert cost == D("86.00")


def test_fifo_stops_once_satisfied() -> None:
    taken, cost = fifo_issue([Layer(1, D("5"), D("2")), Layer(2, D("5"), D("3"))], D("5"))
    assert taken == [Consumption(1, D("5"), D("10.00"))]
    assert cost == D("10.00")


def test_stock_posting_rules() -> None:
    assert [(ln.account, ln.debit, ln.credit) for ln in posting.stock_in(D("500"), "capital")] == [
        ("inventory", D("500.00"), D("0.00")),
        ("capital", D("0.00"), D("500.00")),
    ]
    assert [ln.account for ln in posting.stock_out(D("40"), "inventory_adjustments")] == [
        "inventory_adjustments",
        "inventory",
    ]
    with pytest.raises(ValueError, match="negative"):
        posting.stock_in(D("-1"), "capital")
    with pytest.raises(ValueError, match="negative"):
        posting.stock_out(D("-1"), "x")
