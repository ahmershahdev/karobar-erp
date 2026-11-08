"""Salary tax tables: kept as data per tax year, filled in from the law, editable by the owner.

The official figures ship in data/tax_tables.json with the law and the page they were read from.
A business can add a year, correct one, or fill in the shipped ones; a table that posted payroll
used stays as it is, so the books can always show how a payslip's tax was reached.
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.db import transaction

from apps.accounts.models import User
from apps.core.salary_tax import SalaryTaxError, Slab, check_slabs
from apps.hr.time_off import COUNTRIES, settings_for
from apps.platform.locking import lock_rows
from apps.tenancy import audit
from apps.tenancy.models import AuditEvent

from .models import PayrollRun, TaxSlab, TaxTable

Action = AuditEvent.Action
OFFICIAL = Path(__file__).parent / "data" / "tax_tables.json"
# The month each country's tax year starts. Countries missing here have no tax on salaries.
TAX_YEAR_STARTS = {"PK": 7}


class PayrollError(Exception):
    message = "Payroll could not do that."


class BadSlabsError(PayrollError):
    message = (
        "Check the slabs: the first starts at 0, each starts above the one before, and rates "
        "are 0 to 100."
    )


class BadCountryError(PayrollError):
    message = "Tax tables can be kept for Pakistan, the UAE and Saudi Arabia."


class BadDatesError(PayrollError):
    message = "A tax year ends after it starts."


class TableOverlapError(PayrollError):
    message = "Another tax table already covers some of those dates. Change its dates first."


class TableInUseError(PayrollError):
    message = "Posted payroll used this table, so it stays as it is. Add a new table instead."


def slabs_of(table: TaxTable) -> list[Slab]:
    return [Slab(s.over, s.fixed, s.rate) for s in table.slabs.all()]


def table_for(country: str, on: date) -> TaxTable | None:
    """The table covering `on`, locked until the transaction ends, so save_table and
    delete_table wait while a payroll run reads and uses its slabs."""
    locked = lock_rows(
        TaxTable.objects.filter(country=country, starts_on__lte=on, ends_on__gte=on)
    )
    if not locked:
        return None
    found: TaxTable | None = (
        TaxTable.objects.filter(pk=locked[0].pk).prefetch_related("slabs").first()
    )
    return found


def _used(table: TaxTable) -> bool:
    return PayrollRun.objects.filter(tax_table=table, status=PayrollRun.Status.POSTED).exists()


@transaction.atomic
def save_table(
    actor: User | None,
    values: dict[str, Any],
    slabs: list[Slab],
    table: TaxTable | None = None,
) -> TaxTable:
    target: TaxTable = table or TaxTable()
    if target.pk is not None:
        target = lock_rows(TaxTable.objects.filter(pk=target.pk))[0]
        if _used(target):
            raise TableInUseError
    country = values.get("country", target.country)
    if country not in COUNTRIES:
        raise BadCountryError
    try:
        check_slabs(slabs)
    except SalaryTaxError as exc:
        raise BadSlabsError from exc
    starts = values.get("starts_on", target.starts_on)
    ends = values.get("ends_on", target.ends_on)
    if ends < starts:
        raise BadDatesError
    clash = TaxTable.objects.filter(country=country, starts_on__lte=ends, ends_on__gte=starts)
    if target.pk is not None:
        clash = clash.exclude(pk=target.pk)
    if clash.exists():
        raise TableOverlapError
    creating = target.pk is None
    before = {"name": target.name, "starts_on": str(target.starts_on), "slabs": _text(target)}
    for key, value in values.items():
        setattr(target, key, value)
    target.save()
    target.slabs.all().delete()
    TaxSlab.objects.bulk_create(
        [
            TaxSlab(tenant=target.tenant, table=target, over=s.over, fixed=s.fixed, rate=s.rate)
            for s in slabs
        ]
    )
    after = {"name": target.name, "starts_on": str(target.starts_on), "slabs": _text(target)}
    changes = {k: [None if creating else before[k], after[k]] for k in after}
    audit.record(Action.CREATE if creating else Action.UPDATE, target, actor, changes)
    return target


def _text(table: TaxTable) -> str:
    if table.pk is None:
        return ""
    return "; ".join(f"{s.over} {s.fixed} {s.rate}%" for s in table.slabs.all())


@transaction.atomic
def delete_table(actor: User, table: TaxTable) -> None:
    locked: TaxTable = lock_rows(TaxTable.objects.filter(pk=table.pk))[0]
    if PayrollRun.objects.filter(tax_table=locked).exists():
        raise TableInUseError
    audit.record(Action.DELETE, locked, actor, {"name": [locked.name, None]})
    locked.delete()


def official_tables(country: str) -> list[dict[str, Any]]:
    data: dict[str, list[dict[str, Any]]] = json.loads(OFFICIAL.read_text(encoding="utf-8"))
    return data.get(country, [])


@transaction.atomic
def fill_official(actor: User) -> int:
    """Add the shipped tables for the business's country. Years it already has are left alone,
    so a table the business corrected stays corrected."""
    country = settings_for().holiday_country
    added = 0
    for entry in official_tables(country):
        starts, ends = date.fromisoformat(entry["starts_on"]), date.fromisoformat(entry["ends_on"])
        if TaxTable.objects.filter(country=country, starts_on__lte=ends, ends_on__gte=starts):
            continue
        slabs = [Slab(Decimal(o), Decimal(f), Decimal(r)) for o, f, r in entry["slabs"]]
        values = {
            "country": country,
            "name": entry["name"],
            "starts_on": starts,
            "ends_on": ends,
            "source": entry["source"],
        }
        save_table(actor, values, slabs)
        added += 1
    return added
