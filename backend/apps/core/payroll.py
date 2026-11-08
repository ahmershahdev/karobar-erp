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
    gross = sum((line.amount for line in lines if line.kind == EARNING), ZERO)
    deductions = sum((line.amount for line in lines if line.kind == DEDUCTION), ZERO)
    if deductions > gross:
        raise PayrollError("deductions can't be more than what is earned")
    taxable = sum((line.amount for line in lines if line.kind == EARNING and line.taxable), ZERO)
    return Breakdown(lines, gross, deductions, gross - deductions, taxable)
