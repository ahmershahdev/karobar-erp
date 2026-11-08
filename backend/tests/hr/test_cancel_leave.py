from typing import Any

import pytest

from apps.hr.models import Employee, LeaveRequest
from apps.tenancy.models import AuditEvent
from tests.conftest import Member
from tests.factories import create_membership, create_role
from tests.hr.test_time_off import ask, boss, leave_type, person  # noqa: F401

pytestmark = pytest.mark.django_db


def approved(member: Member, worker: Employee, kind: int, starts: str, ends: str) -> int:
    pk: int = ask(member, worker, kind, starts, ends).json()["id"]
    assert member.client().post(f"/api/hr/leave/{pk}/approve/").status_code == 200
    return pk


def cancel(member: Member, pk: int, back_on: str | None = None) -> Any:
    body = {} if back_on is None else {"back_on": back_on}
    return member.client().post(f"/api/hr/leave/{pk}/cancel/", body, format="json")


def taken(member: Member, worker: Employee) -> str:
    url = f"/api/hr/leave/balances/?employee={worker.pk}&year=2026"
    value: str = member.client().get(url).json()[0]["taken"]
    return value


def test_cancelling_gives_all_the_days_back(boss: Member) -> None:  # noqa: F811
    worker, kind = person(boss), leave_type(boss)
    # Monday 2 to Friday 6 November: five working days.
    pk = approved(boss, worker, kind, "2026-11-02", "2026-11-06")
    assert taken(boss, worker) == "5.0"
    reply = cancel(boss, pk)
    assert reply.status_code == 200, reply.content
    assert reply.json()["status"] == "cancelled"
    assert taken(boss, worker) == "0.0"
    event = AuditEvent.objects.filter(model="hr.LeaveRequest", object_id=str(pk)).last()
    assert event is not None
    assert event.changes["status"] == ["approved", "cancelled"]


def test_coming_back_early_gives_the_rest_back(boss: Member) -> None:  # noqa: F811
    worker, kind = person(boss), leave_type(boss)
    pk = approved(boss, worker, kind, "2026-11-02", "2026-11-06")
    reply = cancel(boss, pk, back_on="2026-11-05")
    body = reply.json()
    assert (body["status"], body["ends_on"], body["days"]) == ("approved", "2026-11-04", "3.0")
    assert taken(boss, worker) == "3.0"


def test_a_back_day_before_the_leave_cancels_all_of_it(boss: Member) -> None:  # noqa: F811
    worker, kind = person(boss), leave_type(boss)
    pk = approved(boss, worker, kind, "2026-11-02", "2026-11-06")
    assert cancel(boss, pk, back_on="2026-10-30").json()["status"] == "cancelled"


def test_a_back_day_after_the_leave_gives_nothing_back(boss: Member) -> None:  # noqa: F811
    worker, kind = person(boss), leave_type(boss)
    pk = approved(boss, worker, kind, "2026-11-02", "2026-11-06")
    reply = cancel(boss, pk, back_on="2026-11-09")
    assert reply.status_code == 400
    assert "no days to give back" in reply.json()["detail"]


def test_only_weekend_left_counts_as_cancelled(boss: Member) -> None:  # noqa: F811
    worker, kind = person(boss), leave_type(boss)
    # Sunday 8 (the weekend) and Monday 9 November: one working day.
    pk = approved(boss, worker, kind, "2026-11-08", "2026-11-09")
    body = cancel(boss, pk, back_on="2026-11-09").json()
    assert (body["status"], body["days"]) == ("cancelled", "0.0")


def test_only_approved_leave_is_cancelled(boss: Member) -> None:  # noqa: F811
    worker, kind = person(boss), leave_type(boss)
    pending = ask(boss, worker, kind, "2026-11-02", "2026-11-03").json()["id"]
    assert cancel(boss, pending).status_code == 400
    done = approved(boss, worker, kind, "2026-11-10", "2026-11-10")
    assert cancel(boss, done).status_code == 200
    assert cancel(boss, done).status_code == 400
    assert LeaveRequest.objects.get(pk=done).status == LeaveRequest.Status.CANCELLED


def test_cancelling_needs_the_post_right(boss: Member) -> None:  # noqa: F811
    worker, kind = person(boss), leave_type(boss)
    pk = approved(boss, worker, kind, "2026-11-02", "2026-11-02")
    joined = create_membership(role=create_role(permissions={"hr": ["view", "update"]}))
    clerk = Member(user=joined.user, tenant=boss.tenant, membership=joined).client()
    assert clerk.post(f"/api/hr/leave/{pk}/cancel/", {}, format="json").status_code == 403
