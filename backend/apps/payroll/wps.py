"""The UAE salary file (WPS SIF) for a posted month, from its payslips (apps/core/wps.py).

Each person's line pays their net pay as the fixed component, over the days of the month they
were employed, with their unpaid days; the control line's total is the month's net pay, which
is what the bank sends out.
"""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from apps.core.wps import Employer, Line, WpsError, sif
from apps.hr.time_off import settings_for

from .models import PayrollRun, Payslip
from .runs import month_end
from .services import PayrollError


class NotUaeError(PayrollError):
    message = "The WPS salary file is for businesses in the UAE."


class NotPostedError(PayrollError):
    message = "The WPS salary file is ready once the payroll is posted."


class NoEmployerIdsError(PayrollError):
    message = (
        "Add the business's MOL establishment ID and its bank's routing code on the Holidays "
        "and work week screen first."
    )


class MissingDetailsError(PayrollError):
    message = (
        "These people need a labour card person ID, a bank routing code and an account on the "
        "Employees screen:"
    )


class BadDetailsError(PayrollError):
    message = "Some WPS details are not in the form the bank expects. Check them:"


def salary_file(run: PayrollRun, made: datetime | None = None) -> tuple[str, str]:
    settings = settings_for()
    if settings.holiday_country != "AE":
        raise NotUaeError
    if run.status != PayrollRun.Status.POSTED:
        raise NotPostedError
    if not settings.wps_employer_id or not settings.wps_bank_code:
        raise NoEmployerIdsError
    employer = Employer(settings.wps_employer_id, settings.wps_bank_code)
    end = month_end(run.month)
    slips = Payslip.objects.filter(run=run).select_related("employee").order_by("employee__code")
    missing: list[str] = []
    lines: list[Line] = []
    for slip in slips:
        person = slip.employee
        if not (person.wps_person_id and person.wps_agent_code and person.bank_account):
            missing.append(person.code)
            continue
        lines.append(
            Line(
                person.wps_person_id,
                person.wps_agent_code,
                person.bank_account.replace(" ", ""),
                # The period saved with the payslip; older payslips fall back to the record
                # as it is now, kept inside the month.
                slip.starts_on or min(max(run.month, person.joined_on), end),
                slip.ends_on or max(min(end, person.left_on or end), run.month),
                slip.net,
                # The SIF counts whole days of leave without pay; a half day absent rounds
                # up, so 1.5 shows as 2 rather than disappearing.
                unpaid_days=int(slip.unpaid_days.quantize(Decimal(1), rounding=ROUND_HALF_UP)),
            )
        )
    if missing:
        raise MissingDetailsError(*missing)
    try:
        return sif(employer, run.month, made or timezone.localtime(), lines, run.number or "")
    except WpsError as exc:
        raise BadDetailsError(str(exc)) from exc
