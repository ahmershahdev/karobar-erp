"""The financial statements, built from account balances.

Each input row is one account's totals for the period, so these functions know nothing about the
database and can be checked by hand against a trial balance.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from .balances import AccountType, balance
from .money import quantize_money

ZERO = Decimal("0.00")
# Everything the goods themselves cost, so gross profit means what a shopkeeper expects.
COST_OF_SALES = frozenset({"cogs", "inventory_adjustments", "purchase_variance"})


@dataclass(frozen=True)
class AccountBalance:
    code: str
    name: str
    type: str
    role: str
    debit: Decimal
    credit: Decimal

    @property
    def amount(self) -> Decimal:
        """Positive on the account's normal side."""
        return balance(AccountType(self.type), self.debit, self.credit)


@dataclass(frozen=True)
class Line:
    code: str
    name: str
    amount: Decimal


@dataclass(frozen=True)
class Section:
    lines: list[Line]
    total: Decimal


@dataclass(frozen=True)
class ProfitAndLoss:
    income: Section
    cost_of_sales: Section
    gross_profit: Decimal
    expenses: Section
    net_profit: Decimal


@dataclass(frozen=True)
class BalanceSheet:
    assets: Section
    liabilities: Section
    equity: Section
    profit_to_date: Decimal
    total_liabilities_and_equity: Decimal
    balanced: bool


def _section(rows: Iterable[AccountBalance]) -> Section:
    lines = [Line(row.code, row.name, row.amount) for row in rows]
    return Section(lines, quantize_money(sum((line.amount for line in lines), ZERO)))


def profit_and_loss(rows: Iterable[AccountBalance]) -> ProfitAndLoss:
    accounts = list(rows)
    income = _section(row for row in accounts if row.type == AccountType.INCOME)
    costs = _section(
        row for row in accounts if row.type == AccountType.EXPENSE and row.role in COST_OF_SALES
    )
    expenses = _section(
        row
        for row in accounts
        if row.type == AccountType.EXPENSE and row.role not in COST_OF_SALES
    )
    gross = income.total - costs.total
    return ProfitAndLoss(income, costs, gross, expenses, gross - expenses.total)


def balance_sheet(rows: Iterable[AccountBalance]) -> BalanceSheet:
    """Assets against liabilities and equity, for balances from the very start of the books.

    Income and expenses aren't closed into equity by a year-end entry, so all profit to date is
    added here. That is what makes the two sides meet.
    """
    accounts = list(rows)
    assets = _section(row for row in accounts if row.type == AccountType.ASSET)
    liabilities = _section(row for row in accounts if row.type == AccountType.LIABILITY)
    equity = _section(row for row in accounts if row.type == AccountType.EQUITY)
    profit = profit_and_loss(accounts).net_profit
    total = liabilities.total + equity.total + profit
    return BalanceSheet(assets, liabilities, equity, profit, total, assets.total == total)


def margin_percent(sales: Decimal, cost: Decimal) -> Decimal | None:
    """Gross margin as a percentage of sales. None when there were no sales to measure against."""
    if sales <= 0:
        return None
    return quantize_money((sales - cost) * 100 / sales)
