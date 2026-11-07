"""Employees, departments, salary structures and contracts. Every change writes an audit row.

Contracts for one employee must not overlap. Saving one locks that employee's row first, so two
contracts saved at once for the same person queue up and the second sees the first.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet

from apps.accounts.models import User
from apps.core.payroll import Breakdown, Component, PayrollError, breakdown, value
from apps.inventory import services as inventory
from apps.platform.locking import lock_rows
from apps.tenancy import audit
from apps.tenancy.models import AuditEvent

from .models import Contract, Employee, SalaryComponent, SalaryStructure

Action = AuditEvent.Action
MAX_COMPONENTS = 30


class HrError(Exception):
    message = "That can't be saved."


class OverlapError(HrError):
    message = "This person already has a contract for some of those dates. End it first."


class BadComponentError(HrError):
    message = "Give each part a name and either a fixed amount or a percentage of basic, not both."


class TooManyComponentsError(HrError):
    message = f"A salary structure can have at most {MAX_COMPONENTS} parts."


class DuplicateNameError(HrError):
    message = "There is already a salary structure with that name."


class InactiveStructureError(HrError):
    message = "That salary structure is switched off. Switch it on or pick another."


class DeductionsTooLargeError(HrError):
    message = "With this basic salary the deductions come to more than the pay."


# Departments and employees reuse the audited master-data helpers of inventory.
save_department = inventory.save_master
delete_department = inventory.delete_master
save_employee = inventory.save_master
delete_employee = inventory.delete_master


@dataclass(frozen=True)
class ComponentInput:
    name: str
    kind: str
    amount: Decimal | None
    percent: Decimal | None
    taxable: bool = True


def _check(rows: list[ComponentInput]) -> None:
    """Each part needs a name and exactly one of a fixed amount or a percentage of basic."""
    if len(rows) > MAX_COMPONENTS:
        raise TooManyComponentsError
    for row in rows:
        if not row.name.strip():
            raise BadComponentError
        try:
            value(Component(row.name, row.kind, row.amount, row.percent), Decimal(0))
        except PayrollError as exc:
            raise BadComponentError from exc


@transaction.atomic
def save_structure(
    actor: User,
    values: dict[str, Any],
    components: list[ComponentInput],
    structure: SalaryStructure | None = None,
) -> SalaryStructure:
    _check(components)
    target = structure or SalaryStructure()
    creating = target.pk is None
    before = {
        "name": target.name,
        "parts": [c.name for c in target.components.all()] if target.pk else [],
    }
    for key in ("name", "note", "is_active"):
        if key in values:
            setattr(target, key, values[key])
    try:
        with transaction.atomic():
            target.save()
    except IntegrityError as exc:
        raise DuplicateNameError from exc
    target.components.all().delete()
    SalaryComponent.objects.bulk_create(
        SalaryComponent(
            tenant_id=target.tenant_id,
            structure=target,
            name=row.name.strip(),
            kind=row.kind,
            amount=row.amount,
            percent=row.percent,
            taxable=row.taxable,
            position=index,
        )
        for index, row in enumerate(components)
    )
    after = {"name": target.name, "parts": [row.name.strip() for row in components]}
    changes = {
        k: [None if creating else before[k], after[k]]
        for k in after
        if creating or before[k] != after[k]
    }
    audit.record(Action.CREATE if creating else Action.UPDATE, target, actor, changes)
    return target


delete_structure = inventory.delete_master


def structure_breakdown(structure: SalaryStructure, basic: Decimal) -> Breakdown:
    parts = [
        Component(c.name, c.kind, c.amount, c.percent, c.taxable)
        for c in structure.components.all()
    ]
    try:
        return breakdown(basic, parts)
    except PayrollError as exc:
        raise DeductionsTooLargeError from exc


def _overlapping(employee: Employee, starts: date, ends: date | None) -> QuerySet[Contract]:
    """Contracts sharing at least one day with [starts, ends]; an empty end runs for ever."""
    query = Contract.objects.filter(employee=employee).filter(
        Q(ends_on__isnull=True) | Q(ends_on__gte=starts)
    )
    if ends is not None:
        query = query.filter(starts_on__lte=ends)
    return query


@transaction.atomic
def save_contract(
    actor: User, values: dict[str, Any], contract: Contract | None = None
) -> Contract:
    target = contract or Contract()
    employee: Employee = values.get("employee") or target.employee
    lock_rows(Employee.objects.filter(pk=employee.pk))
    starts = values.get("starts_on", target.starts_on)
    ends = values.get("ends_on", target.ends_on)
    clash = _overlapping(employee, starts, ends)
    if target.pk is not None:
        clash = clash.exclude(pk=target.pk)
    if clash.exists():
        raise OverlapError
    structure: SalaryStructure = values.get("structure") or target.structure
    changed_structure = target.pk is None or structure.pk != target.structure_id
    if changed_structure and not structure.is_active:
        raise InactiveStructureError
    structure_breakdown(structure, values.get("basic_salary", target.basic_salary))
    saved: Contract = inventory.save_master(actor, target, values)
    return saved


def delete_contract(actor: User, contract: Contract) -> None:
    inventory.delete_master(actor, contract)


def current_contract(employee: Employee, on: date) -> Contract | None:
    return (
        Contract.objects.filter(employee=employee, starts_on__lte=on)
        .filter(Q(ends_on__isnull=True) | Q(ends_on__gte=on))
        .select_related("structure")
        .first()
    )
