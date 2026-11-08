import importlib
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.apps import apps as django_apps

from apps.accounting import services as accounting
from apps.accounting.models import Account, FiscalPeriod, JournalLine
from apps.payroll.models import PayrollRun
from apps.tenancy.models import AuditEvent
from tests.conftest import Member
from tests.factories import create_membership, create_role
from tests.payroll.test_payroll import boss, contract, person, post, work_out  # noqa: F401

pytestmark = pytest.mark.django_db
D = Decimal


def reverse(member: Member, run_id: int, reason: str = "Wrong basic salary") -> Any:
    url = f"/api/payroll/runs/{run_id}/reverse/"
    return member.client().post(url, {"reason": reason}, format="json")


def posted(member: Member, month: str = "2026-07-01") -> int:
    run_id: int = work_out(member, month).json()["id"]
    assert post(member, run_id).json()["posted"] is True
    return run_id


def balance(role: str) -> Decimal:
    lines = JournalLine.objects.filter(account__role=role, entry__status="posted")
    return sum((line.debit - line.credit for line in lines), D(0))


def test_undoing_reverses_the_books_and_keeps_the_run(boss: Member) -> None:  # noqa: F811
    contract(boss, person(), "150000")
    run_id = posted(boss)
    assert balance("salaries") == D("150000.00")
    reply = reverse(boss, run_id)
    assert reply.status_code == 200, reply.content
    body = reply.json()
    assert body["status"] == "reversed"
    assert body["reversal_reason"] == "Wrong basic salary"
    assert body["reversal_number"].startswith("JV-")
    assert body["number"] == "PAY-000001"
    assert len(body["payslips"]) == 1
    for role in ("salaries", "salaries_payable", "withholding_payable"):
        assert balance(role) == D(0), role
    assert AuditEvent.objects.filter(
        model="payroll.PayrollRun", object_id=str(run_id), changes__status=["posted", "reversed"]
    ).exists()


def test_an_undone_month_can_be_worked_out_again(boss: Member) -> None:  # noqa: F811
    contract(boss, person(), "150000")
    first = posted(boss)
    reverse(boss, first)
    again = work_out(boss).json()
    assert again["id"] != first
    assert again["status"] == "draft"
    assert post(boss, again["id"]).json()["run"]["number"] == "PAY-000002"
    months = [(r["status"], r["number"]) for r in boss.client().get("/api/payroll/runs/").json()]
    assert sorted(months) == [("posted", "PAY-000002"), ("reversed", "PAY-000001")]


def test_only_a_posted_unpaid_month_is_undone(boss: Member) -> None:  # noqa: F811
    contract(boss, person(), "150000")
    draft = work_out(boss).json()["id"]
    assert reverse(boss, draft).status_code == 400
    post(boss, draft)
    assert reverse(boss, draft).status_code == 200
    assert reverse(boss, draft).status_code == 400


def test_a_paid_month_cannot_be_undone(boss: Member) -> None:  # noqa: F811
    contract(boss, person(), "150000")
    run_id = posted(boss)
    paid = boss.client().post(
        f"/api/payroll/runs/{run_id}/pay/",
        {"paid_on": "2026-08-01", "paid_from": Account.objects.get(role="bank").pk},
        format="json",
    )
    assert paid.status_code == 200
    reply = reverse(boss, run_id)
    assert reply.status_code == 400
    assert "already paid" in reply.json()["detail"]
    assert PayrollRun.objects.get().status == PayrollRun.Status.POSTED


def test_months_are_undone_from_the_latest_back(boss: Member) -> None:  # noqa: F811
    contract(boss, person(), "150000")
    july = posted(boss)
    august = posted(boss, "2026-08-01")
    blocked = reverse(boss, july)
    assert blocked.status_code == 400
    assert "later month" in blocked.json()["detail"]
    assert reverse(boss, august).status_code == 200
    assert reverse(boss, july).status_code == 200


def test_an_undone_month_no_longer_counts_in_the_years_tax(boss: Member) -> None:  # noqa: F811
    contract(boss, person(), "150000")
    reverse(boss, posted(boss))
    # With July undone, August sees no earlier pay and guesses 11 months of 150,000.
    august = work_out(boss, "2026-08-01").json()["payslips"][0]
    assert august["tax"] == "5045.45"


def test_an_undone_month_has_no_payslips_or_transfer_list(boss: Member) -> None:  # noqa: F811
    contract(boss, person(), "150000")
    run_id = posted(boss)
    reverse(boss, run_id)
    slip = boss.client().get(f"/api/payroll/runs/{run_id}/").json()["payslips"][0]["id"]
    assert boss.client().get(f"/api/payroll/payslips/{slip}/pdf/").status_code == 400
    assert boss.client().get(f"/api/payroll/runs/{run_id}/transfer-list/").status_code == 400


def test_undoing_needs_the_post_right(boss: Member) -> None:  # noqa: F811
    contract(boss, person(), "150000")
    run_id = posted(boss)
    joined = create_membership(role=create_role(permissions={"payroll": ["view", "create"]}))
    clerk = Member(user=joined.user, tenant=boss.tenant, membership=joined).client()
    assert clerk.post(f"/api/payroll/runs/{run_id}/reverse/", {}, format="json").status_code == 403


def test_a_closed_month_cannot_be_undone(boss: Member) -> None:  # noqa: F811
    contract(boss, person(), "150000")
    run_id = posted(boss)
    accounting.set_period_closed(
        boss.user, FiscalPeriod.objects.get(start=date(2026, 7, 1)), closed=True
    )
    assert reverse(boss, run_id).status_code == 400
    assert PayrollRun.objects.get().status == PayrollRun.Status.POSTED


def test_runs_made_before_undoing_existed_count_as_live(boss: Member) -> None:  # noqa: F811
    contract(boss, person(), "150000")
    posted(boss)
    PayrollRun.objects.update(live_month=None)
    migration = importlib.import_module("apps.payroll.migrations.0004_payroll_reversal")
    migration.fill_live_month(django_apps, None)
    assert PayrollRun.objects.get().live_month == date(2026, 7, 1)
