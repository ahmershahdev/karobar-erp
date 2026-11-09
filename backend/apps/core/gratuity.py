"""End-of-service gratuity: what someone is owed for their years of service when they leave.

The rules differ by country and come in as data with the law they are read from. In the UAE
(Federal Decree-Law 33 of 2021, Article 51) a foreign worker earns 21 days of basic wage for each
of the first five years and 30 days for each year after, once a year of service is complete,
never more than two years' wage in all. In Saudi Arabia (Labor Law, Articles 84 and 85) it is half
a month of the full wage for each of the first five years and a month for each year after, and
someone who resigns gets a third, two thirds or all of it by length of service.

Parts of a year count in proportion in both laws, so service is measured in days and turned into
years by dividing by 365.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from .money import quantize_money

ZERO = Decimal(0)
YEAR_DAYS = Decimal(365)


class GratuityError(ValueError):
    pass


@dataclass(frozen=True)
class Band:
    """On resignation, `share` of the full award once service reaches `years` (or passes it,
    when `after` is set: Saudi Article 85 gives two thirds only "in excess of five" years)."""

    years: Decimal
    share: Decimal
    after: bool = False

    def reached(self, service: Decimal) -> bool:
        return service > self.years if self.after else service >= self.years


@dataclass(frozen=True)
class Rule:
    first_years: Decimal
    first_days: Decimal
    later_days: Decimal
    # A month's wage is this many days' wage: the laws count the award in days or months.
    month_days: Decimal = Decimal(30)
    # Nothing is due before this much service.
    min_years: Decimal = ZERO
    # The award never exceeds this many months of the wage; None for no limit.
    cap_months: Decimal | None = None
    # Shares on resignation, lowest first. Empty means resigning changes nothing.
    resignation: tuple[Band, ...] = ()


@dataclass(frozen=True)
class Award:
    years: Decimal
    full: Decimal
    share: Decimal
    amount: Decimal


def check_rule(rule: Rule) -> None:
    numbers = (rule.first_years, rule.first_days, rule.later_days, rule.min_years)
    if any(n < 0 for n in numbers) or rule.month_days <= 0:
        raise GratuityError("gratuity rule figures can't be negative")
    if rule.cap_months is not None and rule.cap_months <= 0:
        raise GratuityError("a cap is more than zero months")
    previous: Band | None = None
    for band in rule.resignation:
        if band.years < 0 or not ZERO <= band.share <= 1:
            raise GratuityError("a resignation band has a share between 0 and 1")
        if previous is not None and (band.years < previous.years or band.share < previous.share):
            raise GratuityError("resignation bands rise with service")
        previous = band


def service_years(days: int) -> Decimal:
    if days < 0:
        raise GratuityError("service can't be negative")
    return Decimal(days) / YEAR_DAYS


def resignation_share(rule: Rule, years: Decimal) -> Decimal:
    share = ZERO
    for band in rule.resignation:
        if band.reached(years):
            share = band.share
    return share if rule.resignation else Decimal(1)


def award(rule: Rule, days: int, wage: Decimal, resigned: bool = False) -> Award:
    """The award for `days` of service at a monthly `wage`.

    Without `resigned` this is the full award, which is also what has built up so far: the
    amount the books keep as a provision while someone is still working.
    """
    check_rule(rule)
    if wage < 0:
        raise GratuityError("a wage can't be negative")
    years = service_years(days)
    if years < rule.min_years:
        return Award(years, ZERO, ZERO, ZERO)
    earned_days = min(years, rule.first_years) * rule.first_days
    earned_days += max(years - rule.first_years, ZERO) * rule.later_days
    full = wage * earned_days / rule.month_days
    if rule.cap_months is not None:
        full = min(full, wage * rule.cap_months)
    full = quantize_money(full)
    share = resignation_share(rule, years) if resigned else Decimal(1)
    return Award(years, full, share, quantize_money(full * share))


def bands(rows: Sequence[tuple[Decimal, Decimal, bool]]) -> tuple[Band, ...]:
    return tuple(Band(years, share, after) for years, share, after in rows)
