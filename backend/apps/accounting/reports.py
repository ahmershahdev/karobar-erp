from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum

from apps.core.balances import AccountType, balance, split
from apps.core.money import quantize_money
from apps.tenancy.context import get_current_tenant

from .models import Account, JournalEntry, JournalLine

ZERO = Decimal("0.00")


POSTED = Q(entry__status=JournalEntry.Status.POSTED)


def posted() -> Q:
    """Posted lines for reports on a few accounts. Naming the entry's tenant lets MySQL range over
    the entry's (tenant, status, date) index, which took a cash balance over a million lines from
    3.8s to 1.3s. Reports grouped over every account use POSTED: with this filter MySQL drives
    them from the lines instead, which measured five times slower."""
    return POSTED & Q(entry__tenant=get_current_tenant())


@dataclass(frozen=True)
class TrialBalanceRow:
    id: int
    code: str
    name: str
    type: str
    debit: Decimal
    credit: Decimal


@dataclass(frozen=True)
class TrialBalance:
    start: date | None
    end: date
    rows: list[TrialBalanceRow]
    total_debit: Decimal
    total_credit: Decimal


def trial_balance(end: date, start: date | None = None) -> TrialBalance:
    """Balances of every account with activity up to `end` (or within [start, end])."""
    window = POSTED & Q(entry__date__lte=end)
    if start is not None:
        window &= Q(entry__date__gte=start)
    sums = (
        JournalLine.objects.filter(window)
        .values("account_id")
        .annotate(debits=Sum("debit"), credits=Sum("credit"))
    )
    by_account = {row["account_id"]: row for row in sums}
    accounts = Account.objects.filter(pk__in=by_account).order_by("code")
    rows: list[TrialBalanceRow] = []
    for account in accounts:
        totals = by_account[account.pk]
        kind = AccountType(account.type)
        amount = balance(kind, totals["debits"] or ZERO, totals["credits"] or ZERO)
        if amount == 0:
            continue
        debit, credit = split(kind, amount)
        rows.append(
            TrialBalanceRow(account.pk, account.code, account.name, account.type, debit, credit)
        )
    return TrialBalance(
        start=start,
        end=end,
        rows=rows,
        total_debit=quantize_money(sum((row.debit for row in rows), ZERO)),
        total_credit=quantize_money(sum((row.credit for row in rows), ZERO)),
    )


@dataclass(frozen=True)
class LedgerLine:
    entry_id: int
    number: str
    date: date
    memo: str
    description: str
    debit: Decimal
    credit: Decimal
    balance: Decimal


@dataclass(frozen=True)
class Ledger:
    account: Account
    start: date | None
    end: date | None
    opening: Decimal
    lines: list[LedgerLine]
    closing: Decimal


def general_ledger(account: Account, start: date | None, end: date | None) -> Ledger:
    """Every posted line of one account, with the running balance on its normal side."""
    kind = AccountType(account.type)
    lines = JournalLine.objects.filter(posted(), account=account)
    opening = ZERO
    if start is not None:
        before = lines.filter(entry__date__lt=start).aggregate(d=Sum("debit"), c=Sum("credit"))
        opening = balance(kind, before["d"] or ZERO, before["c"] or ZERO)
        lines = lines.filter(entry__date__gte=start)
    if end is not None:
        lines = lines.filter(entry__date__lte=end)
    running = opening
    out: list[LedgerLine] = []
    for line in lines.select_related("entry").order_by("entry__date", "entry__number", "id"):
        running = quantize_money(running + balance(kind, line.debit, line.credit))
        out.append(
            LedgerLine(
                entry_id=line.entry_id,
                number=line.entry.number or "",
                date=line.entry.date,
                memo=line.entry.memo,
                description=line.description,
                debit=line.debit,
                credit=line.credit,
                balance=running,
            )
        )
    return Ledger(account, start, end, opening, out, running)
