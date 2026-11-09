"""The working week, public holidays, leave and attendance."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from importlib.metadata import version
from typing import Any

import holidays as holiday_data
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet, Sum
from django.utils import timezone

from apps.accounts.models import User
from apps.core.workdays import WorkdayError, working_days
from apps.inventory import services as inventory
from apps.platform.locking import lock_rows
from apps.tenancy import audit
from apps.tenancy.models import AuditEvent

from .models import Attendance, Employee, Holiday, HrSettings, LeaveRequest, LeaveType
from .services import HrError

Action = AuditEvent.Action
# The countries the app is built for. Others can be added once someone checks their list.
COUNTRIES = ("PK", "AE", "SA")
# The language of filled-in holiday names. Left unset, the library guesses from the server's
# locale, so the same year could come out in Urdu on one machine and English on another.
NAME_LANGUAGES = {"PK": "en_PK", "AE": "en_US", "SA": "en_US"}
MAX_LEAVE_DAYS = 366
MAX_ATTENDANCE_ROWS = 1000


class BadWeekendError(HrError):
    message = "Pick weekend days from Monday to Sunday, leaving at least one working day."


class BadCountryError(HrError):
    message = "Holidays can be filled in for Pakistan, the UAE and Saudi Arabia."


class ShortRetentionError(HrError):
    message = "National IDs must be kept at least 6 years after the tax year someone leaves in."


class DuplicateHolidayError(HrError):
    message = "There is already a holiday on that day."


class LeaveOverlapError(HrError):
    message = "This person already has leave asked for or approved on some of those days."


class NoWorkingDaysError(HrError):
    message = "Those dates are all weekend or holidays, so no leave is needed."


class TooLongError(HrError):
    message = "Leave can be asked for at most a year at a time."


class CrossesYearError(HrError):
    message = "Leave over New Year needs two requests, one for each year's days."


class NotEmployedError(HrError):
    message = "Those dates are outside the time this person works here."


class NotPendingError(HrError):
    message = "This leave has already been decided."


class OverBalanceError(HrError):
    message = "That is more leave of this kind than this person has left this year."


class InactiveLeaveTypeError(HrError):
    message = "That kind of leave is switched off."


def settings_for() -> HrSettings:
    return HrSettings.objects.first() or HrSettings()


@transaction.atomic
def save_settings(actor: User, data: dict[str, Any]) -> HrSettings:
    target = HrSettings.objects.select_for_update().first() or HrSettings()
    created = target.pk is None
    fields = (
        "weekend",
        "holiday_country",
        "id_retention_years",
        "default_province",
        "wps_employer_id",
        "wps_bank_code",
    )
    before = {f: getattr(target, f) for f in fields}
    for key in ("default_province", "wps_employer_id", "wps_bank_code"):
        if key in data:
            setattr(target, key, data[key])
    if "weekend" in data:
        weekend = sorted(set(data["weekend"]))
        if any(not isinstance(d, int) or not 0 <= d <= 6 for d in weekend) or len(weekend) == 7:
            raise BadWeekendError
        target.weekend = weekend
    if "holiday_country" in data:
        if data["holiday_country"] not in COUNTRIES:
            raise BadCountryError
        target.holiday_country = data["holiday_country"]
    if "id_retention_years" in data:
        if data["id_retention_years"] < 6:
            raise ShortRetentionError
        target.id_retention_years = data["id_retention_years"]
    target.save()
    changes = {
        f: [before[f], getattr(target, f)] for f in fields if before[f] != getattr(target, f)
    }
    audit.record(Action.CREATE if created else Action.UPDATE, target, actor, changes)
    return target


def holiday_dates(start: date, end: date) -> set[date]:
    return set(Holiday.objects.filter(on__range=(start, end)).values_list("on", flat=True))


def count_days(start: date, end: date) -> int:
    settings = settings_for()
    try:
        return working_days(start, end, settings.weekend, holiday_dates(start, end))
    except WorkdayError as exc:
        raise BadWeekendError from exc


@transaction.atomic
def fill_holidays(actor: User, year: int) -> int:
    """Add the country's public holidays for a year from the holidays library. Days already on
    the list are left alone, so a date the business corrected stays corrected."""
    country = settings_for().holiday_country
    source = f"holidays {version('holidays')}; moon-sighted dates are estimates, check them"
    taken = set(Holiday.objects.filter(on__year=year).values_list("on", flat=True))
    added = 0
    found = holiday_data.country_holidays(
        country, years=year, language=NAME_LANGUAGES.get(country, "en_US")
    )
    for on, name in sorted(found.items()):
        if on in taken:
            continue
        holiday = Holiday.objects.create(on=on, name=str(name)[:100], source=source)
        audit.record(
            Action.CREATE, holiday, actor, {"on": [None, str(on)], "name": [None, holiday.name]}
        )
        taken.add(on)
        added += 1
    return added


def save_holiday(actor: User, holiday: Holiday, data: dict[str, Any]) -> Holiday:
    try:
        saved: Holiday = inventory.save_master(actor, holiday, data)
    except inventory.DuplicateError as exc:
        raise DuplicateHolidayError from exc
    return saved


# Leave


@dataclass(frozen=True)
class Balance:
    leave_type: LeaveType
    allowed: Decimal
    taken: Decimal
    pending: Decimal

    @property
    def left(self) -> Decimal | None:
        """None means no yearly limit."""
        return None if self.allowed == 0 else self.allowed - self.taken


def _used(employee: Employee, leave_type: LeaveType, year: int, status: str) -> Decimal:
    total = LeaveRequest.objects.filter(
        employee=employee, leave_type=leave_type, status=status, starts_on__year=year
    ).aggregate(total=Sum("days"))["total"]
    return total or Decimal(0)


def balances(employee: Employee, year: int) -> list[Balance]:
    return [
        Balance(
            kind,
            kind.days_per_year,
            _used(employee, kind, year, LeaveRequest.Status.APPROVED),
            _used(employee, kind, year, LeaveRequest.Status.PENDING),
        )
        for kind in LeaveType.objects.filter(is_active=True)
    ]


def _overlapping_leave(employee: Employee, start: date, end: date) -> QuerySet[LeaveRequest]:
    return LeaveRequest.objects.filter(
        employee=employee,
        status__in=[LeaveRequest.Status.PENDING, LeaveRequest.Status.APPROVED],
        starts_on__lte=end,
        ends_on__gte=start,
    )


@transaction.atomic
def ask_leave(actor: User, data: dict[str, Any]) -> LeaveRequest:
    employee: Employee = data["employee"]
    kind: LeaveType = data["leave_type"]
    start, end = data["starts_on"], data["ends_on"]
    lock_rows(Employee.objects.filter(pk=employee.pk))
    if not kind.is_active:
        raise InactiveLeaveTypeError
    if (end - start).days >= MAX_LEAVE_DAYS:
        raise TooLongError
    # Allowances are per calendar year and a request's days count in the year it starts, so
    # leave over New Year is asked for as two requests.
    if start.year != end.year:
        raise CrossesYearError
    if start < employee.joined_on or (employee.left_on and end > employee.left_on):
        raise NotEmployedError
    if _overlapping_leave(employee, start, end).exists():
        raise LeaveOverlapError
    days = count_days(start, end)
    if days == 0:
        raise NoWorkingDaysError
    request: LeaveRequest = LeaveRequest.objects.create(
        employee=employee,
        leave_type=kind,
        starts_on=start,
        ends_on=end,
        days=Decimal(days),
        note=data.get("note", ""),
    )
    audit.record(Action.CREATE, request, actor, {"days": [None, str(request.days)]})
    return request


@transaction.atomic
def decide_leave(actor: User, request: LeaveRequest, approve: bool) -> LeaveRequest:
    """Approving checks the balance under a lock on the employee, so two approvals at once
    can't both use the last days left."""
    lock_rows(Employee.objects.filter(pk=request.employee_id))
    locked: LeaveRequest = lock_rows(LeaveRequest.objects.filter(pk=request.pk))[0]
    if locked.status != LeaveRequest.Status.PENDING:
        raise NotPendingError
    if approve:
        kind = locked.leave_type
        if kind.days_per_year > 0:
            taken = _used(
                locked.employee, kind, locked.starts_on.year, LeaveRequest.Status.APPROVED
            )
            if taken + locked.days > kind.days_per_year:
                raise OverBalanceError
    locked.status = LeaveRequest.Status.APPROVED if approve else LeaveRequest.Status.REJECTED
    locked.decided_by = actor
    locked.decided_at = timezone.now()
    locked.save(update_fields=["status", "decided_by", "decided_at"])
    audit.record(Action.UPDATE, locked, actor, {"status": ["pending", locked.status]})
    return locked


