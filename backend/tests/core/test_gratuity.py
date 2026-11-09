from decimal import Decimal

import pytest

from apps.core.gratuity import (
    Award,
    Band,
    GratuityError,
    Rule,
    award,
    bands,
    check_rule,
    resignation_share,
    service_years,
)

D = Decimal
THIRD = D(1) / D(3)
UAE = Rule(D(5), D(21), D(30), min_years=D(1), cap_months=D(24))
SAUDI = Rule(
    D(5),
    D(15),
    D(30),
    resignation=bands([(D(2), THIRD, False), (D(5), 2 * THIRD, True), (D(10), D(1), False)]),
)


def test_uae_needs_a_full_year() -> None:
    assert award(UAE, 364, D(10000)) == Award(D(364) / D(365), D(0), D(0), D(0))


def test_uae_three_years_is_21_days_a_year() -> None:
    # 3 years x 21 days = 63 days of a 10,000 basic, a day being a thirtieth of the month.
    result = award(UAE, 3 * 365, D(10000))
    assert (result.full, result.amount, result.share) == (D("21000.00"), D("21000.00"), D(1))


def test_uae_after_five_years_is_30_days_and_parts_count() -> None:
    # 5 x 21 + 3 x 30 = 195 days; 182 days more add 182/365 of 30 days.
    assert award(UAE, 8 * 365, D(9000)).full == D("58500.00")
    assert award(UAE, 8 * 365 + 365 // 2, D(9000)).full == D("62987.67")


def test_uae_never_exceeds_two_years_wage() -> None:
    assert award(UAE, 40 * 365, D(10000)).full == D("240000.00")


def test_uae_resigning_changes_nothing() -> None:
    assert award(UAE, 3 * 365, D(10000), resigned=True).amount == D("21000.00")


def test_saudi_full_award_has_no_cap() -> None:
    # 5 x half a month + 3 x a month = 5.5 months.
    assert award(SAUDI, 8 * 365, D(10000)).full == D("55000.00")
    assert award(SAUDI, 40 * 365, D(10000)).full == D("375000.00")


@pytest.mark.parametrize(
    ("years", "share"),
    [
        (D("1.99"), D(0)),
        (D(2), THIRD),
        (D(5), THIRD),
        (D("5.01"), 2 * THIRD),
        (D("9.99"), 2 * THIRD),
        (D(10), D(1)),
    ],
)
def test_saudi_resignation_shares(years: Decimal, share: Decimal) -> None:
    assert resignation_share(SAUDI, years) == share


def test_saudi_resigning_after_three_years_gets_a_third() -> None:
    result = award(SAUDI, 3 * 365, D(9000), resigned=True)
    assert (result.full, result.amount) == (D("13500.00"), D("4500.00"))


def test_service_is_counted_in_days() -> None:
    assert service_years(730) == D(2)
    with pytest.raises(GratuityError):
        service_years(-1)


@pytest.mark.parametrize(
    "rule",
    [
        Rule(D(-1), D(21), D(30)),
        Rule(D(5), D(21), D(30), month_days=D(0)),
        Rule(D(5), D(21), D(30), cap_months=D(0)),
        Rule(D(5), D(21), D(30), resignation=(Band(D(2), D("1.5")),)),
        Rule(D(5), D(21), D(30), resignation=(Band(D(5), D("0.5")), Band(D(2), D("0.7")))),
        Rule(D(5), D(21), D(30), resignation=(Band(D(2), D("0.5")), Band(D(5), D("0.2")))),
    ],
)
def test_strange_rules_are_refused(rule: Rule) -> None:
    with pytest.raises(GratuityError):
        check_rule(rule)


def test_a_negative_wage_is_refused() -> None:
    with pytest.raises(GratuityError):
        award(UAE, 400, D(-1))
