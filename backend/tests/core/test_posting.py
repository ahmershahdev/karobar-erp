from datetime import date
from decimal import Decimal

import pytest

from apps.core import posting
from apps.core.balances import AccountType, balance, is_debit_normal, split
from apps.core.journal import Line, UnbalancedEntryError
from apps.core.periods import PeriodError, fiscal_year_containing, monthly_periods

D = Decimal


def as_tuples(lines: list[Line]) -> list[tuple[str, Decimal, Decimal]]:
    return [(line.account, line.debit, line.credit) for line in lines]


def test_sale_with_tax_and_cost() -> None:
    lines = posting.sale(D("15000"), D("2700"), D("9600"))
    assert as_tuples(lines) == [
        ("receivables", D("17700.00"), D("0.00")),
        ("sales", D("0.00"), D("15000.00")),
        ("tax_output", D("0.00"), D("2700.00")),
        ("cogs", D("9600.00"), D("0.00")),
        ("inventory", D("0.00"), D("9600.00")),
    ]


def test_zero_amounts_produce_no_lines() -> None:
    assert [line.account for line in posting.sale(D("100"))] == ["receivables", "sales"]
    assert [line.account for line in posting.purchase(D("100"))] == ["inventory", "payables"]


def test_purchase_receipt_and_payment() -> None:
    assert as_tuples(posting.purchase(D("1000"), D("180"))) == [
        ("inventory", D("1000.00"), D("0.00")),
        ("tax_input", D("180.00"), D("0.00")),
        ("payables", D("0.00"), D("1180.00")),
    ]
    assert as_tuples(posting.receipt(D("500"), into="bank")) == [
        ("bank", D("500.00"), D("0.00")),
        ("receivables", D("0.00"), D("500.00")),
    ]
    assert as_tuples(posting.payment(D("500"))) == [
        ("payables", D("500.00"), D("0.00")),
        ("cash", D("0.00"), D("500.00")),
    ]


@pytest.mark.parametrize(
    "call",
    [
        lambda: posting.sale(D("-1")),
        lambda: posting.purchase(D("1"), D("-1")),
        lambda: posting.receipt(D("-5")),
        lambda: posting.payment(D("-5")),
    ],
)
def test_negative_amounts_are_refused(call: object) -> None:
    with pytest.raises(ValueError, match="negative"):
        call()  # type: ignore[operator]


def test_a_zero_sale_is_not_an_entry() -> None:
    with pytest.raises(UnbalancedEntryError):
        posting.sale(D("0"))


def test_reversal_swaps_sides() -> None:
    original = posting.sale(D("100"), D("18"))
    undone = posting.reversal(original)
    assert as_tuples(undone)[0] == ("receivables", D("0.00"), D("118.00"))
    assert posting.reversal(undone) == original


@pytest.mark.parametrize(
    ("day", "start_month", "expected"),
    [
        (date(2026, 11, 2), 7, (date(2026, 7, 1), date(2027, 6, 30))),
        (date(2026, 3, 15), 7, (date(2025, 7, 1), date(2026, 6, 30))),
        (date(2026, 3, 15), 1, (date(2026, 1, 1), date(2026, 12, 31))),
    ],
)
def test_fiscal_year_containing(day: date, start_month: int, expected: tuple[date, date]) -> None:
    assert fiscal_year_containing(day, start_month) == expected


def test_fiscal_year_rejects_bad_month() -> None:
    with pytest.raises(PeriodError):
        fiscal_year_containing(date(2026, 1, 1), 13)


def test_monthly_periods_cover_the_year_exactly() -> None:
    periods = monthly_periods(date(2026, 7, 1), date(2027, 6, 30))
    assert len(periods) == 12
    assert periods[0] == (date(2026, 7, 1), date(2026, 7, 31))
    assert periods[7] == (date(2027, 2, 1), date(2027, 2, 28))
    assert periods[-1][1] == date(2027, 6, 30)


def test_monthly_periods_handle_partial_months_and_limits() -> None:
    assert monthly_periods(date(2026, 1, 15), date(2026, 2, 10)) == [
        (date(2026, 1, 15), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 10)),
    ]
    with pytest.raises(PeriodError, match="before"):
        monthly_periods(date(2026, 2, 1), date(2026, 1, 1))
    with pytest.raises(PeriodError, match="24 months"):
        monthly_periods(date(2026, 1, 1), date(2028, 1, 1))


def test_balances_follow_the_normal_side() -> None:
    assert is_debit_normal(AccountType.ASSET)
    assert not is_debit_normal(AccountType.INCOME)
    assert balance(AccountType.ASSET, D("100"), D("30")) == D("70.00")
    assert balance(AccountType.INCOME, D("10"), D("110")) == D("100.00")
    assert balance(AccountType.LIABILITY, D("50"), D("20")) == D("-30.00")


def test_split_places_balances_in_columns() -> None:
    assert split(AccountType.ASSET, D("70")) == (D("70.00"), D("0.00"))
    assert split(AccountType.INCOME, D("100")) == (D("0.00"), D("100.00"))
    assert split(AccountType.ASSET, D("-5")) == (D("0.00"), D("5.00"))
    assert split(AccountType.LIABILITY, D("-30")) == (D("30.00"), D("0.00"))


def test_a_discounted_sale_keeps_full_price_in_sales() -> None:
    lines = posting.sale(D("900"), D("162"), D("500"), D("100"))
    assert [(line.account, line.debit, line.credit) for line in lines] == [
        ("receivables", D("1062.00"), D("0.00")),
        ("sales_discounts", D("100.00"), D("0.00")),
        ("sales", D("0.00"), D("1000.00")),
        ("tax_output", D("0.00"), D("162.00")),
        ("cogs", D("500.00"), D("0.00")),
        ("inventory", D("0.00"), D("500.00")),
    ]


def test_a_negative_discount_is_refused() -> None:
    with pytest.raises(ValueError, match="discount"):
        posting.sale(D("100"), discount=D("-1"))


def test_a_payroll_owes_tax_deductions_and_net_pay() -> None:
    lines = posting.payroll(gross=D("100000"), deductions=D("8330"), tax=D("6000"))
    assert lines == [
        Line("salaries", D("100000.00"), D("0.00")),
        Line("withholding_payable", D("0.00"), D("6000.00")),
        Line("payroll_deductions", D("0.00"), D("8330.00")),
        Line("salaries_payable", D("0.00"), D("85670.00")),
    ]


def test_a_payroll_with_no_tax_has_no_tax_line() -> None:
    accounts = [line.account for line in posting.payroll(D("30000"), D("0"), D("0"))]
    assert accounts == ["salaries", "salaries_payable"]


def test_a_payroll_cannot_keep_back_more_than_it_pays() -> None:
    with pytest.raises(ValueError, match="more than the gross"):
        posting.payroll(D("1000"), D("600"), D("500"))
