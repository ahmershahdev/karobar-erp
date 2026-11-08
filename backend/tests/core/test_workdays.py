from datetime import date

import pytest

from apps.core.workdays import WorkdayError, tax_year_end, working_days

SUNDAY = {6}
GULF = {5, 6}


def test_a_week_without_holidays() -> None:
    # Monday 2 November 2026 to Sunday 8 November 2026.
    assert working_days(date(2026, 11, 2), date(2026, 11, 8), SUNDAY, set()) == 6
    assert working_days(date(2026, 11, 2), date(2026, 11, 8), GULF, set()) == 5


def test_holidays_are_left_out() -> None:
    iqbal_day = date(2026, 11, 9)
    assert working_days(date(2026, 11, 9), date(2026, 11, 11), SUNDAY, {iqbal_day}) == 2


def test_a_single_day() -> None:
    assert working_days(date(2026, 11, 8), date(2026, 11, 8), SUNDAY, set()) == 0
    assert working_days(date(2026, 11, 9), date(2026, 11, 9), SUNDAY, set()) == 1


@pytest.mark.parametrize(
    ("start", "end", "weekend"),
    [
        (date(2026, 11, 9), date(2026, 11, 8), SUNDAY),
        (date(2026, 11, 2), date(2026, 11, 8), {7}),
        (date(2026, 11, 2), date(2026, 11, 8), {0, 1, 2, 3, 4, 5, 6}),
    ],
)
def test_strange_ranges_are_refused(start: date, end: date, weekend: set[int]) -> None:
    with pytest.raises(WorkdayError):
        working_days(start, end, weekend, set())


def test_pakistans_tax_year_ends_on_30_june() -> None:
    assert tax_year_end(date(2026, 11, 7)) == date(2027, 6, 30)
    assert tax_year_end(date(2027, 6, 30)) == date(2027, 6, 30)
    assert tax_year_end(date(2027, 7, 1)) == date(2028, 6, 30)


def test_a_calendar_tax_year_ends_on_31_december() -> None:
    assert tax_year_end(date(2026, 3, 1), first_month=1) == date(2026, 12, 31)


def test_a_strange_first_month_is_refused() -> None:
    with pytest.raises(WorkdayError):
        tax_year_end(date(2026, 1, 1), first_month=13)
