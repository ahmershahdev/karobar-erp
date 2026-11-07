from decimal import Decimal

import pytest

from apps.core.payroll import Component, PayrollError, breakdown, value

D = Decimal


def test_a_structure_adds_up_to_gross_deductions_and_net() -> None:
    result = breakdown(
        D("50000"),
        [
            Component("House rent", "earning", percent=D("45")),
            Component("Medical", "earning", percent=D("10"), taxable=False),
            Component("Conveyance", "earning", amount=D("3000")),
            Component("Provident fund", "deduction", percent=D("8.33")),
            Component("Loan", "deduction", amount=D("2000.005")),
        ],
    )
    amounts = [(line.name, line.amount) for line in result.lines]
    assert amounts == [
        ("Basic", D("50000.00")),
        ("House rent", D("22500.00")),
        ("Medical", D("5000.00")),
        ("Conveyance", D("3000.00")),
        ("Provident fund", D("4165.00")),
        ("Loan", D("2000.01")),
    ]
    assert result.gross == D("80500.00")
    assert result.deductions == D("6165.01")
    assert result.net == D("74334.99")
    # Medical is not taxable, so it is left out of the taxable pay.
    assert result.taxable == D("75500.00")


def test_basic_alone_is_a_valid_structure() -> None:
    result = breakdown(D("30000"), [])
    assert (result.gross, result.deductions, result.net, result.taxable) == (
        D("30000.00"),
        D("0"),
        D("30000.00"),
        D("30000.00"),
    )


@pytest.mark.parametrize(
    "component",
    [
        Component("Both", "earning", amount=D(1), percent=D(1)),
        Component("Neither", "earning"),
        Component("Odd", "bonus", amount=D(1)),
        Component("Negative", "earning", amount=D(-1)),
        Component("Too much", "earning", percent=D(101)),
    ],
)
def test_strange_components_are_refused(component: Component) -> None:
    with pytest.raises((PayrollError, ValueError)):
        value(component, D("1000"))


def test_deductions_cannot_exceed_earnings() -> None:
    with pytest.raises(PayrollError):
        breakdown(D("1000"), [Component("Fine", "deduction", amount=D("1000.01"))])


def test_a_negative_basic_is_refused() -> None:
    with pytest.raises(PayrollError):
        breakdown(D("-1"), [])
