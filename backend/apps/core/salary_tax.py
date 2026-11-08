"""Income tax on salary: a year's tax from slabs, and what to withhold each month.

Slabs are data per tax year with their source (in Pakistan, the First Schedule of the Income Tax
Ordinance as amended by each year's Finance Act), so they come in as arguments. A slab reads
"on income above `over`: `fixed` plus `rate` percent of the part above `over`", which is how the
law writes them.

Monthly withholding follows the annualised method of section 149: estimate the year's taxable
salary from what has been paid so far plus this month's pay for every month left, work out the
year's tax on that, take off what was already withheld, and spread the rest over the months
left. A raise or a bonus therefore changes the tax of the months after it, not only its own.
"""

import itertools
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .money import quantize_money

ZERO = Decimal(0)
HUNDRED = Decimal(100)
MONTHS = 12


class SalaryTaxError(ValueError):
    pass


@dataclass(frozen=True)
class Slab:
    over: Decimal
    fixed: Decimal
    rate: Decimal


@dataclass(frozen=True)
class Withholding:
    tax: Decimal
    # Shown on the payslip, so the person can check the figure.
    projected_income: Decimal
    year_tax: Decimal


def check_slabs(slabs: Sequence[Slab]) -> None:
    """Slabs start at zero, rise strictly, and never charge a negative or above-100% rate."""
    if not slabs:
        raise SalaryTaxError("a tax year needs at least one slab")
    if slabs[0].over != 0:
        raise SalaryTaxError("the first slab starts at zero")
    for slab in slabs:
        if slab.fixed < 0 or not ZERO <= slab.rate <= HUNDRED:
            raise SalaryTaxError(
                "a slab has a fixed amount of zero or more and a rate of 0 to 100"
            )
    if any(later.over <= earlier.over for earlier, later in itertools.pairwise(slabs)):
        raise SalaryTaxError("each slab starts above the one before")


def year_tax(income: Decimal, slabs: Sequence[Slab]) -> Decimal:
    """Tax on a year's taxable income. Income exactly at a slab's start stays in the slab below,
    as the law's "exceeds" wording means."""
    check_slabs(slabs)
    if income <= 0:
        return ZERO
    slab = [s for s in slabs if s.over < income][-1]
    return quantize_money(slab.fixed + (income - slab.over) * slab.rate / HUNDRED)


def months_left(month: date, first_month: int = 7) -> int:
    """Months from `month` to the end of its tax year, counting `month` itself. Pakistan's tax
    year starts in July, so July has 12 and June has 1."""
    if not 1 <= first_month <= MONTHS:
        raise SalaryTaxError("a month is 1 to 12")
    return MONTHS - (month.month - first_month) % MONTHS


def withholding(
    month_income: Decimal,
    earlier_income: Decimal,
    earlier_tax: Decimal,
    left: int,
    slabs: Sequence[Slab],
) -> Withholding:
    """This month's tax. `earlier_income` and `earlier_tax` are this tax year's taxable salary
    and tax withheld before this month; `left` counts this month (see months_left)."""
    if not 1 <= left <= MONTHS:
        raise SalaryTaxError("between 1 and 12 months are left in a tax year")
    if month_income < 0 or earlier_income < 0 or earlier_tax < 0:
        raise SalaryTaxError("income and tax can't be negative")
    projected = quantize_money(earlier_income + month_income * left)
    due = year_tax(projected, slabs)
    # A pay cut can leave more withheld than the year needs; payroll never refunds, the return
    # settles it.
    tax = max(ZERO, quantize_money((due - earlier_tax) / left))
    return Withholding(tax, projected, due)
