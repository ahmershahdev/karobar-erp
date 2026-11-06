from datetime import date
from decimal import Decimal

from apps.core.tax import is_valid_on, tax_on

D = Decimal


def test_tax_rounds_half_up_once_per_line() -> None:
    assert tax_on(D("1000"), D("18")) == D("180.00")
    assert tax_on(D("33.33"), D("18")) == D("6.00")
    assert tax_on(D("0.25"), D("10")) == D("0.03")
    assert tax_on(D("100"), D(0)) == D("0.00")


def test_a_rate_applies_on_both_of_its_end_dates() -> None:
    start, end = date(2026, 7, 1), date(2027, 6, 30)
    assert is_valid_on(start, end, start)
    assert is_valid_on(start, end, end)
    assert not is_valid_on(start, end, date(2026, 6, 30))
    assert not is_valid_on(start, end, date(2027, 7, 1))


def test_a_rate_with_no_end_date_keeps_applying() -> None:
    assert is_valid_on(date(2026, 7, 1), None, date(2040, 1, 1))