@transaction.atomic
def withdraw_leave(actor: User, request: LeaveRequest) -> None:
    locked: LeaveRequest = lock_rows(LeaveRequest.objects.filter(pk=request.pk))[0]
    if locked.status != LeaveRequest.Status.PENDING:
        raise NotPendingError
    audit.record(Action.DELETE, locked, actor, {"days": [str(locked.days), None]})
    locked.delete()


class NotApprovedError(HrError):
    message = (
        "Only approved leave can be cancelled. A request that isn't approved yet can be withdrawn."
    )


class NothingToGiveBackError(HrError):
    message = "They came back after the leave ended, so there are no days to give back."


class LeaveInPostedPayrollError(HrError):
    message = (
        "Payroll is posted for a month with these unpaid days, so they already came off the pay. "
        "Undo that payroll first."
    )


def _unpaid_days_paid_out(employee: Employee, start: date, end: date) -> bool:
    # Imported here: payroll builds on HR, and only this check looks the other way.
    from apps.payroll.models import PayrollRun  # noqa: PLC0415

    return PayrollRun.objects.filter(
        status=PayrollRun.Status.POSTED,
        month__lte=end,
        month__gte=start.replace(day=1),
        payslips__employee=employee,
    ).exists()


@transaction.atomic
def cancel_leave(actor: User, request: LeaveRequest, back_on: date | None = None) -> LeaveRequest:
    """Give back approved leave: all of it, or, for someone who came back early, the days from
    `back_on` (their first day back). A shortened request counts its working days again, so the
    yearly balance gets the rest back.

    Unpaid days in a month whose payroll is posted already came off the pay, so they can't be
    given back until that payroll is undone. Paid leave doesn't change pay, so it can.
    """
    lock_rows(Employee.objects.filter(pk=request.employee_id))
    locked: LeaveRequest = lock_rows(
        LeaveRequest.objects.filter(pk=request.pk).select_related("leave_type")
    )[0]
    if locked.status != LeaveRequest.Status.APPROVED:
        raise NotApprovedError
    give_from = locked.starts_on if back_on is None else max(back_on, locked.starts_on)
    if give_from > locked.ends_on:
        raise NothingToGiveBackError
    if not locked.leave_type.paid and _unpaid_days_paid_out(
        locked.employee, give_from, locked.ends_on
    ):
        raise LeaveInPostedPayrollError
    before = {"ends_on": str(locked.ends_on), "days": str(locked.days), "status": locked.status}
    if give_from == locked.starts_on:
        locked.status = LeaveRequest.Status.CANCELLED
    else:
        locked.ends_on = give_from - timedelta(days=1)
        locked.days = Decimal(count_days(locked.starts_on, locked.ends_on))
        if locked.days == 0:
            # Only weekends and holidays were left: nothing was taken.
            locked.status = LeaveRequest.Status.CANCELLED
    locked.save(update_fields=["status", "ends_on", "days"])
    after = {"ends_on": str(locked.ends_on), "days": str(locked.days), "status": locked.status}
    audit.record(Action.UPDATE, locked, actor, {k: [before[k], after[k]] for k in after})
    return locked


