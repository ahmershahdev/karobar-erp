"""Every write to the books goes through here: atomic, validated by apps.core, and audited."""

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.db import IntegrityError, models, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.core import posting
from apps.core.journal import Line, UnbalancedEntryError, validate_lines
from apps.core.money import quantize_money
from apps.core.periods import fiscal_year_containing, monthly_periods
from apps.platform.locking import lock_rows
from apps.tenancy import audit
from apps.tenancy.models import AuditEvent, Tenant

from .models import (
    Account,
    FiscalPeriod,
    FiscalYear,
    JournalEntry,
    JournalLine,
    NumberSeries,
    TaxRate,
)

CHARTS = Path(__file__).parent / "charts"
JOURNAL_SERIES = ("JV", "JV-")
Action = AuditEvent.Action


class AccountingError(Exception):
    """A rule of the books was broken. Subclasses carry a fixed message the API can show."""

    message = "That isn't allowed by the books."


class UnbalancedError(AccountingError):
    message = "Debits and credits must be equal, with at least two lines and one side per line."


class NoOpenPeriodError(AccountingError):
    message = "The entry date isn't in an open fiscal period."


class AccountNotPostableError(AccountingError):
    message = "Entries can only go to active accounts that are not groups."


class AlreadyPostedError(AccountingError):
    message = "This entry is already posted."


class NotPostedError(AccountingError):
    message = "Only posted entries can be reversed."


class AlreadyReversedError(AccountingError):
    message = "This entry has already been reversed."


class DuplicateCodeError(AccountingError):
    message = "An account with this code or role already exists."


class OverlappingYearError(AccountingError):
    message = "This fiscal year overlaps an existing one."


class HierarchyLoopError(AccountingError):
    message = "An account can't sit under itself or one of its own accounts."


class AccountInUseError(AccountingError):
    message = "This account has entries or child accounts, so it can't be deleted."


@dataclass(frozen=True)
class LineInput:
    account: Account
    debit: Decimal
    credit: Decimal
    description: str = ""


# Setup


@transaction.atomic
def install_chart(tenant: Tenant, actor: User | None, template: str = "standard") -> int:
    data = json.loads((CHARTS / f"{template}.json").read_text(encoding="utf-8"))
    created: dict[str, Account] = {}
    for row in data["accounts"]:
        account: Account = Account.objects.create(
            code=row["code"],
            name=row["name"],
            type=row["type"],
            is_group=row.get("group", False),
            role=row.get("role"),
            parent=created.get(row.get("parent", "")),
        )
        created[account.code] = account
    NumberSeries.objects.get_or_create(
        key=JOURNAL_SERIES[0], defaults={"prefix": JOURNAL_SERIES[1]}
    )
    audit.record(Action.CREATE, tenant, actor, {"chart": [None, data["name"]]})
    return len(created)


@transaction.atomic
def create_fiscal_year(actor: User | None, start: date, end: date, name: str = "") -> FiscalYear:
    if FiscalYear.objects.filter(start__lte=end, end__gte=start).exists():
        raise OverlappingYearError
    year: FiscalYear = FiscalYear.objects.create(
        name=name
        or (
            f"FY {start.year}"
            if start.year == end.year
            else f"FY {start.year}-{end.year % 100:02d}"
        ),
        start=start,
        end=end,
    )
    for number, (period_start, period_end) in enumerate(monthly_periods(start, end), start=1):
        FiscalPeriod.objects.create(
            fiscal_year=year, number=number, start=period_start, end=period_end
        )
    audit.record(Action.CREATE, year, actor, {"name": [None, year.name]})
    return year


def create_current_fiscal_year(actor: User | None, start_month: int) -> FiscalYear:
    start, end = fiscal_year_containing(timezone.localdate(), start_month)
    return create_fiscal_year(actor, start, end)


@transaction.atomic
def set_period_closed(actor: User, period: FiscalPeriod, closed: bool) -> FiscalPeriod:
    before = period.closed_at is not None
    period.closed_at = timezone.now() if closed else None
    period.save(update_fields=["closed_at"])
    audit.record(Action.UPDATE, period, actor, {"closed": [before, closed]})
    return period


# Chart of accounts


