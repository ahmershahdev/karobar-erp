"""Fiscal years and their monthly periods, as plain date arithmetic."""

from calendar import monthrange
from datetime import date, timedelta


class PeriodError(ValueError):
    pass


def _add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def fiscal_year_containing(day: date, start_month: int) -> tuple[date, date]:
    """The twelve-month fiscal year that contains `day`.

    Pakistan's fiscal year runs July to June (start_month=7); most Gulf businesses use the
    calendar year (start_month=1).
    """
    if not 1 <= start_month <= 12:
        raise PeriodError("start month must be between 1 and 12")
    start_year = day.year if day.month >= start_month else day.year - 1
    start = date(start_year, start_month, 1)
    return start, _add_months(start, 12) - timedelta(days=1)


def monthly_periods(start: date, end: date) -> list[tuple[date, date]]:
    """Split [start, end] into calendar-month periods. The first and last may be partial."""
    if end < start:
        raise PeriodError("a fiscal year cannot end before it starts")
    if _add_months(start, 24) <= end:
        raise PeriodError("a fiscal year can be at most 24 months long")
    periods: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        month_end = date(cursor.year, cursor.month, monthrange(cursor.year, cursor.month)[1])
        periods.append((cursor, min(month_end, end)))
        cursor = month_end + timedelta(days=1)
    return periods
