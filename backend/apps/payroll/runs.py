"""Monthly payroll: work out everyone's pay for a month, then post it.

Pay is by calendar day. Someone who joins on the 16th of a 30-day month gets 15 days' pay, a raise
from the 11th pays 10 days at the old contract and 20 at the new one, and each unpaid day comes
off: approved leave of an unpaid kind, and days marked absent (a half day counts as half), on
working days only and never on a day of paid leave.

Income tax uses the year's slabs and what this tax year's posted payslips already paid and
withheld (apps/core/salary_tax.py). That only adds up if the months are posted in order, so a
month can't be posted while an earlier one of its tax year is still a draft, and can't be worked
out once a later one is posted. Tax paid through another employer earlier in the year isn't
known here; the person settles that in their return.
"""

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.accounting import services as accounting
from apps.accounts.models import User
from apps.core import posting
from apps.core.payroll import Breakdown, Component, breakdown, combine, share
from apps.core.payroll import PayrollError as PayMathError
from apps.core.salary_tax import Slab, months_left, withholding
from apps.core.workdays import tax_year_end
from apps.hr.models import Attendance, Contract, Employee, Holiday, LeaveRequest
from apps.hr.time_off import settings_for
from apps.platform.locking import lock_rows
from apps.tenancy import audit
from apps.tenancy.models import AuditEvent

from .models import PayrollRun, Payslip, TaxTable
from .services import TAX_YEAR_STARTS, PayrollError, slabs_of, table_for

Action = AuditEvent.Action
ZERO = Decimal(0)
HALF = Decimal("0.5")
SERIES = ("payroll", "PAY-")


class NoTaxTableError(PayrollError):
    message = (
        "There are no salary tax slabs for this month's tax year. Fill them in on the Tax slabs "
        "screen first."
    )


class NobodyToPayError(PayrollError):
    message = "Nobody had a contract this month, so there is nothing to pay."


class AlreadyPostedError(PayrollError):
    message = "This month's payroll is posted, so it can't be changed."


class NotDraftError(PayrollError):
    message = "Only a payroll that isn't posted yet can be removed."


class EarlierDraftError(PayrollError):
    message = (
        "An earlier month of this tax year isn't posted yet. Post the months in order, so each "
        "month's tax counts the ones before it."
    )


class LaterPostedError(PayrollError):
    message = "A later month of this tax year is already posted, so this month can't change."


class PayTooLowError(PayrollError):
    message = (
        "For these people, deductions and tax come to more than the pay this month. Check their "
        "salary structure and unpaid days:"
    )


@dataclass(frozen=True)
class Figures:
    employee: Employee
    pay: Breakdown
    month_days: int
    paid_days: Decimal
    unpaid_days: Decimal
    tax: Decimal
    projected_income: Decimal
    year_tax: Decimal

    @property
    def net(self) -> Decimal:
        return self.pay.net - self.tax


def month_end(month: date) -> date:
    return month.replace(day=calendar.monthrange(month.year, month.month)[1])


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=n) for n in range((end - start).days + 1)]


def _tax_year(month: date, first: int) -> tuple[date, date]:
    end = tax_year_end(month, first)
    return date(end.year if first == 1 else end.year - 1, first, 1), end


@dataclass(frozen=True)
class _Month:
    start: date
    end: date
    days: int
    weekend: set[int]
    holidays: set[date]

    def working(self, day: date) -> bool:
        return day.weekday() not in self.weekend and day not in self.holidays


def _unpaid(
    month: _Month, leave: list[LeaveRequest], marks: list[Attendance]
) -> dict[date, Decimal]:
    paid_leave: set[date] = set()
    unpaid: dict[date, Decimal] = {}
    for request in leave:
        for day in _days(max(request.starts_on, month.start), min(request.ends_on, month.end)):
            if not month.working(day):
                continue
            if request.leave_type.paid:
                paid_leave.add(day)
            else:
                unpaid[day] = Decimal(1)
    for mark in marks:
        if month.working(mark.on) and mark.on not in paid_leave and mark.on not in unpaid:
            unpaid[mark.on] = Decimal(1) if mark.status == Attendance.Status.ABSENT else HALF
    return unpaid


def _person(
    month: _Month, person: Employee, contracts: list[Contract], unpaid: dict[date, Decimal]
) -> tuple[Breakdown, Decimal, Decimal] | None:
    """The month's pay before tax, and the paid and unpaid days, or None with no contract."""
    parts: list[Breakdown] = []
    paid_days = unpaid_days = ZERO
    for contract in contracts:
        start = max(month.start, person.joined_on, contract.starts_on)
        end = min(month.end, person.left_on or month.end, contract.ends_on or month.end)
        if end < start:
            continue
        off = sum((v for day, v in unpaid.items() if start <= day <= end), ZERO)
        paid = Decimal((end - start).days + 1) - off
        components = [
            Component(c.name, c.kind, c.amount, c.percent, c.taxable)
            for c in contract.structure.components.all()
        ]
        parts.append(share(breakdown(contract.basic_salary, components), paid, month.days))
        paid_days += paid
        unpaid_days += off
    if not parts:
        return None
    return combine(parts), paid_days, unpaid_days


