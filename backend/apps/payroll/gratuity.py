"""End-of-service gratuity in the UAE and Saudi Arabia: the rules as data, the provision built up
by each month's payroll, and the payout when someone leaves.

Every posted month books the change in each person's gratuity so far, worked out as if they left
at the month's end with the full award (apps/core/gratuity.py). When they do leave, the payout
uses that provision up and books any difference, such as the part a Saudi worker gives up by
resigning early.
"""

import json
from datetime import date
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Sum

from apps.accounting import services as accounting
from apps.accounting.models import Account
from apps.accounts.models import User
from apps.core import posting
from apps.core.balances import AccountType
from apps.core.gratuity import Award, Band, GratuityError, Rule, award, check_rule
from apps.core.payroll import Component, breakdown
from apps.hr.models import Contract, Employee
from apps.hr.time_off import settings_for
from apps.platform.locking import lock_rows
from apps.tenancy import audit
from apps.tenancy.models import AuditEvent

from .models import GratuityPayout, GratuityRule, PayrollRun, Payslip
from .services import PayrollError, lock_business

Action = AuditEvent.Action
OFFICIAL = Path(__file__).parent / "data" / "gratuity.json"
# Countries whose labour law gives an end-of-service gratuity that payroll builds up.
GRATUITY_COUNTRIES = {"AE", "SA"}
ZERO = Decimal(0)


class BadRuleError(PayrollError):
    message = (
        "Check the rule: figures can't be negative, a cap is more than zero, and resignation "
        "shares rise from 0 to 1 with service."
    )


class DuplicateRuleError(PayrollError):
    message = "There is already a rule for that country starting on that day. Change it instead."


class RuleInUseError(PayrollError):
    message = "A gratuity was paid under this rule, so it stays. Add a new rule from a later day."


class NoRuleError(PayrollError):
    message = (
        "There is no end-of-service rule for this month. Fill it in on the End of service "
        "screen first."
    )


class NotLeftError(PayrollError):
    message = "Set the day this person left on the Employees screen first."


class LastMonthNotPostedError(PayrollError):
    message = (
        "Post the payroll for the month this person left first, so their gratuity is up to date."
    )


class AlreadyPaidError(PayrollError):
    message = "This person's end-of-service gratuity is already paid."


class BadAccountError(PayrollError):
    message = "Choose an active cash or bank account that is not a group."


class TooEarlyError(PayrollError):
    message = "The gratuity can't be paid before the day the person left."


class NotDueError(PayrollError):
    message = "No end-of-service gratuity is due here for this person."


def _share(text: str) -> Decimal:
    fraction = Fraction(text)
    return Decimal(fraction.numerator) / Decimal(fraction.denominator)


def as_rule(row: GratuityRule) -> Rule:
    try:
        bands = tuple(
            Band(Decimal(b["years"]), _share(b["share"]), bool(b.get("after", False)))
            for b in row.resignation
        )
    except (KeyError, TypeError, ValueError, ZeroDivisionError, ArithmeticError) as exc:
        raise BadRuleError from exc
    return Rule(
        row.first_years,
        row.first_days,
        row.later_days,
        row.month_days,
        row.min_years,
        row.cap_months,
        bands,
    )


def rule_for(country: str, on: date) -> GratuityRule | None:
    found: GratuityRule | None = (
        GratuityRule.objects.filter(country=country, starts_on__lte=on)
        .order_by("-starts_on")
        .first()
    )
    return found


def applies(row: GratuityRule, person: Employee, country: str) -> bool:
    return not (row.excludes_nationals and person.nationality == country)


def _fields(row: GratuityRule) -> dict[str, str]:
    names = [
        "country",
        "starts_on",
        "first_years",
        "first_days",
        "later_days",
        "month_days",
        "min_years",
        "cap_months",
        "wage",
        "excludes_nationals",
        "excludes_unpaid_days",
        "source",
    ]
    fields = {name: str(getattr(row, name)) for name in names}
    fields["resignation"] = json.dumps(row.resignation, sort_keys=True)
    return fields


