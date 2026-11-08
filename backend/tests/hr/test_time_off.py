from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest

from apps.hr import retention, tasks
from apps.hr.models import Attendance, Employee, Holiday, HrSettings, LeaveRequest
from apps.tenancy.context import tenant_context
from apps.tenancy.models import AuditEvent
from tests.conftest import Member, make_member
from tests.factories import create_membership, create_role

pytestmark = pytest.mark.django_db


@pytest.fixture
def boss(db: None) -> Iterator[Member]:
    member = make_member(owner=True)
    with tenant_context(member.tenant):
        yield member


def person(member: Member, code: str = "E1", **extra: Any) -> Employee:
    values = {"code": code, "full_name": f"Worker {code}", "joined_on": date(2026, 1, 1), **extra}
    worker: Employee = Employee.objects.create(**values)
    return worker


def leave_type(member: Member, name: str = "Annual", days: str = "14", paid: bool = True) -> int:
    body = {"name": name, "days_per_year": days, "paid": paid}
    reply = member.client().post("/api/hr/leave-types/", body, format="json")
    assert reply.status_code == 201, reply.content
    return int(reply.json()["id"])


def ask(member: Member, worker: Employee, kind: int, starts: str, ends: str) -> Any:
    body = {"employee": worker.pk, "leave_type": kind, "starts_on": starts, "ends_on": ends}
    return member.client().post("/api/hr/leave/", body, format="json")


# Settings and holidays


def test_settings_start_with_a_sunday_weekend_in_pakistan(boss: Member) -> None:
    body = boss.client().get("/api/hr/settings/").json()
    assert body == {"weekend": [6], "holiday_country": "PK", "id_retention_years": 6}


def test_settings_are_saved_and_audited(boss: Member) -> None:
    reply = boss.client().patch(
        "/api/hr/settings/", {"weekend": [5, 6], "holiday_country": "AE"}, format="json"
    )
    assert reply.status_code == 200, reply.content
    assert HrSettings.objects.get().weekend == [5, 6]
    assert AuditEvent.objects.filter(model="hr.HrSettings").exists()


@pytest.mark.parametrize(
    "change",
    [
        {"weekend": [0, 1, 2, 3, 4, 5, 6]},
        {"weekend": [7]},
        {"holiday_country": "US"},
        {"id_retention_years": 5},
    ],
)
def test_strange_settings_are_refused(boss: Member, change: dict[str, Any]) -> None:
    assert boss.client().patch("/api/hr/settings/", change, format="json").status_code == 400


def test_holidays_are_filled_from_the_library_once(boss: Member) -> None:
    first = boss.client().post("/api/hr/holidays/fill/", {"year": 2027}, format="json")
    assert first.status_code == 200, first.content
    assert first.json()["added"] > 10
    assert Holiday.objects.filter(on=date(2027, 8, 14)).exists()
    assert "estimates" in Holiday.objects.first().source  # type: ignore[union-attr]
    again = boss.client().post("/api/hr/holidays/fill/", {"year": 2027}, format="json")
    assert again.json()["added"] == 0


@pytest.mark.parametrize("locale", ["C.UTF-8", "en_US.UTF-8", "ur_PK.UTF-8"])
def test_holiday_names_do_not_follow_the_server_locale(
    boss: Member, monkeypatch: pytest.MonkeyPatch, locale: str
) -> None:
    for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANG", locale)
    boss.client().post("/api/hr/holidays/fill/", {"year": 2027}, format="json")
    assert Holiday.objects.get(on=date(2027, 8, 14)).name == "Independence Day"
    assert Holiday.objects.filter(name__startswith="Eid-ul-Fitr").exists()


def test_a_corrected_holiday_survives_a_refill(boss: Member) -> None:
    boss.client().post("/api/hr/holidays/fill/", {"year": 2027}, format="json")
    eid = Holiday.objects.filter(name__startswith="Eid-ul-Fitr").first()
    assert eid is not None
    reply = boss.client().patch(
        f"/api/hr/holidays/{eid.pk}/",
        {"name": "Eid-ul-Fitr", "source": "Ruet-e-Hilal notice"},
        format="json",
    )
    assert reply.status_code == 200
    boss.client().post("/api/hr/holidays/fill/", {"year": 2027}, format="json")
    eid.refresh_from_db()
    assert eid.source == "Ruet-e-Hilal notice"