Records = tuple[
    list[Employee],
    dict[int, list[Contract]],
    dict[int, list[LeaveRequest]],
    dict[int, list[Attendance]],
]


def _month_records(first_day: date, end: date) -> Records:
    """Who was employed in the month, with their contracts, approved leave and absences."""
    people = list(
        Employee.objects.filter(joined_on__lte=end)
        .filter(Q(left_on__isnull=True) | Q(left_on__gte=first_day))
        .order_by("code")
    )
    contracts: dict[int, list[Contract]] = defaultdict(list)
    for contract in (
        Contract.objects.filter(starts_on__lte=end)
        .filter(Q(ends_on__isnull=True) | Q(ends_on__gte=first_day))
        .select_related("structure")
        .prefetch_related("structure__components")
        .order_by("starts_on")
    ):
        contracts[contract.employee_id].append(contract)
    leave: dict[int, list[LeaveRequest]] = defaultdict(list)
    for request in LeaveRequest.objects.filter(
        status=LeaveRequest.Status.APPROVED, starts_on__lte=end, ends_on__gte=first_day
    ).select_related("leave_type"):
        leave[request.employee_id].append(request)
    marks: dict[int, list[Attendance]] = defaultdict(list)
    for mark in Attendance.objects.filter(
        on__range=(first_day, end),
        status__in=[Attendance.Status.ABSENT, Attendance.Status.HALF_DAY],
    ):
        marks[mark.employee_id].append(mark)
    return people, contracts, leave, marks


def _earlier_this_tax_year(first_day: date, first_month: int) -> dict[int, dict[str, Any]]:
    """Each person's taxable pay and tax on this tax year's posted payslips before the month."""
    year_start, _ = _tax_year(first_day, first_month)
    return {
        row["employee_id"]: row
        for row in Payslip.objects.filter(
            run__status=PayrollRun.Status.POSTED,
            run__month__gte=year_start,
            run__month__lt=first_day,
        )
        .values("employee_id")
        .annotate(income=Sum("taxable"), tax=Sum("tax"))
    }


def work_out_figures(first_day: date) -> tuple[TaxTable | None, list[Figures]]:
    """Everyone's figures for the month starting `first_day`, without saving anything."""
    end = month_end(first_day)
    settings = settings_for()
    country = settings.holiday_country
    table = None
    first_month = TAX_YEAR_STARTS.get(country)
    if first_month is not None:
        # Locked, so the slabs can't change between working the month out and storing or
        # posting it; both callers are inside a transaction.
        table = table_for(country, first_day)
        if table is None:
            raise NoTaxTableError
    holidays = set(Holiday.objects.filter(on__range=(first_day, end)).values_list("on", flat=True))
    month = _Month(first_day, end, end.day, set(settings.weekend), holidays)

    people, contracts, leave, marks = _month_records(first_day, end)
    earlier: dict[int, dict[str, Any]] = {}
    slabs: list[Slab] = []
    left = 1
    if table is not None and first_month is not None:
        slabs = slabs_of(table)
        left = months_left(first_day, first_month)
        earlier = _earlier_this_tax_year(first_day, first_month)

    figures: list[Figures] = []
    too_low: list[str] = []
    for person in people:
        try:
            worked = _person(
                month,
                person,
                contracts[person.pk],
                _unpaid(month, leave[person.pk], marks[person.pk]),
            )
        except PayMathError:
            too_low.append(person.code)
            continue
        if worked is None:
            continue
        pay, paid_days, unpaid_days = worked
        tax = projected = due = ZERO
        if table is not None:
            before = earlier.get(person.pk, {})
            result = withholding(
                pay.taxable, before.get("income") or ZERO, before.get("tax") or ZERO, left, slabs
            )
            tax, projected, due = result.tax, result.projected_income, result.year_tax
        if pay.net - tax < 0:
            too_low.append(person.code)
            continue
        figures.append(
            Figures(person, pay, month.days, paid_days, unpaid_days, tax, projected, due)
        )
    if too_low:
        raise PayTooLowError(*too_low)
    if not figures:
        raise NobodyToPayError
    return table, figures


