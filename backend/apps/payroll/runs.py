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

EOBI and social security come from the rates and minimum wages in force on the first of the
month (contributions.py). The staff's share is a deduction line on the payslip; the business's
share is stored beside it and booked as a cost.
"""

import calendar
import json
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, cast

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.accounting import services as accounting
from apps.accounting.models import JournalEntry
from apps.accounts.models import User
from apps.core import posting
from apps.core.payroll import Breakdown, Component, breakdown, combine, share
from apps.core.payroll import PayrollError as PayMathError
from apps.core.salary_tax import Slab, months_left, withholding
from apps.hr.models import Attendance, Contract, Employee, Holiday, LeaveRequest
from apps.hr.time_off import settings_for
from apps.platform.locking import lock_rows
from apps.tenancy import audit
from apps.tenancy.models import AuditEvent

from .contributions import Book, Contribution, insurable_wage
from .gratuity import (
    GRATUITY_COUNTRIES,
    NoRuleError,
    accrued_before,
    applies,
    built_up,
    unpaid_before,
)
from .gratuity import rule_for as gratuity_rule_for
from .models import (
    GratuityPayout,
    GratuityRule,
    OpeningPay,
    PayrollRun,
    Payslip,
    SalaryPayment,
    TaxTable,
)
from .services import (
    TAX_YEAR_STARTS,
    PayrollError,
    lock_business,
    slabs_of,
    table_for,
    tax_year,
)

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


class UndoneError(PayrollError):
    message = "This month's payroll was undone, so it can't be posted. Work the month out again."


class NotPostedError(PayrollError):
    message = "Only a posted payroll can be undone."


class PaidError(PayrollError):
    message = (
        "This month's salaries are already paid, so it can't be undone. The money has left the "
        "bank; correct it in next month's payroll instead."
    )


class GratuityPaidError(PayrollError):
    message = (
        "Someone in this month was paid their end-of-service gratuity, which counted this "
        "month, so it can't be undone."
    )


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
    contributions: tuple[Contribution, ...] = ()
    gratuity_accrued: Decimal = ZERO
    gratuity_change: Decimal = ZERO

    @property
    def net(self) -> Decimal:
        return self.pay.net - self.tax

    @property
    def employee_contributions(self) -> Decimal:
        return sum((c.share.employee for c in self.contributions), ZERO)

    @property
    def employer_contributions(self) -> Decimal:
        return sum((c.share.employer for c in self.contributions), ZERO)


def month_end(month: date) -> date:
    return month.replace(day=calendar.monthrange(month.year, month.month)[1])


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=n) for n in range((end - start).days + 1)]


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
    """Each person's taxable pay and tax this tax year before the month: posted payslips plus
    any pay from before payroll ran here."""
    year_start, _ = tax_year(first_day, first_month)
    earlier: dict[int, dict[str, Any]] = {
        row["employee_id"]: row
        for row in Payslip.objects.filter(
            run__status=PayrollRun.Status.POSTED,
            run__month__gte=year_start,
            run__month__lt=first_day,
        )
        .values("employee_id")
        .annotate(income=Sum("taxable"), tax=Sum("tax"))
    }
    # Pay from before payroll ran here counts as earlier in the year too.
    for opening in OpeningPay.objects.filter(year_starts=year_start):
        row = earlier.setdefault(opening.employee_id, {"income": ZERO, "tax": ZERO})
        row["income"] = (row["income"] or ZERO) + opening.taxable
        row["tax"] = (row["tax"] or ZERO) + opening.tax
    return earlier


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
    book = Book(first_day, country)
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
        try:
            pay, owed = book.deduct(person, pay, insurable_wage(contracts[person.pk][-1]))
        except PayMathError:
            too_low.append(person.code)
            continue
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
            Figures(
                person, pay, month.days, paid_days, unpaid_days, tax, projected, due, tuple(owed)
            )
        )
    book.check()
    if too_low:
        raise PayTooLowError(*too_low)
    if not figures:
        raise NobodyToPayError
    return table, _with_gratuity(first_day, country, contracts, figures)


def _with_gratuity(
    first_day: date, country: str, contracts: dict[int, list[Contract]], figures: list[Figures]
) -> list[Figures]:
    """Each person's end-of-service gratuity built up by the month's end, or by the day they
    left, and how much that grew since the last posted month."""
    if country not in GRATUITY_COUNTRIES:
        return figures
    end = month_end(first_day)
    unpaid = unpaid_before(first_day)
    before = accrued_before(first_day)
    # The rule in force on each person's own date, the month's end or the day they left, so a
    # rule that starts mid-month counts for whoever is still there on it. Few distinct dates.
    rules: dict[date, GratuityRule | None] = {}
    updated: list[Figures] = []
    for f in figures:
        person = f.employee
        until = min(end, person.left_on or end)
        if until not in rules:
            rules[until] = gratuity_rule_for(country, until)
        row = rules[until]
        if row is None:
            raise NoRuleError
        if not applies(row, person, country):
            # Someone now left out, such as a worker recorded as a UAE national later, gets
            # nothing, so what was set aside for them comes back.
            earlier = before.get(person.pk, ZERO)
            updated.append(replace(f, gratuity_accrued=ZERO, gratuity_change=-earlier))
            continue
        # The contract in force at the month's end; contracts come ordered by start.
        contract = contracts[person.pk][-1]
        days_off = unpaid.get(person.pk, ZERO) + f.unpaid_days
        _, _, result = built_up(row, person, contract, until, days_off)
        change = result.full - before.get(person.pk, ZERO)
        updated.append(replace(f, gratuity_accrued=result.full, gratuity_change=change))
    return updated


def _check_order(run: PayrollRun, posting_it: bool) -> None:
    """Salary tax counts the earlier months of its tax year, and the gratuity provision the
    month before, so those months are posted in order."""
    country = settings_for().holiday_country
    first = TAX_YEAR_STARTS.get(country)
    if first is not None:
        start, end = tax_year(run.month, first)
    elif country in GRATUITY_COUNTRIES:
        start, end = date.min, date.max
    else:
        return
    same_year = PayrollRun.objects.filter(month__range=(start, end)).exclude(pk=run.pk)
    if same_year.filter(month__gt=run.month, status=PayrollRun.Status.POSTED).exists():
        raise LaterPostedError
    if posting_it and same_year.filter(month__lt=run.month, status=PayrollRun.Status.DRAFT):
        raise EarlierDraftError


def _lines(pay: Breakdown) -> list[dict[str, Any]]:
    return [
        {"name": line.name, "kind": line.kind, "amount": str(line.amount), "taxable": line.taxable}
        for line in pay.lines
    ]


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
                lines=_lines(f.pay),
                gross=f.pay.gross,
                deductions=f.pay.deductions,
                taxable=f.pay.taxable,
                tax=f.tax,
                net=f.net,
                projected_income=f.projected_income,
                year_tax=f.year_tax,
                contributions=[c.as_json() for c in f.contributions],
                employee_contributions=f.employee_contributions,
                employer_contributions=f.employer_contributions,
                gratuity_accrued=f.gratuity_accrued,
                gratuity_change=f.gratuity_change,
            )
            for f in figures
        ]
    )
    run.tax_table = table
    run.gross = sum((f.pay.gross for f in figures), ZERO)
    run.deductions = sum((f.pay.deductions for f in figures), ZERO)
    run.tax = sum((f.tax for f in figures), ZERO)
    run.net = sum((f.net for f in figures), ZERO)
    run.employee_contributions = sum((f.employee_contributions for f in figures), ZERO)
    run.employer_contributions = sum((f.employer_contributions for f in figures), ZERO)
    run.gratuity_change = sum((f.gratuity_change for f in figures), ZERO)
    run.save()


def _totals(run: PayrollRun) -> dict[str, str]:
    return {"gross": str(run.gross), "tax": str(run.tax), "net": str(run.net)}


@transaction.atomic
def work_out(actor: User, month: date) -> PayrollRun:
    """Work out a month's payroll as a draft, or work out an existing draft again."""
    first_day = month.replace(day=1)
    lock_business()
    rows = lock_rows(PayrollRun.objects.filter(live_month=first_day))
    run = rows[0] if rows else PayrollRun(month=first_day, live_month=first_day)
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
    # The lines and contributions go in as text, so a renamed or reworded part counts as a
    # change even when the totals are the same; the payslip prints them.
    return sorted(
        tuple(json.dumps(v, sort_keys=True) if isinstance(v, list) else v for v in row)
        for row in rows
    )