# Attendance


@dataclass(frozen=True)
class DayRow:
    employee: Employee
    status: str
    note: str = ""


def on_leave(on: date) -> set[int]:
    return set(
        LeaveRequest.objects.filter(
            status=LeaveRequest.Status.APPROVED, starts_on__lte=on, ends_on__gte=on
        ).values_list("employee_id", flat=True)
    )


def working(on: date) -> QuerySet[Employee]:
    """People employed on that day."""
    return Employee.objects.filter(joined_on__lte=on).filter(
        Q(left_on__isnull=True) | Q(left_on__gte=on)
    )


@transaction.atomic
def mark_day(actor: User, on: date, rows: list[DayRow]) -> int:
    """Record a day's attendance for several people at once. A row marked present for someone
    with no earlier row adds nothing, because a missing row already counts as present."""
    if len(rows) > MAX_ATTENDANCE_ROWS:
        raise TooLongError
    employed = set(working(on).values_list("id", flat=True))
    if any(row.employee.pk not in employed for row in rows):
        raise NotEmployedError
    existing = {a.employee_id: a for a in lock_rows(Attendance.objects.filter(on=on))}
    changed = 0
    for row in rows:
        current = existing.get(row.employee.pk)
        if current is None and row.status == Attendance.Status.PRESENT and not row.note:
            continue
        if current is not None and (current.status, current.note) == (row.status, row.note):
            continue
        before = current.status if current else None
        target = current or Attendance(employee=row.employee, on=on)
        target.status, target.note = row.status, row.note
        try:
            with transaction.atomic():
                target.save()
        except IntegrityError as exc:
            raise HrError from exc
        audit.record(
            Action.UPDATE if current else Action.CREATE,
            target,
            actor,
            {"status": [before, row.status]},
        )
        changed += 1
    return changed
