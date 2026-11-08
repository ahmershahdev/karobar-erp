"""Working days and tax years, for leave and payroll.

A business sets its own weekend (Sunday in Pakistan, Saturday and Sunday in the UAE since 2022)
and keeps its own list of public holidays, so both come in as arguments, never as constants.
"""

from collections.abc import Collection
from datetime import date, timedelta


class WorkdayError(ValueError):
    pass


def working_days(
    start: date, end: date, weekend: Collection[int], holidays: Collection[date]
) -> int:
    """Days from `start` to `end`, both included, that are neither weekend nor holiday.

    `weekend` holds weekday numbers as `date.weekday()` gives them: Monday is 0, Sunday is 6.
    """
    if end < start:
        raise WorkdayError("the end can't be before the start")
    if any(not 0 <= day <= 6 for day in weekend):
        raise WorkdayError("weekend days are 0 (Monday) to 6 (Sunday)")
    if len(set(weekend)) == 7:
        raise WorkdayError("a week needs at least one working day")
    days = 0
    current = start
    while current <= end:
        if current.weekday() not in weekend and current not in holidays:
            days += 1
        current += timedelta(days=1)
    return days


def tax_year_end(on: date, first_month: int = 7) -> date:
    """The last day of the tax year `on` falls in. Pakistan's runs July to June, so the
    default year ends on 30 June."""
    if not 1 <= first_month <= 12:
        raise WorkdayError("a month is 1 to 12")
    if first_month == 1:
        return date(on.year, 12, 31)
    # The year ends the day before the next first month starts.
    next_start_year = on.year + 1 if on.month >= first_month else on.year
    return date(next_start_year, first_month, 1) - timedelta(days=1)
