from decimal import Decimal

import pytest

from apps.core.contributions import ContributionError, Rate, Share, check_rate, contribution

D = Decimal


def test_on_minimum_wage_ignores_salary() -> None:
    rate = Rate(D(5), D(1), on_minimum_wage=True)
    assert contribution(rate, D(250000), D(40700)) == Share(
        D("40700.00"), D("2035.00"), D("407.00")
    )
    assert contribution(rate, D(10000), D(40700)) == Share(
        D("40700.00"), D("2035.00"), D("407.00")
    )


def test_on_pay_up_to_a_ceiling() -> None:
    rate = Rate(D(6), D(0), on_minimum_wage=False, cap=D(43000))
    assert contribution(rate, D(30000), None) == Share(D("30000.00"), D("1800.00"), D("0.00"))
    assert contribution(rate, D(90000), None) == Share(D("43000.00"), D("2580.00"), D("0.00"))


def test_on_pay_without_a_ceiling() -> None:
    rate = Rate(D("6.5"), D(0), on_minimum_wage=False)
    assert contribution(rate, D("12345.67"), None).employer == D("802.47")


def test_minimum_wage_is_needed() -> None:
    rate = Rate(D(5), D(1), on_minimum_wage=True)
    with pytest.raises(ContributionError):
        contribution(rate, D(1000), None)
    with pytest.raises(ContributionError):
        contribution(rate, D(1000), D(0))


def test_negative_pay_is_refused() -> None:
    with pytest.raises(ContributionError):
        contribution(Rate(D(6), D(0), on_minimum_wage=False), D(-1), None)


@pytest.mark.parametrize(
    "rate",
    [
        Rate(D(-1), D(0), on_minimum_wage=False),
        Rate(D(0), D(101), on_minimum_wage=False),
        Rate(D(6), D(0), on_minimum_wage=False, cap=D(0)),
        Rate(D(5), D(1), on_minimum_wage=True, cap=D(40000)),
    ],
)
def test_bad_rates(rate: Rate) -> None:
    with pytest.raises(ContributionError):
        check_rate(rate)
