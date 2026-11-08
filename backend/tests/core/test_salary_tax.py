import itertools
from datetime import date
from decimal import Decimal

import pytest

from apps.core.salary_tax import (
    SalaryTaxError,
    Slab,
    check_slabs,
    months_left,
    withholding,
    year_tax,
)

D = Decimal

# Tax year 2027 (July 2026 to June 2027), First Schedule Part I Division I clause 2, as printed in
# FBR's withholding tax rate card updated to 30 June 2026 per the Finance Act 2026.
PK_2027 = [
    Slab(D(0), D(0), D(0)),
    Slab(D(600000), D(0), D(1)),
    Slab(D(1200000), D(6000), D(11)),
    Slab(D(2200000), D(116000), D(20)),
    Slab(D(3200000), D(316000), D(25)),
    Slab(D(4100000), D(541000), D(29)),
    Slab(D(5600000), D(976000), D(32)),
    Slab(D(7000000), D(1424000), D(35)),
]


@pytest.mark.parametrize(
    ("income", "tax"),
    [
        ("0", "0"),
        ("-5", "0"),
        ("600000", "0"),  # "Exceeds 600,000" starts above it.
        ("600001", "0.01"),
        ("1200000", "6000.00"),
        ("1800000", "72000.00"),
        ("2200000", "116000.00"),
        ("8000000", "1774000.00"),
    ],
)
def test_a_years_tax_follows_the_slabs(income: str, tax: str) -> None:
    assert year_tax(D(income), PK_2027) == D(tax)


def test_each_fixed_amount_is_the_tax_at_the_top_of_the_slab_below() -> None:
    for below, slab in itertools.pairwise(PK_2027):
        assert year_tax(slab.over, PK_2027) == slab.fixed, below


@pytest.mark.parametrize(
    "slabs",
    [
        [],
        [Slab(D(100), D(0), D(0))],
        [Slab(D(0), D(-1), D(0))],
        [Slab(D(0), D(0), D(101))],
        [Slab(D(0), D(0), D(-1))],
        [Slab(D(0), D(0), D(0)), Slab(D(0), D(0), D(5))],
        [Slab(D(0), D(0), D(0)), Slab(D(500), D(0), D(5)), Slab(D(400), D(0), D(5))],
    ],
)
def test_broken_slabs_are_refused(slabs: list[Slab]) -> None:
    with pytest.raises(SalaryTaxError):
        check_slabs(slabs)


@pytest.mark.parametrize(
    ("month", "first", "left"),
    [
        (date(2026, 7, 1), 7, 12),
        (date(2026, 12, 1), 7, 7),
        (date(2027, 1, 1), 7, 6),
        (date(2027, 6, 1), 7, 1),
        (date(2027, 1, 1), 1, 12),
        (date(2027, 12, 1), 1, 1),
    ],
)
def test_months_left_count_the_month_itself(month: date, first: int, left: int) -> None:
    assert months_left(month, first) == left


@pytest.mark.parametrize("first", [0, 13])
def test_a_tax_year_starts_in_a_real_month(first: int) -> None:
    with pytest.raises(SalaryTaxError):
        months_left(date(2027, 1, 1), first)


def test_a_steady_salary_pays_a_twelfth_each_month() -> None:
    july = withholding(D(150000), D(0), D(0), 12, PK_2027)
    assert july.projected_income == D(1800000)
    assert july.year_tax == D(72000)
    assert july.tax == D(6000)


def test_a_raise_spreads_the_extra_tax_over_the_months_left() -> None:
    # Six months at 100,000 (6,000 a year, so 500 a month), then 200,000 from January.
    january = withholding(D(200000), D(600000), D(3000), 6, PK_2027)
    assert january.projected_income == D(1800000)
    assert january.tax == D(11500)


def test_a_pay_cut_never_turns_into_a_refund() -> None:
    # 30,000 already withheld, but 900,000 plus six months at 10,000 owes only 3,600 a year.
    after = withholding(D(10000), D(900000), D(30000), 6, PK_2027)
    assert after.year_tax == D(3600)
    assert after.tax == D(0)


@pytest.mark.parametrize(
    ("income", "earlier", "tax", "left"),
    [
        ("100", "0", "0", 0),
        ("100", "0", "0", 13),
        ("-1", "0", "0", 12),
        ("100", "-1", "0", 12),
        ("100", "0", "-1", 12),
    ],
)
def test_impossible_withholding_inputs_are_refused(
    income: str, earlier: str, tax: str, left: int
) -> None:
    with pytest.raises(SalaryTaxError):
        withholding(D(income), D(earlier), D(tax), left, PK_2027)
