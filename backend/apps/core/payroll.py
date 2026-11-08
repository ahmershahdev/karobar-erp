"""Salary maths: what one month of a salary structure comes to.

A structure is a basic salary plus components. Each component is an earning (an allowance) or a
deduction, worth a fixed amount or a percentage of basic, and counted as taxable or not. Income
tax itself is not worked out here: the slabs are data per tax year and arrive with payroll runs.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from .documents import percent_of
from .money import quantize_money

ZERO = Decimal(0)
HUNDRED = Decimal(100)
EARNING, DEDUCTION = "earning", "deduction"


class PayrollError(ValueError):
    pass


@dataclass(frozen=True)
class Component:
    name: str
    kind: str
    amount: Decimal | None = None
    percent: Decimal | None = None
    taxable: bool = True


@dataclass(frozen=True)
class Line:
    name: str
    kind: str
    amount: Decimal
    taxable: bool


@dataclass(frozen=True)
class Breakdown:
    lines: list[Line]
    gross: Decimal
    deductions: Decimal
    net: Decimal
    # Basic plus the taxable earnings. Deductions don't lower it here; which ones the tax law
    # allows is a rule of the tax year, applied when payroll runs.
    taxable: Decimal


def value(component: Component, basic: Decimal) -> Decimal:
    """A component is either a fixed amount or a percentage of basic, never both."""
    if component.kind not in (EARNING, DEDUCTION):
        raise PayrollError("a component is an earning or a deduction")
    if (component.amount is None) == (component.percent is None):
        raise PayrollError("give a component a fixed amount or a percentage, not both")
    if component.amount is not None:
        if component.amount < 0:
            raise PayrollError("a component can't be negative")
        return quantize_money(component.amount)
    percent = component.percent or ZERO
    if not ZERO <= percent <= HUNDRED:
        raise PayrollError("a percentage of basic is between 0 and 100")
    return percent_of(basic, percent)


def breakdown(basic: Decimal, components: Sequence[Component]) -> Breakdown:
    if basic < 0:
        raise PayrollError("basic salary can't be negative")
    basic = quantize_money(basic)
    lines = [Line("Basic", EARNING, basic, True)]
    lines += [Line(c.name, c.kind, value(c, basic), c.taxable) for c in components]
    return _totals(lines)


def _totals(lines: list[Line]) -> Breakdown:
    gross = sum((line.amount for line in lines if line.kind == EARNING), ZERO)
    deductions = sum((line.amount for line in lines if line.kind == DEDUCTION), ZERO)
    if deductions > gross:
        raise PayrollError("deductions can't be more than what is earned")
    taxable = sum((line.amount for line in lines if line.kind == EARNING and line.taxable), ZERO)
    return Breakdown(lines, gross, deductions, gross - deductions, taxable)


def share(month: Breakdown, paid_days: Decimal, month_days: int) -> Breakdown:
    """The part of a full month's pay earned in `paid_days` of a `month_days`-day month.

    Pay is by calendar day, so 15 days of a 30-day month is half the month whether or not a
    weekend falls in it; someone who joins on the 16th gets the second half. Each line is
    rounded on its own, so the payslip lines add up to its totals.
    """
    if month_days <= 0 or not ZERO <= paid_days <= month_days:
        raise PayrollError("paid days are between zero and the days in the month")
    lines = [
        Line(
            line.name,
            line.kind,
            quantize_money(line.amount * paid_days / month_days),
            line.taxable,
        )
        for line in month.lines
    ]
    return _totals(lines)


def combine(parts: Sequence[Breakdown]) -> Breakdown:
    """One payslip from several pieces of a month, such as the days before and after a raise.
    Lines with the same name, kind and tax treatment are added together, in first-seen order."""
    merged: dict[tuple[str, str, bool], Decimal] = {}
    for part in parts:
        for line in part.lines:
            key = (line.name, line.kind, line.taxable)
            merged[key] = merged.get(key, ZERO) + line.amount
    lines = [Line(name, kind, amount, taxable) for (name, kind, taxable), amount in merged.items()]
    return _totals(lines)