@transaction.atomic
def post(actor: User, run: PayrollRun) -> bool:
    """Post a draft and book its journal entry. Pay is worked out once more first; if anything
    changed since the draft was made (a contract, leave, attendance), the draft is updated
    instead and False comes back, so nobody posts figures they haven't seen."""
    lock_business()
    locked: PayrollRun = lock_rows(PayrollRun.objects.filter(pk=run.pk))[0]
    if locked.status == PayrollRun.Status.POSTED:
        raise AlreadyPostedError
    # Only a draft posts. An undone run is history: posting it again would give its month a
    # second live run outside the one-live-run rule.
    if locked.status != PayrollRun.Status.DRAFT:
        raise UndoneError
    _check_order(locked, posting_it=True)
    table, figures = work_out_figures(locked.month)
    fresh = _fingerprint(
        [
            (
                f.employee.pk,
                f.pay.gross,
                f.pay.deductions,
                f.tax,
                f.paid_days,
                f.projected_income,
                f.year_tax,
                f.employer_contributions,
                f.gratuity_accrued,
                f.gratuity_change,
                [c.as_json() for c in f.contributions],
                _lines(f.pay),
            )
            for f in figures
        ]
    )
    stored = _fingerprint(
        list(
            locked.payslips.values_list(
                "employee_id",
                "gross",
                "deductions",
                "tax",
                "paid_days",
                "projected_income",
                "year_tax",
                "employer_contributions",
                "gratuity_accrued",
                "gratuity_change",
                "contributions",
                "lines",
            )
        )
    )
    if fresh != stored or table != locked.tax_table:
        _store(locked, table, figures)
        audit.record(Action.UPDATE, locked, actor, {"worked_out_again": [None, _totals(locked)]})
        return False
    lines = posting.payroll(
        locked.gross,
        locked.deductions - locked.employee_contributions,
        locked.tax,
        locked.employee_contributions,
        locked.employer_contributions,
        locked.gratuity_change,
    )
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