@transaction.atomic
def save_rule(actor: User | None, row: GratuityRule, values: dict[str, Any]) -> GratuityRule:
    lock_business()
    if row.pk is not None:
        row = lock_rows(GratuityRule.objects.filter(pk=row.pk))[0]
    creating = row.pk is None
    before = {} if creating else _fields(row)
    for key, value in values.items():
        setattr(row, key, value)
    try:
        check_rule(as_rule(row))
    except GratuityError as exc:
        raise BadRuleError from exc
    try:
        with transaction.atomic():
            row.save()
    except IntegrityError as exc:
        raise DuplicateRuleError from exc
    after = _fields(row)
    changes = {k: [before.get(k), v] for k, v in after.items() if before.get(k) != v}
    audit.record(Action.CREATE if creating else Action.UPDATE, row, actor, changes)
    return row


@transaction.atomic
def delete_rule(actor: User, row: GratuityRule) -> None:
    lock_business()
    locked: GratuityRule = lock_rows(GratuityRule.objects.filter(pk=row.pk))[0]
    if GratuityPayout.objects.filter(rule=locked).exists():
        raise RuleInUseError
    audit.record(Action.DELETE, locked, actor, {"starts_on": [str(locked.starts_on), None]})
    locked.delete()


def official() -> dict[str, list[dict[str, Any]]]:
    data: dict[str, list[dict[str, Any]]] = json.loads(OFFICIAL.read_text(encoding="utf-8"))
    return data


@transaction.atomic
def fill_official(actor: User) -> int:
    """Add the shipped rule for the business's country if it has none from that day."""
    country = settings_for().holiday_country
    added = 0
    for entry in official().get(country, []):
        starts = date.fromisoformat(entry["starts_on"])
        if GratuityRule.objects.filter(country=country, starts_on=starts).exists():
            continue
        values = {**entry, "country": country, "starts_on": starts}
        for key in ("first_years", "first_days", "later_days", "month_days", "min_years"):
            values[key] = Decimal(values[key])
        if values["cap_months"] is not None:
            values["cap_months"] = Decimal(values["cap_months"])
        save_rule(actor, GratuityRule(), values)
        added += 1
    return added


def monthly_wage(row: GratuityRule, contract: Contract) -> Decimal:
    """The month's wage the award is counted in: the basic salary, or basic plus allowances."""
    if row.wage == GratuityRule.Wage.BASIC:
        return Decimal(contract.basic_salary)
    components = [
        Component(c.name, c.kind, c.amount, c.percent, c.taxable)
        for c in contract.structure.components.all()
    ]
    return breakdown(contract.basic_salary, components).gross


def service_days(person: Employee, until: date, unpaid_days: Decimal) -> int:
    """Calendar days from joining to `until`, both counted, less whole unpaid days."""
    days = (until - person.joined_on).days + 1 - int(unpaid_days)
    return max(days, 0)


def unpaid_before(month: date) -> dict[int, Decimal]:
    """Each person's unpaid days in posted months before `month`."""
    return {
        row["employee_id"]: row["days"] or ZERO
        for row in Payslip.objects.filter(
            run__status=PayrollRun.Status.POSTED, run__month__lt=month
        )
        .values("employee_id")
        .annotate(days=Sum("unpaid_days"))
    }


def accrued_before(month: date) -> dict[int, Decimal]:
    """Each person's gratuity provision from their latest posted payslip before `month`."""
    found: dict[int, Decimal] = {}
    for employee_id, accrued in (
        Payslip.objects.filter(run__status=PayrollRun.Status.POSTED, run__month__lt=month)
        .order_by("employee_id", "run__month")
        .values_list("employee_id", "gratuity_accrued")
    ):
        found[employee_id] = accrued
    return found


def built_up(
    row: GratuityRule,
    person: Employee,
    contract: Contract,
    until: date,
    unpaid_days: Decimal,
    resigned: bool = False,
) -> tuple[int, Decimal, Award]:
    days = service_days(person, until, unpaid_days if row.excludes_unpaid_days else ZERO)
    wage = monthly_wage(row, contract)
    return days, wage, award(as_rule(row), days, wage, resigned)


