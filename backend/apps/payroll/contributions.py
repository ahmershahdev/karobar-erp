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
from apps.core.payroll import Breakdown, Component, with_deductions
from apps.core.payroll import value as part_value
from apps.hr.models import Contract, Employee, Province, SalaryComponent
from apps.platform.locking import lock_rows
from apps.tenancy import audit
from apps.tenancy.models import AuditEvent

from .models import ContributionRate, MinimumWage
from .services import PayrollError, lock_business

Action = AuditEvent.Action
OFFICIAL = Path(__file__).parent / "data" / "contributions.json"
Scheme = ContributionRate.Scheme
# The payslip line each scheme's staff share shows as.
AppliesTo = ContributionRate.AppliesTo
LINE_NAMES: dict[str, str] = {
    Scheme.EOBI: "EOBI",
    Scheme.SOCIAL_SECURITY: "Social security",
    Scheme.GOSI_ANNUITIES: "GOSI annuities",
    Scheme.GOSI_SANED: "GOSI SANED",
    Scheme.GOSI_HAZARDS: "GOSI occupational hazards",
    Scheme.GPSSA: "Pension (GPSSA)",
}
# The schemes each Gulf country's payroll owes, by nationality instead of a switch per person.
GULF_SCHEMES: dict[str, list[str]] = {
    "SA": [Scheme.GOSI_ANNUITIES, Scheme.GOSI_SANED, Scheme.GOSI_HAZARDS],
    "AE": [Scheme.GPSSA],
}


class BadRateError(PayrollError):
    message = (
        "Check the rate: percentages are 0 to 100, a ceiling and a floor are more than zero, "
        "the floor isn't above the ceiling, and a rate on the minimum wage has neither."
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
    return Rate(
        row.employer_percent,
        row.employee_percent,
        row.on_minimum_wage,
        row.wage_cap,
        row.wage_floor,
    )


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
            "on_insurable",
            "wage_cap",
            "wage_floor",
            "applies_to",
            "first_insured_from",
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
        # The unique index can't catch this one: MySQL lets rows with no first-insured date
        # repeat. Under the business lock, so two saves can't both pass.
        same = ContributionRate.objects.filter(
            scheme=row.scheme,
            province=row.province,
            applies_to=row.applies_to,
            first_insured_from=row.first_insured_from,
            starts_on=row.starts_on,
        )
        if row.pk is not None:
            same = same.exclude(pk=row.pk)
        if same.exists():
            raise DuplicateError
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


@dataclass(frozen=True)
class _Row:
    scheme: str
    province: str
    applies_to: str
    first_insured_from: date | None
    on_insurable: bool
    rate: Rate


def insurable_wage(contract: Contract) -> Decimal:
    """A full month of the basic salary and the earnings marked as counting for social
    insurance. GOSI and the UAE pension charge on this registered wage, whatever the days."""
    total = contract.basic_salary
    for part in contract.structure.components.all():
        if part.kind == SalaryComponent.Kind.EARNING and part.insurable:
            item = Component(part.name, part.kind, part.amount, part.percent, part.taxable)
            total += part_value(item, contract.basic_salary)
    return Decimal(total)


class Book:
    """The rates and minimum wages for one month, read once for everyone on the payroll.

    Pakistan's schemes go by each person's two switches and province. The Gulf's go by
    nationality against the business's country, and for GOSI by when the person was first
    insured; a Gulf scheme with no rate entered is simply not charged.
    """

    def __init__(self, first_day: date, country: str = "PK") -> None:
        self.country = country
        latest: dict[tuple[str, str, str, date | None], _Row] = {}
        for row in ContributionRate.objects.filter(starts_on__lte=first_day).order_by("starts_on"):
            # Ordered by start, so the latest rate of each group wins.
            key = (row.scheme, row.province, row.applies_to, row.first_insured_from)
            latest[key] = _Row(
                row.scheme,
                row.province,
                row.applies_to,
                row.first_insured_from,
                row.on_insurable,
                _rate(row),
            )
        self.rows = list(latest.values())
        self.wages: dict[str, Decimal] = {}
        for wage in MinimumWage.objects.filter(starts_on__lte=first_day).order_by("starts_on"):
            self.wages[wage.province] = wage.amount
        self.missing: set[str] = set()
        self.no_province: list[str] = []

    def _best(self, scheme: str, person: Employee, province: str = "") -> _Row | None:
        national = person.nationality == self.country
        insured = person.insured_since or person.joined_on
        matches = [
            row
            for row in self.rows
            if row.scheme == scheme
            and row.province in ("", province)
            and row.applies_to
            in (AppliesTo.ALL, AppliesTo.NATIONALS if national else AppliesTo.OTHERS)
            and (row.first_insured_from is None or insured >= row.first_insured_from)
        ]
        if not matches:
            return None
        # The most particular one wins: its own province, then its own group, then the latest
        # first-insured date that still covers the person.
        return max(
            matches,
            key=lambda row: (
                row.province == province,
                row.applies_to != AppliesTo.ALL,
                row.first_insured_from or date.min,
            ),
        )

    def _share(self, row: _Row, pay: Decimal, insurable: Decimal, wage: Decimal | None) -> Share:
        return contribution(row.rate, insurable if row.on_insurable else pay, wage)

    def for_person(
        self, person: Employee, pay: Decimal, insurable: Decimal | None = None
    ) -> list[Contribution]:
        """What the person and the business owe this month. Gaps are collected rather than
        raised, so one message can name every missing figure; call `check` afterwards."""
        base = pay if insurable is None else insurable
        if self.country in GULF_SCHEMES:
            found: list[Contribution] = []
            for scheme in GULF_SCHEMES[self.country]:
                row = self._best(scheme, person)
                if row is not None:
                    found.append(Contribution(scheme, row.rate, self._share(row, pay, base, None)))
            return found
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
        owed: list[Contribution] = []
        for scheme in schemes:
            row = self._best(scheme, person, person.province)
            if row is None:
                self.missing.add(f"{LINE_NAMES[scheme]} rate in {place}")
                continue
            wage = self.wages.get(person.province)
            if row.rate.on_minimum_wage and wage is None:
                self.missing.add(f"minimum wage in {place}")
                continue
            owed.append(Contribution(scheme, row.rate, self._share(row, pay, base, wage)))
        return owed

    def deduct(
        self, person: Employee, pay: Breakdown, insurable: Decimal | None = None
    ) -> tuple[Breakdown, list[Contribution]]:
        """The pay with the person's share taken off as deduction lines, and what is owed.
        Raises the pay maths error when the share leaves less than nothing."""
        owed = self.for_person(person, pay.gross, insurable)
        shares = [(LINE_NAMES[c.scheme], c.share.employee) for c in owed if c.share.employee]
        return with_deductions(pay, shares), owed

    def check(self) -> None:
        if self.no_province:
            raise NoProvinceError(*self.no_province)
        if self.missing:
            raise MissingRateError(*sorted(self.missing))