def test_two_holidays_on_one_day_are_refused(boss: Member) -> None:
    body = {"on": "2027-01-01", "name": "New Year"}
    assert boss.client().post("/api/hr/holidays/", body, format="json").status_code == 201
    assert boss.client().post("/api/hr/holidays/", body, format="json").status_code == 400


def test_holidays_are_listed_by_year_and_removed(boss: Member) -> None:
    made = boss.client().post(
        "/api/hr/holidays/", {"on": "2027-01-01", "name": "X"}, format="json"
    )
    boss.client().post("/api/hr/holidays/", {"on": "2028-01-01", "name": "Y"}, format="json")
    assert [h["name"] for h in boss.client().get("/api/hr/holidays/?year=2027").json()] == ["X"]
    assert boss.client().delete(f"/api/hr/holidays/{made.json()['id']}/").status_code == 204


# Leave


def test_leave_counts_only_working_days(boss: Member) -> None:
    worker = person(boss)
    kind = leave_type(boss)
    Holiday.objects.create(on=date(2026, 11, 9), name="Iqbal Day")
    # Saturday 7 to Wednesday 11 November: Sunday is the weekend and Monday a holiday.
    reply = ask(boss, worker, kind, "2026-11-07", "2026-11-11")
    assert reply.status_code == 201, reply.content
    assert reply.json()["days"] == "3.0"
    assert reply.json()["status"] == "pending"


def test_overlapping_leave_is_refused(boss: Member) -> None:
    worker, kind = person(boss), leave_type(boss)
    assert ask(boss, worker, kind, "2026-11-02", "2026-11-04").status_code == 201
    assert ask(boss, worker, kind, "2026-11-04", "2026-11-05").status_code == 400


@pytest.mark.parametrize(
    ("starts", "ends"),
    [("2026-11-08", "2026-11-08"), ("2025-12-29", "2025-12-30"), ("2026-11-05", "2026-11-04")],
)
def test_leave_that_makes_no_sense_is_refused(boss: Member, starts: str, ends: str) -> None:
    worker, kind = person(boss), leave_type(boss)
    assert ask(boss, worker, kind, starts, ends).status_code == 400


def test_leave_after_someone_left_is_refused(boss: Member) -> None:
    worker = person(boss, left_on=date(2026, 6, 30))
    assert ask(boss, worker, leave_type(boss), "2026-07-01", "2026-07-02").status_code == 400


def test_more_than_a_year_of_leave_is_refused(boss: Member) -> None:
    worker = person(boss)
    assert (
        ask(boss, worker, leave_type(boss, days="0"), "2026-01-01", "2027-01-05").status_code
        == 400
    )


def test_leave_over_new_year_is_asked_for_once_per_year(boss: Member) -> None:
    worker = person(boss)
    kind = leave_type(boss)
    over = ask(boss, worker, kind, "2026-12-28", "2027-01-05")
    assert over.status_code == 400
    assert "two requests" in str(over.json())
    assert ask(boss, worker, kind, "2026-12-28", "2026-12-31").status_code == 201
    assert ask(boss, worker, kind, "2027-01-01", "2027-01-05").status_code == 201


def test_approving_keeps_to_the_yearly_allowance(boss: Member) -> None:
    worker, kind = person(boss), leave_type(boss, days="3")
    first = ask(boss, worker, kind, "2026-11-02", "2026-11-03").json()["id"]
    second = ask(boss, worker, kind, "2026-11-05", "2026-11-06").json()["id"]
    assert boss.client().post(f"/api/hr/leave/{first}/approve/").status_code == 200
    refused = boss.client().post(f"/api/hr/leave/{second}/approve/")
    assert refused.status_code == 400
    assert "left this year" in str(refused.json())
    assert boss.client().post(f"/api/hr/leave/{first}/approve/").status_code == 400
    balances = boss.client().get(f"/api/hr/leave/balances/?employee={worker.pk}&year=2026").json()
    assert balances[0]["taken"] == "2.0"
    assert balances[0]["pending"] == "2.0"
    assert balances[0]["left"] == "1.0"


