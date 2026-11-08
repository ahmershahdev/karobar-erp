from datetime import date

import pytest

from apps.hr.models import LeaveRequest, LeaveType
from tests.conftest import Member
from tests.payroll.test_payroll import boss, contract, person, post, work_out  # noqa: F401

pytestmark = pytest.mark.django_db


def leave(worker_id: int, paid: bool) -> LeaveRequest:
    kind = LeaveType.objects.create(name="Unpaid" if not paid else "Annual", paid=paid)
    made: LeaveRequest = LeaveRequest.objects.create(
        employee_id=worker_id,
        leave_type=kind,
        starts_on=date(2026, 7, 6),
        ends_on=date(2026, 7, 7),
        days=2,
        status=LeaveRequest.Status.APPROVED,
    )
    return made


def cancel(member: Member, pk: int) -> int:
    code: int = member.client().post(f"/api/hr/leave/{pk}/cancel/", {}, format="json").status_code
    return code


def test_unpaid_days_already_taken_off_pay_stay_until_payroll_is_undone(
    boss: Member,  # noqa: F811
) -> None:
    worker = person()
    contract(boss, worker, "31000")
    unpaid = leave(worker.pk, paid=False)
    post(boss, work_out(boss).json()["id"])
    reply = boss.client().post(f"/api/hr/leave/{unpaid.pk}/cancel/", {}, format="json")
    assert reply.status_code == 400
    assert "Undo that payroll first" in reply.json()["detail"]


def test_paid_leave_can_be_cancelled_after_payroll(boss: Member) -> None:  # noqa: F811
    worker = person()
    contract(boss, worker, "31000")
    annual = leave(worker.pk, paid=True)
    post(boss, work_out(boss).json()["id"])
    assert cancel(boss, annual.pk) == 200


def test_unpaid_leave_in_a_month_not_yet_posted_can_be_cancelled(
    boss: Member,  # noqa: F811
) -> None:
    worker = person()
    contract(boss, worker, "31000")
    unpaid = leave(worker.pk, paid=False)
    work_out(boss)  # A draft only.
    assert cancel(boss, unpaid.pk) == 200
