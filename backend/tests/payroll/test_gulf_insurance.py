from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from apps.accounting.models import JournalEntry
from apps.hr import services as hr
from apps.hr.models import HrSettings, SalaryComponent
from apps.payroll import gratuity
from apps.payroll.models import ContributionRate, TaxTable
from tests.conftest import Member
from tests.payroll.test_payroll import boss, contract, person, post, work_out  # noqa: F401

pytestmark = pytest.mark.django_db
D = Decimal
# Housing counts for GOSI; transport doesn't.
PARTS = [
    hr.ComponentInput("Housing", "earning", D("2500"), None, insurable=True),
    hr.ComponentInput("Transport", "earning", D("1000"), None),
]
NEW_SYSTEM = date(2024, 7, 3)


def gulf(member: Member, country: str) -> None:
    TaxTable.objects.all().delete()
    HrSettings.objects.create(holiday_country=country, weekend=[4, 5])
    gratuity.fill_official(member.user)


def rate(scheme: str, employer: str, employee: str, **extra: Any) -> ContributionRate:
    values: dict[str, Any] = {
        "scheme": scheme,
        "starts_on": date(2024, 1, 1),
        "employer_percent": D(employer),
        "employee_percent": D(employee),
        "on_insurable": True,
        "source": "Invented test figures",
        **extra,
    }
    row: ContributionRate = ContributionRate.objects.create(**values)
    return row


def saudi_rates() -> None:
    rate("gosi_annuities", "9", "9", applies_to="nationals", wage_cap=D(45000), wage_floor=D(1500))
    rate(
        "gosi_annuities",
        "9.5",
        "9.5",
        applies_to="nationals",
        first_insured_from=NEW_SYSTEM,
        wage_cap=D(45000),
        wage_floor=D(1500),
    )
    rate("gosi_saned", "0.75", "0.75", applies_to="nationals", wage_cap=D(45000))
    rate("gosi_hazards", "2", "0", wage_cap=D(45000))


def schemes(slip: dict[str, Any]) -> dict[str, tuple[str, str, str]]:
    return {c["scheme"]: (c["base"], c["employer"], c["employee"]) for c in slip["contributions"]}


def test_gosi_by_nationality_and_system(boss: Member) -> None:  # noqa: F811
    gulf(boss, "SA")
    saudi_rates()
    old = person("S1", joined=date(2020, 1, 1), nationality="SA")
    new = person("S2", joined=date(2025, 1, 1), nationality="SA")
    expat = person("X1", joined=date(2020, 1, 1), nationality="PK")
    for worker in (old, new, expat):
        contract(boss, worker, "10000", starts=worker.joined_on, parts=PARTS)
    slips = {s["employee_code"]: s for s in work_out(boss).json()["payslips"]}
    # Basic 10,000 plus housing 2,500; transport is left out.
    assert schemes(slips["S1"]) == {
        "gosi_annuities": ("12500.00", "1125.00", "1125.00"),
        "gosi_saned": ("12500.00", "93.75", "93.75"),
        "gosi_hazards": ("12500.00", "250.00", "0.00"),
    }
    assert schemes(slips["S2"])["gosi_annuities"] == ("12500.00", "1187.50", "1187.50")
    assert schemes(slips["X1"]) == {"gosi_hazards": ("12500.00", "250.00", "0.00")}
    lines = [(line["name"], line["amount"]) for line in slips["S1"]["lines"]]
    assert ("GOSI annuities", "1125.00") in lines
    assert ("GOSI SANED", "93.75") in lines
    assert all(name != "GOSI occupational hazards" for name, _ in lines)


def test_the_first_insured_date_beats_joining(boss: Member) -> None:  # noqa: F811
    gulf(boss, "SA")
    saudi_rates()
    worker = person(
        "S3", joined=date(2025, 1, 1), nationality="SA", insured_since=date(2019, 5, 1)
    )
    contract(boss, worker, "10000", starts=worker.joined_on)
    slip = work_out(boss).json()["payslips"][0]
    assert schemes(slip)["gosi_annuities"] == ("10000.00", "900.00", "900.00")


