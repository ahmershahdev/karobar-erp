"""Clearing what former employees' records no longer need to hold.

A bank account is only needed for the final pay, so it goes 90 days after someone leaves. The
national ID stays on tax records for six years after the end of the tax year they left in (the
business may choose longer), then it goes too. Names, payslips and journal entries stay, so the
books remain complete.
"""

from datetime import date, timedelta

from django.db import transaction

from apps.core.workdays import tax_year_end
from apps.tenancy import audit
from apps.tenancy.models import AuditEvent

from .models import Employee
from .time_off import settings_for

BANK_ACCOUNT_DAYS = 90


def _years_after(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 29 February in a year that has none.
        return day.replace(year=day.year + years, day=28)


@transaction.atomic
def clear_former_employees(today: date) -> int:
    """For the current business. Returns how many records were changed."""
    years = settings_for().id_retention_years
    changed = 0
    for person in Employee.objects.select_for_update().filter(left_on__isnull=False):
        left_on: date = person.left_on
        cleared = {}
        if person.bank_account and today > left_on + timedelta(days=BANK_ACCOUNT_DAYS):
            cleared["bank_account"] = ["kept", None]
            person.bank_account = ""
        if person.national_id and today > _years_after(tax_year_end(left_on), years):
            cleared["national_id"] = ["kept", None]
            person.national_id = ""
        if cleared:
            person.save(update_fields=list(cleared))
            # No user made this change; the audit row says what went, never the value itself.
            audit.record(AuditEvent.Action.UPDATE, person, None, cleared)
            changed += 1
    return changed