def _check_no_loop(account: Account) -> None:
    # Lock the business row so hierarchy changes run one at a time per business; then walk the
    # new parent's ancestors as they are in the database. Two concurrent moves can't both pass.
    Tenant.objects.select_for_update().get(pk=account.tenant_id)
    seen: set[int] = set()
    parent_id = account.parent_id
    while parent_id is not None and parent_id not in seen:
        if parent_id == account.pk:
            raise HierarchyLoopError
        seen.add(parent_id)
        parent_id = (
            Account.objects.filter(pk=parent_id).values_list("parent_id", flat=True).first()
        )


@transaction.atomic
def save_account(actor: User, values: dict[str, Any], account: Account | None = None) -> Account:
    fields = ("code", "name", "type", "parent_id", "is_group", "is_active", "role")
    before = {f: getattr(account, f) for f in fields} if account else dict.fromkeys(fields)
    target = account or Account()
    for key, value in values.items():
        setattr(target, key, value)
    if "parent" in values and target.pk is not None:
        _check_no_loop(target)
    try:
        with transaction.atomic():
            target.save()
    except IntegrityError as exc:
        raise DuplicateCodeError from exc
    after = {f: getattr(target, f) for f in fields}
    changes = {k: [before[k], after[k]] for k in fields if before[k] != after[k]}
    audit.record(Action.UPDATE if account else Action.CREATE, target, actor, changes)
    return target


@transaction.atomic
def delete_account(actor: User, account: Account) -> None:
    if account.lines.exists() or account.children.exists():
        raise AccountInUseError
    audit.record(Action.DELETE, account, actor, {"code": [account.code, None]})
    account.delete()


# Journal entries


def _check_lines(lines: list[LineInput]) -> None:
    try:
        validate_lines([Line(str(line.account.pk), line.debit, line.credit) for line in lines])
    except UnbalancedEntryError as exc:
        raise UnbalancedError from exc


def _write_lines(entry: JournalEntry, lines: list[LineInput]) -> None:
    entry.lines.all().delete()
    JournalLine.objects.bulk_create(
        JournalLine(
            tenant=entry.tenant,
            entry=entry,
            account=line.account,
            debit=quantize_money(line.debit),
            credit=quantize_money(line.credit),
            description=line.description,
        )
        for line in lines
    )


def _locked_draft(entry: JournalEntry) -> JournalEntry:
    # The caller's copy may be stale: someone else could have posted the entry since it was
    # loaded. Lock the row and decide on what the database says now.
    locked: JournalEntry = lock_rows(JournalEntry.objects.filter(pk=entry.pk))[0]
    if locked.status == JournalEntry.Status.POSTED:
        raise AlreadyPostedError
    return locked


@transaction.atomic
def save_draft(
    actor: User,
    entry_date: date,
    memo: str,
    lines: list[LineInput],
    entry: JournalEntry | None = None,
) -> JournalEntry:
    """Drafts may be unbalanced while someone is still typing; posting is where balance is law."""
    target = _locked_draft(entry) if entry is not None else JournalEntry(created_by=actor)
    target.date, target.memo = entry_date, memo
    target.save()
    _write_lines(target, lines)
    audit.record(
        Action.UPDATE if entry else Action.CREATE,
        target,
        actor,
        {"date": [None, str(entry_date)], "lines": [None, len(lines)]},
    )
    return target


@transaction.atomic
def delete_draft(actor: User, entry: JournalEntry) -> None:
    draft = _locked_draft(entry)
    audit.record(Action.DELETE, draft, actor, {"memo": [draft.memo, None]})
    draft.delete()


def next_number(key: str, prefix: str) -> str:
    # The series row is locked until this transaction ends, so concurrent posts queue here and
    # each takes the next number. If the post rolls back, so does the increment: no gaps.
    series = NumberSeries.objects.filter(key=key)
    rows = lock_rows(series)
    if not rows:
        NumberSeries.objects.create(key=key, prefix=prefix)
        rows = lock_rows(series)
    counter = rows[0]
    number = f"{counter.prefix}{counter.next_number:06d}"
    counter.next_number += 1
    counter.save(update_fields=["next_number"])
    return number