@transaction.atomic
def reverse(actor: User, run: PayrollRun, reason: str = "") -> PayrollRun:
    """Undo a posted month. Its entry is reversed on the same date, so the month's books net to
    nothing; the run stays as history, marked reversed, with its payslips and number. The month
    can then be worked out again.

    A paid month can't be undone: the money has gone. Nor can a month once a later month of the
    same tax year is posted, because that month's tax counted this one.
    """
    lock_business()
    locked: PayrollRun = lock_rows(PayrollRun.objects.filter(pk=run.pk))[0]
    if locked.status != PayrollRun.Status.POSTED:
        raise NotPostedError
    if SalaryPayment.objects.filter(run=locked).exists():
        raise PaidError
    if GratuityPayout.objects.filter(employee__payslips__run=locked).exists():
        raise GratuityPaidError
    _check_order(locked, posting_it=False)
    # Posting always sets the entry, so a posted run has one.
    entry = cast(JournalEntry, locked.entry)
    memo = f"Payroll {locked.month:%B %Y} undone" + (f": {reason}" if reason else "")
    locked.reversal = accounting.reverse_entry(actor, entry, entry.date, memo[:255])
    locked.status = PayrollRun.Status.REVERSED
    locked.live_month = None
    locked.reversed_by = actor
    locked.reversed_at = timezone.now()
    locked.reversal_reason = reason
    locked.save()
    audit.record(
        Action.UPDATE, locked, actor, {"status": ["posted", "reversed"], "reason": [None, reason]}
    )
    return locked