def _last_contract(person: Employee, on: date) -> Contract | None:
    found: Contract | None = (
        Contract.objects.filter(employee=person, starts_on__lte=on)
        .select_related("structure")
        .prefetch_related("structure__components")
        .order_by("-starts_on")
        .first()
    )
    return found


@transaction.atomic
def settle(actor: User, person: Employee, data: dict[str, Any]) -> GratuityPayout:
    """Pay a leaver's gratuity from a cash or bank account, once."""
    lock_business()
    locked: Employee = lock_rows(Employee.objects.filter(pk=person.pk))[0]
    if locked.left_on is None:
        raise NotLeftError
    if GratuityPayout.objects.filter(employee=locked).exists():
        raise AlreadyPaidError
    country = settings_for().holiday_country
    row = rule_for(country, locked.left_on)
    if row is None:
        raise NoRuleError
    if not applies(row, locked, country):
        raise NotDueError
    last_month = locked.left_on.replace(day=1)
    posted = Payslip.objects.filter(employee=locked, run__status=PayrollRun.Status.POSTED)
    if not posted.filter(run__month=last_month).exists():
        raise LastMonthNotPostedError
    paid_on: date = data["paid_on"]
    if paid_on < locked.left_on:
        raise TooEarlyError
    source: Account = data["paid_from"]
    if source.type != AccountType.ASSET or source.is_group or not source.is_active:
        raise BadAccountError
    contract = _last_contract(locked, locked.left_on)
    if contract is None:
        raise NotDueError
    resigned = data["reason"] == GratuityPayout.Reason.RESIGNED
    unpaid = posted.aggregate(days=Sum("unpaid_days"))["days"] or ZERO
    days, wage, result = built_up(row, locked, contract, locked.left_on, unpaid, resigned)
    provision = accrued_before(_after(last_month)).get(locked.pk, ZERO)
    entry = accounting.post_rule_lines(
        actor,
        paid_on,
        f"End-of-service gratuity {locked.code}",
        posting.gratuity_payout(result.amount, provision, out_of="paid_from"),
        {"paid_from": source},
        ("gratuity_payout", str(locked.pk)),
    )
    payout: GratuityPayout = GratuityPayout.objects.create(
        employee=locked,
        rule=row,
        reason=data["reason"],
        service_days=days,
        wage=wage,
        full=result.full,
        share=result.share.quantize(Decimal("0.000001")),
        amount=result.amount,
        provision=provision,
        paid_on=paid_on,
        paid_from=source,
        entry=entry,
        paid_by=actor,
    )
    audit.record(
        Action.POST,
        payout,
        actor,
        {"amount": [None, str(payout.amount)], "reason": [None, payout.reason]},
    )
    return payout


def _after(month: date) -> date:
    """The first day of the month after `month`."""
    return date(month.year + month.month // 12, month.month % 12 + 1, 1)


def quote(person: Employee) -> dict[str, Any]:
    """What the person's gratuity has built up to on their latest posted payslip, and for
    someone who left and isn't paid yet, what each reason for leaving would pay."""
    posted = Payslip.objects.filter(employee=person, run__status=PayrollRun.Status.POSTED)
    latest = posted.order_by("-run__month").first()
    payout = GratuityPayout.objects.filter(employee=person).first()
    found: dict[str, Any] = {
        "accrued": latest.gratuity_accrued if latest else ZERO,
        "service_days": None,
        "if_ended": None,
        "if_resigned": None,
        "payout": payout,
    }
    if person.left_on is None or payout is not None:
        return found
    country = settings_for().holiday_country
    row = rule_for(country, person.left_on)
    contract = _last_contract(person, person.left_on)
    if row is None or contract is None or not applies(row, person, country):
        return found
    unpaid = posted.aggregate(days=Sum("unpaid_days"))["days"] or ZERO
    days, _, ended = built_up(row, person, contract, person.left_on, unpaid)
    _, _, resigned = built_up(row, person, contract, person.left_on, unpaid, resigned=True)
    found.update(service_days=days, if_ended=ended.amount, if_resigned=resigned.amount)
    return found
