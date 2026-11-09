"""Social insurance contributions on a month's pay: Pakistan's EOBI and provincial social security.

Both are a percentage of a base, split between the employer and the employee. The base is either
the minimum wage where the person works (EOBI collects this way, whatever the salary) or the
person's own pay, cut off at a ceiling (provincial social security). Rates, ceilings and minimum
wages change by notification and differ by province, so they arrive as data with their source and
are never written here.
"""

from dataclasses import dataclass
from decimal import Decimal

from .money import quantize_money

ZERO = Decimal(0)
HUNDRED = Decimal(100)


class ContributionError(ValueError):
    pass


@dataclass(frozen=True)
class Rate:
    employer: Decimal
    employee: Decimal
    # True: the base is the minimum wage. False: the base is the month's pay, up to `cap`.
    on_minimum_wage: bool
    cap: Decimal | None = None
    # The least the base can be, as GOSI counts at least a minimum contributory wage.
    floor: Decimal | None = None


@dataclass(frozen=True)
class Share:
    base: Decimal
    employer: Decimal
    employee: Decimal


def check_rate(rate: Rate) -> None:
    for percent in (rate.employer, rate.employee):
        if not ZERO <= percent <= HUNDRED:
            raise ContributionError("a contribution rate is between 0 and 100")
    if rate.cap is not None and rate.cap <= 0:
        raise ContributionError("a ceiling on pay is more than zero")
    if rate.floor is not None and rate.floor <= 0:
        raise ContributionError("a floor on pay is more than zero")
    if rate.floor is not None and rate.cap is not None and rate.floor > rate.cap:
        raise ContributionError("a floor can't be above the ceiling")
    if rate.on_minimum_wage and (rate.cap is not None or rate.floor is not None):
        raise ContributionError("a rate on the minimum wage has no ceiling or floor")


def contribution(rate: Rate, pay: Decimal, minimum_wage: Decimal | None) -> Share:
    """The month's contribution on `pay`, the person's gross pay for the month.

    On the minimum wage the base is the whole month's minimum wage even when the person worked
    part of it: the institution charges per insured person per month, not per day.
    """
    check_rate(rate)
    if pay < 0:
        raise ContributionError("pay can't be negative")
    if rate.on_minimum_wage:
        if minimum_wage is None or minimum_wage <= 0:
            raise ContributionError("a rate on the minimum wage needs the minimum wage")
        base = minimum_wage
    else:
        base = pay if rate.cap is None else min(pay, rate.cap)
        if rate.floor is not None:
            base = max(base, rate.floor)
    base = quantize_money(base)
    return Share(
        base,
        quantize_money(base * rate.employer / HUNDRED),
        quantize_money(base * rate.employee / HUNDRED),
    )