def test_a_low_wage_is_charged_on_the_floor(boss: Member) -> None:  # noqa: F811
    gulf(boss, "SA")
    saudi_rates()
    contract(boss, person("S4", joined=date(2020, 1, 1), nationality="SA"), "1000")
    slip = work_out(boss).json()["payslips"][0]
    assert schemes(slip)["gosi_annuities"][0] == "1500.00"


def test_the_uae_pension_is_for_nationals_and_booked(boss: Member) -> None:  # noqa: F811
    gulf(boss, "AE")
    rate("gpssa", "15", "11", applies_to="nationals", wage_cap=D(70000))
    emirati = person("A1", joined=date(2020, 1, 1), nationality="AE")
    expat = person("X2", joined=date(2020, 1, 1), nationality="IN")
    contract(boss, emirati, "20000", starts=emirati.joined_on, parts=PARTS)
    contract(boss, expat, "20000", starts=expat.joined_on, parts=PARTS)
    run = work_out(boss).json()
    slips = {s["employee_code"]: s for s in run["payslips"]}
    assert schemes(slips["A1"]) == {"gpssa": ("22500.00", "3375.00", "2475.00")}
    assert slips["X2"]["contributions"] == []
    assert post(boss, run["id"]).json()["posted"] is True
    entry = JournalEntry.objects.get(source_type="payroll_run")
    roles = {line.account.role: (line.debit, line.credit) for line in entry.lines.all()}
    assert roles["employer_contributions"] == (D("3375.00"), D("0.00"))
    assert roles["contributions_payable"] == (D("0.00"), D("5850.00"))


def test_no_gulf_rate_means_nothing_is_charged(boss: Member) -> None:  # noqa: F811
    gulf(boss, "SA")
    contract(boss, person("S5", joined=date(2020, 1, 1), nationality="SA"), "10000")
    reply = work_out(boss)
    assert reply.status_code == 200
    assert reply.json()["payslips"][0]["contributions"] == []


def test_the_new_rate_fields_are_kept(boss: Member) -> None:  # noqa: F811
    client = boss.client()
    body = {
        "scheme": "gosi_annuities",
        "starts_on": "2026-07-01",
        "employer_percent": "10",
        "employee_percent": "10",
        "on_insurable": True,
        "wage_cap": "45000",
        "wage_floor": "1500",
        "applies_to": "nationals",
        "first_insured_from": "2024-07-03",
        "source": "GOSI statement",
    }
    made = client.post("/api/payroll/contribution-rates/", body, format="json")
    assert made.status_code == 201, made.content
    pk = made.json()["id"]
    plain = {k: v for k, v in body.items() if k not in ("applies_to", "first_insured_from")}
    changed = client.put(f"/api/payroll/contribution-rates/{pk}/", plain, format="json").json()
    assert (changed["applies_to"], changed["first_insured_from"]) == ("all", None)
    wrong = client.post(
        "/api/payroll/contribution-rates/",
        {**body, "starts_on": "2026-08-01", "wage_floor": "50000"},
        format="json",
    )
    assert wrong.status_code == 400


def test_a_pay_part_can_count_for_social_insurance(boss: Member) -> None:  # noqa: F811
    body = {
        "name": "Gulf staff",
        "components": [
            {"name": "Housing", "kind": "earning", "amount": "2500", "insurable": True},
            {"name": "Transport", "kind": "earning", "amount": "1000"},
        ],
    }
    reply = boss.client().post("/api/hr/salary-structures/", body, format="json")
    assert reply.status_code == 201, reply.content
    parts = {c["name"]: c["insurable"] for c in reply.json()["components"]}
    assert parts == {"Housing": True, "Transport": False}
    assert SalaryComponent.objects.get(name="Housing").insurable
