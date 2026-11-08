from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from apps.accounting import services as accounting
from apps.accounting.models import Account, FiscalPeriod, JournalLine
from apps.hr.models import Employee
from apps.payroll.models import SalaryPayment
from apps.tenancy.models import AuditEvent
from tests.conftest import Member
from tests.factories import create_membership, create_role
from tests.payroll.test_payroll import STANDARD, boss, contract, person, post, work_out  # noqa: F401

pytestmark = pytest.mark.django_db
D = Decimal


def posted_july(member: Member, **worker: Any) -> int:
    contract(member, person(**worker), "50000", parts=STANDARD)
    run_id: int = work_out(member).json()["id"]
    assert post(member, run_id).json()["posted"] is True
    return run_id


def pay(member: Member, run_id: int, **change: Any) -> Any:
    body = {
        "paid_on": "2026-08-02",
        "paid_from": Account.objects.get(role="bank").pk,
        "reference": "Cheque 1001",
        **change,
    }
    return member.client().post(f"/api/payroll/runs/{run_id}/pay/", body, format="json")


def balance(role: str) -> Decimal:
    lines = JournalLine.objects.filter(account__role=role, entry__status="posted")
    return sum((line.debit - line.credit for line in lines), D(0))


def test_paying_settles_the_salaries_owed(boss: Member) -> None:  # noqa: F811
    run_id = posted_july(boss)
    assert boss.client().get(f"/api/payroll/runs/{run_id}/").json()["payment"] is None
    reply = pay(boss, run_id)
    assert reply.status_code == 200, reply.content
    paid = reply.json()["payment"]
    assert (paid["amount"], paid["paid_on"], paid["reference"]) == (
        "73110.00",
        "2026-08-02",
        "Cheque 1001",
    )
    assert paid["paid_from_name"] == Account.objects.get(role="bank").name
    assert paid["entry_number"].startswith("JV-")
    assert balance("salaries_payable") == D(0)
    assert balance("bank") == D("-73110.00")
    assert AuditEvent.objects.filter(
        model="payroll.SalaryPayment", action=AuditEvent.Action.POST
    ).exists()


def test_only_a_posted_month_is_paid_and_only_once(boss: Member) -> None:  # noqa: F811
    contract(boss, person(), "50000")
    draft = work_out(boss).json()["id"]
    assert "Post it first" in pay(boss, draft).json()["detail"]
    post(boss, draft)
    assert pay(boss, draft).status_code == 200
    again = pay(boss, draft)
    assert again.status_code == 400
    assert "already paid" in again.json()["detail"]
    assert SalaryPayment.objects.count() == 1


def test_salaries_are_not_paid_before_their_month(boss: Member) -> None:  # noqa: F811
    run_id = posted_july(boss)
    assert pay(boss, run_id, paid_on="2026-06-30").status_code == 400
    assert pay(boss, run_id, paid_on="2026-07-01").status_code == 200


@pytest.mark.parametrize("pick", ["income", "group", "inactive"])
def test_money_leaves_only_a_cash_or_bank_account(boss: Member, pick: str) -> None:  # noqa: F811
    run_id = posted_july(boss)
    account = {
        "income": lambda: Account.objects.get(role="sales"),
        "group": lambda: Account.objects.get(code="1100"),
        "inactive": lambda: Account.objects.get(role="cash"),
    }[pick]()
    if pick == "inactive":
        account.is_active = False
        account.save()
    reply = pay(boss, run_id, paid_from=account.pk)
    assert reply.status_code == 400
    assert not SalaryPayment.objects.exists()


def test_paying_into_a_closed_month_is_refused(boss: Member) -> None:  # noqa: F811
    run_id = posted_july(boss)
    august = FiscalPeriod.objects.get(start=date(2026, 8, 1))
    accounting.set_period_closed(boss.user, august, closed=True)
    assert pay(boss, run_id).status_code == 400
    assert not SalaryPayment.objects.exists()


def test_paying_needs_the_post_right(boss: Member) -> None:  # noqa: F811
    run_id = posted_july(boss)
    joined = create_membership(role=create_role(permissions={"payroll": ["view", "create"]}))
    clerk = Member(user=joined.user, tenant=boss.tenant, membership=joined).client()
    body = {"paid_on": "2026-08-02", "paid_from": Account.objects.get(role="bank").pk}
    assert clerk.post(f"/api/payroll/runs/{run_id}/pay/", body, format="json").status_code == 403


# The bank transfer list


def test_the_transfer_list_has_everyones_account_and_net_pay(boss: Member) -> None:  # noqa: F811
    contract(boss, person("E1", bank_account="PK00TEST0000000001"), "50000", parts=STANDARD)
    odd = Employee.objects.create(code="E2", full_name="=HYPERLINK(1)", joined_on=date(2026, 1, 1))
    contract(boss, odd, "30000")
    run_id = work_out(boss).json()["id"]
    url = f"/api/payroll/runs/{run_id}/transfer-list/"
    assert boss.client().get(url).status_code == 400
    post(boss, run_id)
    reply = boss.client().get(url)
    assert reply.status_code == 200
    assert reply["Content-Type"] == "text/csv"
    assert reply["Content-Disposition"] == 'attachment; filename="salaries-2026-07.csv"'
    rows = reply.content.decode().splitlines()
    assert rows[0] == "Code,Name,Bank account,Net pay,Reference"
    assert rows[1] == "E1,Invented E1,PK00TEST0000000001,73110.00,Salary 2026-07"
    # A name that would run as a spreadsheet formula opens as text instead.
    assert rows[2] == "E2,'=HYPERLINK(1),,30000.00,Salary 2026-07"


def test_the_transfer_list_needs_hr_rights_for_the_bank_accounts(boss: Member) -> None:  # noqa: F811
    run_id = posted_july(boss)
    url = f"/api/payroll/runs/{run_id}/transfer-list/"

    def client(permissions: dict[str, list[str]]) -> Any:
        joined = create_membership(role=create_role(permissions=permissions))
        return Member(user=joined.user, tenant=boss.tenant, membership=joined).client()

    assert client({"payroll": ["view"]}).get(url).status_code == 403
    assert client({"payroll": ["view"], "hr": ["view"]}).get(url).status_code == 200