def test_unpaid_leave_has_no_yearly_limit(boss: Member) -> None:
    worker, kind = person(boss), leave_type(boss, "Unpaid", "0", paid=False)
    pk = ask(boss, worker, kind, "2026-03-02", "2026-03-31").json()["id"]
    assert boss.client().post(f"/api/hr/leave/{pk}/approve/").status_code == 200
    balance = boss.client().get(f"/api/hr/leave/balances/?employee={worker.pk}").json()
    assert balance[0]["left"] is None


def test_deciding_leave_needs_the_post_right(boss: Member) -> None:
    membership = create_membership(role=create_role(permissions={"hr": ["view", "create"]}))
    clerk = Member(user=membership.user, tenant=boss.tenant, membership=membership)
    worker, kind = person(boss), leave_type(boss)
    pk = ask(clerk, worker, kind, "2026-11-02", "2026-11-02").json()["id"]
    assert clerk.client().post(f"/api/hr/leave/{pk}/approve/").status_code == 403
    assert boss.client().post(f"/api/hr/leave/{pk}/reject/").json()["status"] == "rejected"


def test_only_pending_leave_can_be_withdrawn(boss: Member) -> None:
    worker, kind = person(boss), leave_type(boss)
    pending = ask(boss, worker, kind, "2026-11-02", "2026-11-02").json()["id"]
    decided = ask(boss, worker, kind, "2026-11-03", "2026-11-03").json()["id"]
    boss.client().post(f"/api/hr/leave/{decided}/approve/")
    assert boss.client().delete(f"/api/hr/leave/{pending}/").status_code == 204
    assert boss.client().delete(f"/api/hr/leave/{decided}/").status_code == 400
    assert list(LeaveRequest.objects.values_list("pk", flat=True)) == [decided]


def test_a_switched_off_leave_type_cannot_be_asked_for(boss: Member) -> None:
    worker, kind = person(boss), leave_type(boss)
    boss.client().patch(f"/api/hr/leave-types/{kind}/", {"is_active": False}, format="json")
    assert ask(boss, worker, kind, "2026-11-02", "2026-11-02").status_code == 400


def test_balances_for_someone_unknown_are_not_found(boss: Member) -> None:
    assert boss.client().get("/api/hr/leave/balances/?employee=999999").status_code == 404


def test_a_leave_type_in_use_cannot_be_deleted(boss: Member) -> None:
    worker, kind = person(boss), leave_type(boss)
    ask(boss, worker, kind, "2026-11-02", "2026-11-02")
    assert boss.client().delete(f"/api/hr/leave-types/{kind}/").status_code == 400
    spare = leave_type(boss, "Spare")
    assert boss.client().delete(f"/api/hr/leave-types/{spare}/").status_code == 204


# Attendance


def test_a_day_lists_who_works_and_who_is_away(boss: Member) -> None:
    here, away = person(boss, "E1"), person(boss, "E2")
    person(boss, "E3", left_on=date(2026, 6, 30))
    kind = leave_type(boss)
    pk = ask(boss, away, kind, "2026-11-10", "2026-11-10").json()["id"]
    boss.client().post(f"/api/hr/leave/{pk}/approve/")
    body = boss.client().get("/api/hr/attendance/?date=2026-11-10").json()
    assert body["working_day"] is True
    rows = {row["code"]: row for row in body["people"]}
    assert set(rows) == {"E1", "E2"}
    assert rows["E1"]["status"] == "present"
    assert rows["E2"]["on_leave"] is True
    assert here.pk == rows["E1"]["employee"]


