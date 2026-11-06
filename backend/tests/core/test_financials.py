from decimal import Decimal

from apps.core.financials import AccountBalance, balance_sheet, margin_percent, profit_and_loss

D = Decimal


def row(
    code: str, kind: str, debit: str = "0", credit: str = "0", role: str = ""
) -> AccountBalance:
    return AccountBalance(code, code, kind, role, D(debit), D(credit))


ROWS = [
    row("1110", "asset", debit="700", role="cash"),
    row("1140", "asset", debit="400", role="inventory"),
    row("2110", "liability", credit="100", role="payables"),
    row("3100", "equity", credit="600", role="capital"),
    row("4100", "income", credit="1000", role="sales"),
    row("4200", "income", debit="100", role="sales_returns"),
    row("5100", "expense", debit="500", role="cogs"),
    row("6100", "expense", debit="100", role="salaries"),
]


def test_profit_and_loss_separates_goods_from_running_costs() -> None:
    report = profit_and_loss(ROWS)
    assert report.income.total == D("900.00")
    assert report.cost_of_sales.total == D("500.00")
    assert report.gross_profit == D("400.00")
    assert report.expenses.total == D("100.00")
    assert report.net_profit == D("300.00")


def test_sales_returns_reduce_income_rather_than_counting_as_a_cost() -> None:
    lines = {line.code: line.amount for line in profit_and_loss(ROWS).income.lines}
    assert lines["4200"] == D("-100.00")


def test_a_balance_sheet_balances_once_profit_to_date_is_included() -> None:
    report = balance_sheet(ROWS)
    assert report.assets.total == D("1100.00")
    assert report.profit_to_date == D("300.00")
    assert report.total_liabilities_and_equity == D("1000.00")
    assert not report.balanced


def test_a_balance_sheet_that_truly_balances_says_so() -> None:
    fixed = [*ROWS[:2], row("2120", "liability", credit="100"), *ROWS[2:]]
    report = balance_sheet(fixed)
    assert report.total_liabilities_and_equity == report.assets.total
    assert report.balanced


def test_margin() -> None:
    assert margin_percent(D("1000"), D("600")) == D("40.00")
    assert margin_percent(D("3"), D("2")) == D("33.33")
    assert margin_percent(D(0), D("10")) is None