@transaction.atomic
def post_entry(actor: User, entry: JournalEntry) -> JournalEntry:
    # Lock the entry first so two people pressing Post at once can't both post it.
    locked: JournalEntry = lock_rows(JournalEntry.objects.filter(pk=entry.pk))[0]
    if locked.status == JournalEntry.Status.POSTED:
        raise AlreadyPostedError
    lines = list(locked.lines.select_related("account"))
    _check_lines([LineInput(ln.account, ln.debit, ln.credit) for ln in lines])
    if any(ln.account.is_group or not ln.account.is_active for ln in lines):
        raise AccountNotPostableError
    # Locking the period row makes closing a period and posting into it mutually exclusive.
    periods = lock_rows(FiscalPeriod.objects.filter(start__lte=locked.date, end__gte=locked.date))
    if not periods or periods[0].closed_at is not None:
        raise NoOpenPeriodError
    locked.number = next_number(*JOURNAL_SERIES)
    locked.status = JournalEntry.Status.POSTED
    locked.posted_by = actor
    locked.posted_at = timezone.now()
    locked.save(update_fields=["number", "status", "posted_by", "posted_at"])
    audit.record(Action.POST, locked, actor, {"number": [None, locked.number]})
    return locked


@transaction.atomic
def reverse_entry(actor: User, entry: JournalEntry, on: date, memo: str = "") -> JournalEntry:
    original = lock_rows(JournalEntry.objects.filter(pk=entry.pk))[0]
    if original.status != JournalEntry.Status.POSTED:
        raise NotPostedError
    if JournalEntry.objects.filter(reversal_of=original).exists():
        raise AlreadyReversedError
    source = list(original.lines.select_related("account"))
    swapped = posting.reversal([Line(str(ln.pk), ln.debit, ln.credit) for ln in source])
    lines = [
        LineInput(line.account, flipped.debit, flipped.credit, line.description)
        for line, flipped in zip(source, swapped, strict=True)
    ]
    draft = save_draft(actor, on, memo or f"Reversal of {original.number}", lines)
    draft.reversal_of = original
    draft.save(update_fields=["reversal_of"])
    posted: JournalEntry = post_entry(actor, draft)
    return posted


class MissingRoleError(AccountingError):
    message = "The chart of accounts has no account for a role this posting needs."


def account_for_role(role: str) -> Account:
    found: Account | None = Account.objects.filter(role=role).first()
    if found is None:
        raise MissingRoleError
    return found


def post_rule_lines(
    actor: User,
    entry_date: date,
    memo: str,
    lines: list[Line],
    accounts: dict[str, Account],
    source: tuple[str, str],
) -> JournalEntry:
    """Turn apps.core posting-rule lines into a posted journal entry.

    Each line names an account role ("inventory") or a key in `accounts` for accounts the user
    chose (a contra account on a stock adjustment). Runs inside the caller's transaction, so the
    document, its stock moves and this entry commit or fail together.
    """
    resolved = [
        LineInput(
            accounts.get(line.account) or account_for_role(line.account), line.debit, line.credit
        )
        for line in lines
    ]
    draft = save_draft(actor, entry_date, memo, resolved)
    draft.source_type, draft.source_id = source
    draft.save(update_fields=["source_type", "source_id"])
    posted: JournalEntry = post_entry(actor, draft)
    return posted


class TaxRateInUseError(AccountingError):
    message = "This rate is on saved documents. Give it an end date instead of deleting it."


@transaction.atomic
def save_tax_rate(actor: User, rate: TaxRate, values: dict[str, Any]) -> TaxRate:
    action = Action.UPDATE if rate.pk else Action.CREATE
    before = {key: getattr(rate, key) if rate.pk else None for key in values}
    for key, value in values.items():
        setattr(rate, key, value)
    rate.save()
    audit.record(action, rate, actor, {key: [before[key], values[key]] for key in values})
    return rate


@transaction.atomic
def delete_tax_rate(actor: User, rate: TaxRate) -> None:
    audit.record(Action.DELETE, rate, actor, {"name": [rate.name, None]})
    try:
        with transaction.atomic():
            rate.delete()
    except models.ProtectedError as exc:
        raise TaxRateInUseError from exc