def test_weekends_and_holidays_are_not_working_days(boss: Member) -> None:
    Holiday.objects.create(on=date(2026, 11, 9), name="Iqbal Day")
    holiday = boss.client().get("/api/hr/attendance/?date=2026-11-09").json()
    assert (holiday["working_day"], holiday["holiday"]) == (False, "Iqbal Day")
    assert boss.client().get("/api/hr/attendance/?date=2026-11-08").json()["working_day"] is False


def test_marking_a_day_keeps_only_what_differs_from_present(boss: Member) -> None:
    first, second = person(boss, "E1"), person(boss, "E2")
    body = {
        "on": "2026-11-10",
        "rows": [
            {"employee": first.pk, "status": "absent", "note": "Sick, called in"},
            {"employee": second.pk, "status": "present"},
        ],
    }
    reply = boss.client().post("/api/hr/attendance/", body, format="json")
    assert reply.json() == {"changed": 1}
    assert list(Attendance.objects.values_list("employee_id", "status")) == [(first.pk, "absent")]
    # The same again changes nothing; back to present keeps the row as present.
    assert boss.client().post("/api/hr/attendance/", body, format="json").json() == {"changed": 0}
    body["rows"] = [{"employee": first.pk, "status": "present"}]
    assert boss.client().post("/api/hr/attendance/", body, format="json").json() == {"changed": 1}
    assert Attendance.objects.get().status == "present"


def test_marking_someone_not_employed_that_day_is_refused(boss: Member) -> None:
    gone = person(boss, left_on=date(2026, 6, 30))
    body = {"on": "2026-11-10", "rows": [{"employee": gone.pk, "status": "absent"}]}
    assert boss.client().post("/api/hr/attendance/", body, format="json").status_code == 400


# Retention


def test_a_former_employees_bank_account_goes_after_90_days(boss: Member) -> None:
    worker = person(boss, bank_account="PK00", national_id="35202", left_on=date(2026, 7, 15))
    assert retention.clear_former_employees(date(2026, 10, 13)) == 0
    assert retention.clear_former_employees(date(2026, 10, 14)) == 1
    worker.refresh_from_db()
    assert (worker.bank_account, worker.national_id) == ("", "35202")


def test_a_national_id_stays_six_years_after_the_tax_year(boss: Member) -> None:
    # Left in July 2026, so in the tax year ending 30 June 2027; kept to 30 June 2033.
    worker = person(boss, national_id="35202", left_on=date(2026, 7, 15))
    retention.clear_former_employees(date(2033, 6, 30))
    worker.refresh_from_db()
    assert worker.national_id == "35202"
    retention.clear_former_employees(date(2033, 7, 1))
    worker.refresh_from_db()
    assert worker.national_id == ""
    event = AuditEvent.objects.filter(model="hr.Employee").latest("id")
    assert event.user is None
    assert "35202" not in str(event.changes)


def test_a_business_can_keep_ids_longer(boss: Member) -> None:
    boss.client().patch("/api/hr/settings/", {"id_retention_years": 8}, format="json")
    worker = person(boss, national_id="35202", left_on=date(2026, 7, 15))
    retention.clear_former_employees(date(2034, 1, 1))
    worker.refresh_from_db()
    assert worker.national_id == "35202"


def test_people_still_working_are_never_touched(boss: Member) -> None:
    worker = person(boss, bank_account="PK00", national_id="35202")
    assert retention.clear_former_employees(date(2040, 1, 1)) == 0
    worker.refresh_from_db()
    assert worker.national_id == "35202"


def test_the_nightly_job_runs_for_every_business(boss: Member) -> None:
    person(boss, bank_account="PK00", joined_on=date(2019, 1, 1), left_on=date(2020, 1, 31))
    other = make_member(owner=True)
    with tenant_context(other.tenant):
        person(other, bank_account="PK11", joined_on=date(2019, 1, 1), left_on=date(2020, 1, 31))
    assert tasks.clear_former_employee_details() == 2


def test_a_leap_day_moves_to_the_28th(boss: Member) -> None:
    assert retention._years_after(date(2028, 2, 29), 1) == date(2029, 2, 28)
