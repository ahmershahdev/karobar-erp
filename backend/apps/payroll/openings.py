"""Pay from earlier in a tax year, before payroll ran here.

A business that starts using payroll in November, or takes on someone who worked elsewhere since
July, would otherwise tax only the months Karobar sees. Section 149 has the employer count salary
and tax from earlier in the year when it is known (a previous employer's certificate, or the
business's own records), so these figures join the year's posted payslips in the tax maths.

They can be set only while the person has no posted payslip in that tax year: after that, posted
tax already depends on them.
"""

from datetime import date
from typing import Any

from django.db import transaction

from apps.accounts.models import User
from apps.hr.models import Employee
from apps.hr.time_off import settings_for
from apps.platform.locking import lock_rows
from apps.tenancy import audit
from apps.tenancy.models import AuditEvent

from .models import OpeningPay, PayrollRun, Payslip
from .services import TAX_YEAR_STARTS, PayrollError, lock_business, tax_year

Action = AuditEvent.Action


class NoSalaryTaxError(PayrollError):
    message = "This business's country has no tax on salaries, so earlier pay isn't needed."


class TaxAboveIncomeError(PayrollError):
    message = "The tax withheld can't be more than the taxable salary."


class AlreadyPaidHereError(PayrollError):
    message = (
        "This person already has posted pay in that tax year, so pay from before can't change now."
    )


def year_starting(month: date) -> date:
    first = TAX_YEAR_STARTS.get(settings_for().holiday_country)
    if first is None:
        raise NoSalaryTaxError
    return tax_year(month, first)[0]


def _check_unpaid_here(employee: Employee, starts: date) -> None:
    first = TAX_YEAR_STARTS[settings_for().holiday_country]
    _, ends = tax_year(starts, first)
    if Payslip.objects.filter(
        employee=employee,
        run__status=PayrollRun.Status.POSTED,
        run__month__range=(starts, ends),
    ).exists():
        raise AlreadyPaidHereError


@transaction.atomic
def save(actor: User, data: dict[str, Any]) -> OpeningPay:
    """Set one person's earlier pay for the tax year `data["month"]` falls in. Saving again for
    the same person and year replaces the figures."""
    lock_business()
    employee: Employee = data["employee"]
    starts = year_starting(data["month"])
    if data["tax"] > data["taxable"]:
        raise TaxAboveIncomeError
    _check_unpaid_here(employee, starts)
    rows = lock_rows(OpeningPay.objects.filter(employee=employee, year_starts=starts))
    opening = rows[0] if rows else OpeningPay(employee=employee, year_starts=starts)
    before = None if opening.pk is None else [str(opening.taxable), str(opening.tax)]
    opening.taxable, opening.tax = data["taxable"], data["tax"]
    opening.note = data.get("note", "")
    opening.save()
    audit.record(
        Action.CREATE if before is None else Action.UPDATE,
        opening,
        actor,
        {"taxable_and_tax": [before, [str(opening.taxable), str(opening.tax)]]},
    )
    return opening


@transaction.atomic
def delete(actor: User, opening: OpeningPay) -> None:
    lock_business()
    locked: OpeningPay = lock_rows(OpeningPay.objects.filter(pk=opening.pk))[0]
    _check_unpaid_here(locked.employee, locked.year_starts)
    audit.record(
        Action.DELETE,
        locked,
        actor,
        {"taxable_and_tax": [[str(locked.taxable), str(locked.tax)], None]},
    )
    locked.delete()
