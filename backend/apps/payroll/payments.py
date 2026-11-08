"""Paying a posted month's salaries, and the list the bank needs to do it.

Posting a payroll books the salaries as owed (salaries payable). Paying them is a separate step
because it happens later, often in the first days of the next month, and from a particular bank
account or the till: Dr salaries payable, Cr that account, for the month's total net pay.
"""

from datetime import date
from typing import Any

from django.db import transaction

from apps.accounting import services as accounting
from apps.accounting.models import Account
from apps.accounts.models import User
from apps.core import posting
from apps.core.balances import AccountType
from apps.platform.locking import lock_rows
from apps.tenancy import audit
from apps.tenancy.models import AuditEvent

from .models import PayrollRun, Payslip, SalaryPayment
from .services import PayrollError, lock_business

Action = AuditEvent.Action


class NotPostedError(PayrollError):
    message = "Only a posted payroll can be paid. Post it first."


class AlreadyPaidError(PayrollError):
    message = "This month's salaries are already paid."


class BadAccountError(PayrollError):
    message = "Choose an active cash or bank account that is not a group."


class TooEarlyError(PayrollError):
    message = "Salaries can't be paid before the month they are for has started."


@transaction.atomic
def pay(actor: User, run: PayrollRun, data: dict[str, Any]) -> SalaryPayment:
    lock_business()
    locked: PayrollRun = lock_rows(PayrollRun.objects.filter(pk=run.pk))[0]
    if locked.status != PayrollRun.Status.POSTED:
        raise NotPostedError
    if SalaryPayment.objects.filter(run=locked).exists():
        raise AlreadyPaidError
    paid_on: date = data["paid_on"]
    if paid_on < locked.month:
        raise TooEarlyError
    source: Account = data["paid_from"]
    if source.type != AccountType.ASSET or source.is_group or not source.is_active:
        raise BadAccountError
    entry = accounting.post_rule_lines(
        actor,
        paid_on,
        f"Salaries paid for {locked.month:%B %Y}",
        posting.salary_payment(locked.net, out_of="paid_from"),
        {"paid_from": source},
        ("salary_payment", str(locked.pk)),
    )
    payment: SalaryPayment = SalaryPayment.objects.create(
        run=locked,
        paid_on=paid_on,
        paid_from=source,
        amount=locked.net,
        reference=data.get("reference", ""),
        entry=entry,
        paid_by=actor,
    )
    audit.record(
        Action.POST,
        payment,
        actor,
        {"amount": [None, str(payment.amount)], "paid_on": [None, str(paid_on)]},
    )
    return payment


TRANSFER_HEADER = ("Code", "Name", "Bank account", "Net pay", "Reference")


def transfer_rows(run: PayrollRun) -> list[tuple[object, ...]]:
    """Rows for the bank transfer list: one per person with their bank account and net pay.
    People without a bank account are kept, with the account left empty, so nobody is missed;
    they are paid in cash or the account is added first. platform.csv_export writes the file and
    keeps cells from running as spreadsheet formulas."""
    return [
        (
            slip.employee.code,
            slip.employee.full_name,
            slip.employee.bank_account,
            slip.net,
            f"Salary {run.month:%Y-%m}",
        )
        for slip in Payslip.objects.filter(run=run)
        .select_related("employee")
        .order_by("employee__code")
    ]
