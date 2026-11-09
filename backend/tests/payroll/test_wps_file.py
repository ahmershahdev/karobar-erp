from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from apps.hr import retention
from apps.hr.models import Attendance, Employee, HrSettings
from apps.payroll import gratuity
from apps.payroll.models import TaxTable
from tests.conftest import Member
from tests.factories import create_membership, create_role
from tests.payroll.test_payroll import boss, contract, person, post, work_out  # noqa: F401

pytestmark = pytest.mark.django_db
D = Decimal


def uae(member: Member, ids: bool = True) -> None:
    TaxTable.objects.all().delete()
    HrSettings.objects.create(
        holiday_country="AE",
        weekend=[5, 6],
        wps_employer_id="965625" if ids else "",
        wps_bank_code="302620122" if ids else "",
    )
    gratuity.fill_official(member.user)


def worker(code: str = "E1", **extra: Any) -> Employee:
    details = {
        "wps_person_id": "12345678",
        "wps_agent_code": "703420114",
        "bank_account": "AE02 0340 0002 2123 4567 001",
        **extra,
    }
    return person(code, joined=date(2026, 7, 16), **details)


def download(member: Member, run_id: int) -> Any:
    return member.client().get(f"/api/payroll/runs/{run_id}/wps-file/")


def posted(member: Member) -> int:
    run_id: int = work_out(member).json()["id"]
    post(member, run_id)
    return run_id


def test_a_posted_uae_month_gives_its_salary_file(boss: Member) -> None:  # noqa: F811
    uae(boss)
    contract(boss, worker(), "10000", starts=date(2026, 7, 16))
    run_id = posted(boss)
    reply = download(boss, run_id)
    assert reply.status_code == 200
    assert reply["Content-Type"] == "text/plain; charset=us-ascii"
    name = reply["Content-Disposition"]
    assert name.startswith('attachment; filename="0000000965625')
    assert name.endswith('.SIF"')
    edr, scr, end = reply.content.decode().split("\r\n")
    # Joined on the 16th: 16 days of a 31-day month, paid as net pay.
    assert edr == (
        "EDR,00000012345678,703420114,AE020340000221234567001,2026-07-16,2026-07-31,16,"
        "5161.29,0.00,0"
    )
    fields = scr.split(",")
    assert fields[:3] == ["SCR", "0000000965625", "302620122"]
    assert fields[5:] == ["072026", "1", "5161.29", "AED", "PAY-000001"]
    assert end == ""


def test_the_file_is_only_for_posted_uae_months(boss: Member) -> None:  # noqa: F811
    uae(boss)
    contract(boss, worker(), "10000", starts=date(2026, 7, 16))
    draft = work_out(boss).json()["id"]
    assert "once the payroll is posted" in download(boss, draft).json()["detail"]
    post(boss, draft)
    HrSettings.objects.update(holiday_country="SA")
    assert "businesses in the UAE" in download(boss, draft).json()["detail"]


def test_missing_details_are_named(boss: Member) -> None:  # noqa: F811
    uae(boss, ids=False)
    contract(boss, worker("E1"), "10000", starts=date(2026, 7, 16))
    contract(boss, worker("E2", wps_person_id=""), "10000", starts=date(2026, 7, 16))
    run_id = posted(boss)
    assert "MOL establishment ID" in download(boss, run_id).json()["detail"]
    HrSettings.objects.update(wps_employer_id="965625", wps_bank_code="302620122")
    detail = download(boss, run_id).json()["detail"]
    assert "labour card person ID" in detail
    assert detail.endswith("E2")


def test_a_detail_the_bank_would_refuse_is_said(boss: Member) -> None:  # noqa: F811
    uae(boss)
    contract(boss, worker(bank_account="A" * 30), "10000", starts=date(2026, 7, 16))
    assert "account is up to 23" in download(boss, posted(boss)).json()["detail"]


def test_the_file_needs_hr_rights(boss: Member) -> None:  # noqa: F811
    uae(boss)
    contract(boss, worker(), "10000", starts=date(2026, 7, 16))
    run_id = posted(boss)
    joined = create_membership(role=create_role(permissions={"payroll": ["view"]}))
    clerk = Member(user=joined.user, tenant=boss.tenant, membership=joined)
    assert download(clerk, run_id).status_code == 403


def test_wps_details_are_checked_on_the_employee(boss: Member) -> None:  # noqa: F811
    client = boss.client()
    body = {"code": "N1", "full_name": "Invented New", "joined_on": "2026-07-01"}
    good = client.post(
        "/api/hr/employees/",
        {**body, "wps_person_id": " 12345678 ", "wps_agent_code": "703420114"},
        format="json",
    )
    assert good.json()["wps_person_id"] == "12345678"
    for wrong in ({"wps_person_id": "12-34"}, {"wps_agent_code": "7034"}):
        bad = client.post("/api/hr/employees/", {**body, "code": "N2", **wrong}, format="json")
        assert bad.status_code == 400
    settings = client.patch(
        "/api/hr/settings/", {"wps_employer_id": "965625", "wps_bank_code": "12"}, format="json"
    )
    assert settings.status_code == 400


def test_the_labour_card_id_is_cleared_with_the_national_id(boss: Member) -> None:  # noqa: F811
    leaver = worker(national_id="784-1990-1234567-1")
    Employee.objects.filter(pk=leaver.pk).update(left_on=date(2026, 7, 31))
    retention.clear_former_employees(date(2034, 7, 1))
    leaver.refresh_from_db()
    assert (leaver.national_id, leaver.wps_person_id) == ("", "")


def test_a_half_day_absent_is_counted_not_dropped(boss: Member) -> None:  # noqa: F811
    uae(boss)
    someone = worker()
    contract(boss, someone, "10000", starts=date(2026, 7, 16))
    Attendance.objects.create(employee=someone, on=date(2026, 7, 20), status="half_day")
    edr = download(boss, posted(boss)).content.decode().split("\r\n")[0]
    assert edr.endswith(",1")


def test_a_later_edit_to_the_dates_does_not_change_the_file(boss: Member) -> None:  # noqa: F811
    uae(boss)
    someone = worker()
    contract(boss, someone, "10000", starts=date(2026, 7, 16))
    run_id = posted(boss)
    Employee.objects.filter(pk=someone.pk).update(
        joined_on=date(2026, 1, 1), left_on=date(2026, 6, 30)
    )
    edr = download(boss, run_id).content.decode().split("\r\n")[0]
    assert ",2026-07-16,2026-07-31,16," in edr
