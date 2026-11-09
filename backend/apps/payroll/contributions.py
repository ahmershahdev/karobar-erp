"""EOBI and provincial social security: the rates and minimum wages a payroll run needs, kept as
data with their source and editable by the owner.

Only figures read from an official notification ship in data/contributions.json. The others
(EOBI's percentages, each province's social security rate and ceiling, minimum wages not yet
notified for the year) are entered by the business from its own challan or notification.
"""

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.db import IntegrityError, transaction

from apps.accounts.models import User
from apps.core.contributions import ContributionError, Rate, Share, check_rate, contribution
from apps.core.payroll import Breakdown, with_deductions
from apps.hr.models import Employee, Province
from apps.platform.locking import lock_rows
from apps.tenancy import audit
from apps.tenancy.models import AuditEvent

from .models import ContributionRate, MinimumWage
from .services import PayrollError, lock_business

Action = AuditEvent.Action
OFFICIAL = Path(__file__).parent / "data" / "contributions.json"
Scheme = ContributionRate.Scheme
# The payslip line each scheme's staff share shows as.
LINE_NAMES: dict[str, str] = {Scheme.EOBI: "EOBI", Scheme.SOCIAL_SECURITY: "Social security"}


class BadRateError(PayrollError):
    message = (
        "Check the rate: percentages are 0 to 100, a ceiling is more than zero, and a rate on "
        "the minimum wage has no ceiling."
    )


class DuplicateError(PayrollError):
    message = "There is already one starting on that day. Change that one instead."


class NoProvinceError(PayrollError):
    message = (
        "These people pay EOBI or social security but have no province. Choose where they work "
        "on the Employees screen:"
    )


class MissingRateError(PayrollError):
    message = (
        "A rate or a minimum wage this month needs is missing. Add it on the Contributions screen:"
    )


def _check(rate: ContributionRate) -> None:
    try:
        check_rate(_rate(rate))
    except ContributionError as exc:
        raise BadRateError from exc


def _rate(row: ContributionRate) -> Rate:
    return Rate(row.employer_percent, row.employee_percent, row.on_minimum_wage, row.wage_cap)


def _fields(row: ContributionRate | MinimumWage) -> dict[str, str]:
    names = (
        ["province", "starts_on", "amount", "source"]
        if isinstance(row, MinimumWage)
        else [
            "scheme",
            "province",
            "starts_on",
            "employer_percent",
            "employee_percent",
            "on_minimum_wage",
            "wage_cap",
            "source",
        ]
    )
    return {name: str(getattr(row, name)) for name in names}


@transaction.atomic
def save(
    actor: User | None, row: ContributionRate | MinimumWage, values: dict[str, Any]
) -> ContributionRate | MinimumWage:
    lock_business()
    if row.pk is not None:
        row = lock_rows(type(row).objects.filter(pk=row.pk))[0]
    creating = row.pk is None
    before = {} if creating else _fields(row)
    for key, value in values.items():
        setattr(row, key, value)
    if isinstance(row, ContributionRate):
        _check(row)
    try:
        with transaction.atomic():
            row.save()
    except IntegrityError as exc:
        raise DuplicateError from exc
    after = _fields(row)
    changes = {k: [before.get(k), v] for k, v in after.items() if before.get(k) != v}
    audit.record(Action.CREATE if creating else Action.UPDATE, row, actor, changes)
    return row


@transaction.atomic
def delete(actor: User, row: ContributionRate | MinimumWage) -> None:
    lock_business()
    locked = lock_rows(type(row).objects.filter(pk=row.pk))[0]
    audit.record(Action.DELETE, locked, actor, {"starts_on": [str(locked.starts_on), None]})
    locked.delete()


def official() -> dict[str, list[dict[str, Any]]]:
    data: dict[str, list[dict[str, Any]]] = json.loads(OFFICIAL.read_text(encoding="utf-8"))
    return data