def _check_order(run: PayrollRun, posting_it: bool) -> None:
    first = TAX_YEAR_STARTS.get(settings_for().holiday_country)
    if first is None:
        return
    start, end = _tax_year(run.month, first)
    same_year = PayrollRun.objects.filter(month__range=(start, end)).exclude(pk=run.pk)
    if same_year.filter(month__gt=run.month, status=PayrollRun.Status.POSTED).exists():
        raise LaterPostedError
    if posting_it and same_year.filter(month__lt=run.month, status=PayrollRun.Status.DRAFT):
        raise EarlierDraftError


def _store(run: PayrollRun, table: TaxTable | None, figures: list[Figures]) -> None:
    run.payslips.all().delete()
    Payslip.objects.bulk_create(
        [
            Payslip(
                tenant=run.tenant,
                run=run,
                employee=f.employee,
                month_days=f.month_days,
                paid_days=f.paid_days,
                unpaid_days=f.unpaid_days,
                lines=[
                    {
                        "name": line.name,
                        "kind": line.kind,
                        "amount": str(line.amount),
                        "taxable": line.taxable,
                    }
                    for line in f.pay.lines
                ],
                gross=f.pay.gross,
                deductions=f.pay.deductions,
                taxable=f.pay.taxable,
                tax=f.tax,
                net=f.net,
                projected_income=f.projected_income,
                year_tax=f.year_tax,
            )
            for f in figures
        ]
    )
    run.tax_table = table
    run.gross = sum((f.pay.gross for f in figures), ZERO)
    run.deductions = sum((f.pay.deductions for f in figures), ZERO)
    run.tax = sum((f.tax for f in figures), ZERO)
    run.net = sum((f.net for f in figures), ZERO)
    run.save()


def _totals(run: PayrollRun) -> dict[str, str]:
    return {"gross": str(run.gross), "tax": str(run.tax), "net": str(run.net)}


@transaction.atomic
def work_out(actor: User, month: date) -> PayrollRun:
    """Work out a month's payroll as a draft, or work out an existing draft again."""
    first_day = month.replace(day=1)
    rows = lock_rows(PayrollRun.objects.filter(month=first_day))
    run = rows[0] if rows else PayrollRun(month=first_day)
    if run.status == PayrollRun.Status.POSTED:
        raise AlreadyPostedError
    _check_order(run, posting_it=False)
    creating = run.pk is None
    before = {} if creating else _totals(run)
    table, figures = work_out_figures(first_day)
    if creating:
        run.save()
    _store(run, table, figures)
    after = _totals(run)
    changes = {k: [before.get(k), after[k]] for k in after}
    audit.record(Action.CREATE if creating else Action.UPDATE, run, actor, changes)
    return run


def _fingerprint(rows: list[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    return sorted(rows)


@transaction.atomic
def post(actor: User, run: PayrollRun) -> bool:
    """Post a draft and book its journal entry. Pay is worked out once more first; if anything
    changed since the draft was made (a contract, leave, attendance), the draft is updated
    instead and False comes back, so nobody posts figures they haven't seen."""
    locked: PayrollRun = lock_rows(PayrollRun.objects.filter(pk=run.pk))[0]
    if locked.status == PayrollRun.Status.POSTED:
        raise AlreadyPostedError
    _check_order(locked, posting_it=True)
    table, figures = work_out_figures(locked.month)
    fresh = _fingerprint(
        [(f.employee.pk, f.pay.gross, f.pay.deductions, f.tax, f.paid_days) for f in figures]
    )
    stored = _fingerprint(
        list(locked.payslips.values_list("employee_id", "gross", "deductions", "tax", "paid_days"))
    )
    if fresh != stored or table != locked.tax_table:
        _store(locked, table, figures)
        audit.record(Action.UPDATE, locked, actor, {"worked_out_again": [None, _totals(locked)]})
        return False
    lines = posting.payroll(locked.gross, locked.deductions, locked.tax)
    entry = accounting.post_rule_lines(
        actor,
        month_end(locked.month),
        f"Payroll {locked.month:%B %Y}",
        lines,
        {},
        ("payroll_run", str(locked.pk)),
    )
    locked.number = accounting.next_number(*SERIES)
    locked.status = PayrollRun.Status.POSTED
    locked.entry = entry
    locked.posted_by = actor
    locked.posted_at = timezone.now()
    locked.save()
    audit.record(Action.POST, locked, actor, {"number": [None, locked.number]})
    return True


@transaction.atomic
def delete(actor: User, run: PayrollRun) -> None:
    locked: PayrollRun = lock_rows(PayrollRun.objects.filter(pk=run.pk))[0]
    if locked.status != PayrollRun.Status.DRAFT:
        raise NotDraftError
    audit.record(Action.DELETE, locked, actor, {"net": [str(locked.net), None]})
    locked.delete()
