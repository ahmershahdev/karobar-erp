from typing import Any

import pytest

from apps.hr.models import Employee, HrSettings
from apps.payroll.models import OpeningPay
from apps.tenancy.models import AuditEvent
from tests.conftest import Member
from tests.payroll.test_payroll import STANDARD, boss, contract, person, post, work_out  # noqa: F401

pytestmark = pytest.mark.django_db


def opening(
    member: Member, worker: Employee, taxable: str, tax: str, month: str = "2026-11-01"
) -> Any:
    body = {
        "employee": worker.pk,
        "month": month,
        "taxable": taxable,
        "tax": tax,
        "note": "Jul-Oct",
    }
    return member.client().post("/api/payroll/opening-pay/", body, format="json")


def test_pay_from_before_counts_in_the_years_tax(boss: Member) -> None:  # noqa: F811
    worker = person()
    contract(boss, worker, "50000", parts=STANDARD)
    # Without it, November sees only 8 months of 72,500: 580,000, under the tax-free 600,000.
    assert work_out(boss, "2026-11-01").json()["payslips"][0]["tax"] == "0.00"
    made = opening(boss, worker, "290000", "0")
    assert made.status_code == 201, made.content
    assert made.json()["year_starts"] == "2026-07-01"
    slip = work_out(boss, "2026-11-01").json()["payslips"][0]
    # 290,000 before plus 8 months of 72,500 is 870,000: 2,700 for the year, over 8 months.
    assert slip["projected_income"] == "870000.00"
    assert slip["tax"] == "337.50"


def test_tax_already_withheld_before_is_taken_off(boss: Member) -> None:  # noqa: F811
    worker = person()
    contract(boss, worker, "150000")
    opening(boss, worker, "600000", "24000")
    slip = work_out(boss, "2026-11-01").json()["payslips"][0]
    # 600,000 plus 8 months of 150,000 is 1,800,000: 72,000 a year, 24,000 already withheld.
    assert slip["tax"] == "6000.00"


def test_saving_again_replaces_the_figures_and_is_audited(boss: Member) -> None:  # noqa: F811
    worker = person()
    first = opening(boss, worker, "100000", "0").json()["id"]
    again = opening(boss, worker, "120000", "500", month="2027-03-01")
    assert again.json()["id"] == first
    assert OpeningPay.objects.get().taxable == 120000
    listed = boss.client().get("/api/payroll/opening-pay/?month=2026-08-01").json()
    assert [row["employee_code"] for row in listed] == ["E1"]
    assert boss.client().get("/api/payroll/opening-pay/?month=2027-08-01").json() == []
    actions = list(
        AuditEvent.objects.filter(model="payroll.OpeningPay").values_list("action", flat=True)
    )
    assert actions == [AuditEvent.Action.CREATE, AuditEvent.Action.UPDATE]
    assert boss.client().delete(f"/api/payroll/opening-pay/{first}/").status_code == 204
    assert not OpeningPay.objects.exists()


def test_strange_figures_are_refused(boss: Member) -> None:  # noqa: F811
    worker = person()
    assert opening(boss, worker, "1000", "2000").status_code == 400
    assert opening(boss, worker, "-1", "0").status_code == 400
    assert boss.client().get("/api/payroll/opening-pay/?month=soon").status_code == 400


def test_figures_are_fixed_once_the_person_is_paid_here(boss: Member) -> None:  # noqa: F811
    worker = person()
    contract(boss, worker, "150000")
    pk = opening(boss, worker, "600000", "24000").json()["id"]
    post(boss, work_out(boss, "2026-11-01").json()["id"])
    reply = opening(boss, worker, "700000", "24000")
    assert reply.status_code == 400
    assert "posted pay" in reply.json()["detail"]
    assert boss.client().delete(f"/api/payroll/opening-pay/{pk}/").status_code == 400
    # Another tax year is still open.
    assert opening(boss, worker, "0", "0", month="2027-08-01").status_code == 201


def test_a_country_without_salary_tax_needs_none(boss: Member) -> None:  # noqa: F811
    HrSettings.objects.create(holiday_country="AE", weekend=[5, 6])
    reply = opening(boss, person(), "1000", "0")
    assert reply.status_code == 400
    assert "no tax on salaries" in reply.json()["detail"]
    assert boss.client().get("/api/payroll/opening-pay/?month=2026-11-01").json() == []


def test_figures_can_be_removed_after_moving_to_a_country_without_salary_tax(
    boss: Member,  # noqa: F811
) -> None:
    pk = opening(boss, person(), "1000", "0").json()["id"]
    HrSettings.objects.create(holiday_country="SA", weekend=[4, 5])
    assert boss.client().delete(f"/api/payroll/opening-pay/{pk}/").status_code == 204