@transaction.atomic
def fill_official(actor: User) -> int:
    """Add the shipped figures the business doesn't have yet. A row it already has for the same
    start is left alone, so a figure the business corrected stays corrected."""
    data = official()
    added = 0
    for entry in data["minimum_wages"]:
        starts = date.fromisoformat(entry["starts_on"])
        if MinimumWage.objects.filter(province=entry["province"], starts_on=starts).exists():
            continue
        values = {**entry, "starts_on": starts, "amount": Decimal(entry["amount"])}
        save(actor, MinimumWage(), values)
        added += 1
    for entry in data["rates"]:
        starts = date.fromisoformat(entry["starts_on"])
        same = ContributionRate.objects.filter(
            scheme=entry["scheme"], province=entry["province"], starts_on=starts
        )
        if same.exists():
            continue
        values = {**entry, "starts_on": starts}
        for key in ("employer_percent", "employee_percent", "wage_cap"):
            if values.get(key) is not None:
                values[key] = Decimal(values[key])
        save(actor, ContributionRate(), values)
        added += 1
    return added


@dataclass(frozen=True)
class Contribution:
    scheme: str
    rate: Rate
    share: Share

    def as_json(self) -> dict[str, str]:
        return {
            "scheme": self.scheme,
            "base": str(self.share.base),
            "employer_percent": str(self.rate.employer),
            "employee_percent": str(self.rate.employee),
            "employer": str(self.share.employer),
            "employee": str(self.share.employee),
        }


class Book:
    """The rates and minimum wages for one month, read once for everyone on the payroll."""

    def __init__(self, first_day: date) -> None:
        self.rates: dict[tuple[str, str], Rate] = {}
        for row in ContributionRate.objects.filter(starts_on__lte=first_day).order_by("starts_on"):
            # Ordered by start, so the latest rate for each scheme and province wins.
            self.rates[(row.scheme, row.province)] = _rate(row)
        self.wages: dict[str, Decimal] = {}
        for wage in MinimumWage.objects.filter(starts_on__lte=first_day).order_by("starts_on"):
            self.wages[wage.province] = wage.amount
        self.missing: set[str] = set()
        self.no_province: list[str] = []

    def _rate_for(self, scheme: str, province: str) -> Rate | None:
        return self.rates.get((scheme, province)) or self.rates.get((scheme, ""))

    def for_person(self, person: Employee, pay: Decimal) -> list[Contribution]:
        """What the person and the business owe this month. Gaps are collected rather than
        raised, so one message can name every missing figure; call `check` afterwards."""
        schemes = [
            scheme
            for scheme, on in (
                (Scheme.EOBI, person.pays_eobi),
                (Scheme.SOCIAL_SECURITY, person.pays_social_security),
            )
            if on
        ]
        if not schemes:
            return []
        if not person.province:
            self.no_province.append(person.code)
            return []
        place = Province(person.province).label
        found: list[Contribution] = []
        for scheme in schemes:
            rate = self._rate_for(scheme, person.province)
            if rate is None:
                self.missing.add(f"{LINE_NAMES[scheme]} rate in {place}")
                continue
            wage = self.wages.get(person.province)
            if rate.on_minimum_wage and wage is None:
                self.missing.add(f"minimum wage in {place}")
                continue
            found.append(Contribution(scheme, rate, contribution(rate, pay, wage)))
        return found

    def deduct(self, person: Employee, pay: Breakdown) -> tuple[Breakdown, list[Contribution]]:
        """The pay with the person's share taken off as deduction lines, and what is owed.
        Raises the pay maths error when the share leaves less than nothing."""
        owed = self.for_person(person, pay.gross)
        shares = [(LINE_NAMES[c.scheme], c.share.employee) for c in owed if c.share.employee]
        return with_deductions(pay, shares), owed

    def check(self) -> None:
        if self.no_province:
            raise NoProvinceError(*self.no_province)
        if self.missing:
            raise MissingRateError(*sorted(self.missing))
