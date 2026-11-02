from decimal import Decimal

import pytest

from apps.core.money import MoneyError, quantize_money, quantize_quantity, to_decimal


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("10.005", "10.01"), ("10.004", "10.00"), ("-2.345", "-2.35"), (7, "7.00")],
)
def test_quantize_money_rounds_half_up(raw: str | int, expected: str) -> None:
    assert quantize_money(raw) == Decimal(expected)


def test_quantize_quantity_keeps_four_places() -> None:
    assert quantize_quantity("1.23456") == Decimal("1.2346")


def test_numbers_too_large_to_round_raise_money_error() -> None:
    with pytest.raises(MoneyError, match="too large"):
        quantize_money("1E+30")


@pytest.mark.parametrize("bad", [0.1, True, None, "abc", "NaN", "Infinity"])
def test_to_decimal_refuses_floats_and_garbage(bad: object) -> None:
    with pytest.raises(MoneyError):
        to_decimal(bad)  # type: ignore[arg-type]
