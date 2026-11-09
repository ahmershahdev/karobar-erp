import importlib
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.apps import apps as django_apps

from apps.accounting.models import Account, JournalEntry
from apps.hr.models import HrSettings
from apps.payroll import contributions, documents
from apps.payroll.models import ContributionRate, MinimumWage, Payslip
from apps.tenancy.models import AuditEvent
from tests.conftest import Member
from tests.factories import create_membership, create_role
from tests.payroll.test_payroll import boss, contract, person, post, work_out  # noqa: F401

pytestmark = pytest.mark.django_db
D = Decimal


def eobi(province: str = "", starts: date = date(2026, 7, 1)) -> ContributionRate:
    row: ContributionRate = ContributionRate.objects.create(
        scheme="eobi",
        province=province,
        starts_on=starts,
        employer_percent=D(5),
        employee_percent=D(1),
        on_minimum_wage=True,
        source="Test figures, invented",
    )
    return row


def social_security(province: str, cap: str = "43000") -> ContributionRate:
    row: ContributionRate = ContributionRate.objects.create(
        scheme="social_security",
        province=province,
        starts_on=date(2026, 7, 1),
        employer_percent=D(6),
        employee_percent=D(0),
        on_minimum_wage=False,
        wage_cap=D(cap),
        source="Test figures, invented",
    )
    return row


def wage(province: str, amount: str, starts: date = date(2026, 7, 1)) -> MinimumWage:
    row: MinimumWage = MinimumWage.objects.create(
        province=province, starts_on=starts, amount=D(amount), source="Test figures, invented"
    )
    return row


def problem(reply: Any) -> str:
    assert reply.status_code == 400, reply.content
    detail: str = reply.json()["detail"]
    return detail


# The shipped figures


def test_only_officially_notified_minimum_wages_are_filled_in(boss: Member) -> None:  # noqa: F811
    reply = boss.client().post("/api/payroll/contributions/fill/")
    assert reply.json() == {"added": 2}
    rows = {(w.province, w.starts_on, w.amount) for w in MinimumWage.objects.all()}
    assert rows == {
        ("ICT", date(2026, 7, 1), D("40700.00")),
        ("SD", date(2026, 7, 1), D("43000.00")),
    }
    assert "ADLW 8(20)-ICT/2024-934" in MinimumWage.objects.get(province="ICT").source
    assert "SO(L-II)/13-3/2016-II" in MinimumWage.objects.get(province="SD").source
    # No EOBI or social security rate ships: none was found in an official text.
    assert not ContributionRate.objects.exists()
    assert boss.client().post("/api/payroll/contributions/fill/").json() == {"added": 0}


def test_shipped_rates_would_be_filled_in_too(
    boss: Member,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rate = {
        "scheme": "social_security",
        "province": "SD",
        "starts_on": "2026-07-01",
        "employer_percent": "6",
        "employee_percent": "0",
        "on_minimum_wage": False,
        "wage_cap": "43000",
        "source": "Invented",
    }
    monkeypatch.setattr(contributions, "official", lambda: {"minimum_wages": [], "rates": [rate]})
    assert contributions.fill_official(boss.user) == 1
    assert contributions.fill_official(boss.user) == 0
    assert ContributionRate.objects.get().wage_cap == D("43000.00")


# Keeping rates and minimum wages


def test_rates_and_wages_are_kept_as_data_and_audited(boss: Member) -> None:  # noqa: F811
    client = boss.client()
    body = {
        "scheme": "eobi",
        "starts_on": "2026-07-01",
        "employer_percent": "5",
        "employee_percent": "1",
        "on_minimum_wage": True,
        "source": "EOBI circular",
    }
    made = client.post("/api/payroll/contribution-rates/", body, format="json")
    assert made.status_code == 201, made.content
    pk = made.json()["id"]
    assert made.json()["province"] == ""
    changed = client.put(
        f"/api/payroll/contribution-rates/{pk}/",
        {**body, "employer_percent": "6"},
        format="json",
    )
    assert changed.status_code == 200, changed.content
    assert changed.json()["employer_percent"] == "6.00"
    model = "payroll.ContributionRate"
    assert AuditEvent.objects.filter(model=model, object_id=str(pk)).count() == 2
    assert client.delete(f"/api/payroll/contribution-rates/{pk}/").status_code == 204

    wage_body = {"province": "PB", "starts_on": "2025-07-01", "amount": "40000", "source": "N"}
    made = client.post("/api/payroll/minimum-wages/", wage_body, format="json")
    assert made.status_code == 201, made.content
    pk = made.json()["id"]
    changed = client.put(
        f"/api/payroll/minimum-wages/{pk}/", {**wage_body, "amount": "41000"}, format="json"
    )
    assert changed.json()["amount"] == "41000.00"
    again = client.post("/api/payroll/minimum-wages/", wage_body, format="json")
    assert "already one starting" in problem(again)
    assert client.delete(f"/api/payroll/minimum-wages/{pk}/").status_code == 204


@pytest.mark.parametrize(
    "change",
    [
        {"employer_percent": "101"},
        {"wage_cap": "0"},
        {"on_minimum_wage": True, "wage_cap": "40000"},
        {"scheme": "pension"},
        {"province": "XX"},
    ],
)
def test_strange_rates_are_refused(boss: Member, change: dict[str, Any]) -> None:  # noqa: F811
    body = {
        "scheme": "social_security",
        "province": "PB",
        "starts_on": "2026-07-01",
        "employer_percent": "6",
        "employee_percent": "0",
        "source": "N",
        **change,
    }
    reply = boss.client().post("/api/payroll/contribution-rates/", body, format="json")
    assert reply.status_code == 400
    assert not ContributionRate.objects.exists()


def test_rates_need_payroll_rights(boss: Member) -> None:  # noqa: F811

    joined = create_membership(role=create_role(permissions={"hr": ["view"]}))
    hr_only = Member(user=joined.user, tenant=boss.tenant, membership=joined).client()
    assert hr_only.get("/api/payroll/contribution-rates/").status_code == 403
    assert hr_only.post("/api/payroll/contributions/fill/").status_code == 403


# Payroll


def test_eobi_on_the_minimum_wage_and_social_security_up_to_a_ceiling(boss: Member) -> None:  # noqa: F811
    eobi()
    social_security("SD")
    wage("SD", "43000")
    worker = person(province="SD", pays_eobi=True, pays_social_security=True)
    contract(boss, worker, "100000")
    slip = work_out(boss).json()["payslips"][0]
    assert [(line["name"], line["amount"]) for line in slip["lines"]] == [
        ("Basic", "100000.00"),
        ("EOBI", "430.00"),
    ]
    assert slip["contributions"] == [
        {
            "scheme": "eobi",
            "base": "43000.00",
            "employer_percent": "5.00",
            "employee_percent": "1.00",
            "employer": "2150.00",
            "employee": "430.00",
        },
        {
            "scheme": "social_security",
            "base": "43000.00",
            "employer_percent": "6.00",
            "employee_percent": "0.00",
            "employer": "2580.00",
            "employee": "0.00",
        },
    ]
    assert (slip["employee_contributions"], slip["employer_contributions"]) == (
        "430.00",
        "4730.00",
    )
    # The staff's share doesn't lower the taxable pay.
    assert slip["taxable"] == "100000.00"
    assert D(slip["net"]) == D("100000") - D("430") - D(slip["tax"])


def test_a_province_rate_wins_over_the_one_for_everywhere(boss: Member) -> None:  # noqa: F811
    eobi()
    ContributionRate.objects.create(
        scheme="eobi",
        province="ICT",
        starts_on=date(2026, 1, 1),
        employer_percent=D(4),
        employee_percent=D(0),
        on_minimum_wage=True,
        source="Invented",
    )
    wage("ICT", "40700")
    wage("ICT", "37000", starts=date(2025, 7, 1))
    # A later rate isn't in force yet in July.
    eobi(starts=date(2026, 8, 1))
    contract(boss, person(province="ICT", pays_eobi=True), "60000")
    slip = work_out(boss).json()["payslips"][0]
    assert slip["contributions"][0]["employer"] == "1628.00"
    assert slip["employee_contributions"] == "0.00"


def test_people_who_dont_pay_are_left_alone(boss: Member) -> None:  # noqa: F811
    contract(boss, person(province="PB"), "60000")
    slip = work_out(boss).json()["payslips"][0]
    assert slip["contributions"] == []
    assert slip["employer_contributions"] == "0.00"


def test_missing_figures_are_named(boss: Member) -> None:  # noqa: F811
    contract(boss, person("E1", province="PB", pays_eobi=True, pays_social_security=True), "60000")
    eobi()
    detail = problem(work_out(boss))
    assert "Contributions screen" in detail
    assert "minimum wage in Punjab" in detail
    assert "Social security rate in Punjab" in detail


def test_someone_without_a_province_is_named(boss: Member) -> None:  # noqa: F811
    eobi()
    contract(boss, person("E7", pays_eobi=True), "60000")
    detail = problem(work_out(boss))
    assert "no province" in detail
    assert detail.endswith("E7")


def test_a_share_bigger_than_the_pay_names_the_person(boss: Member) -> None:  # noqa: F811
    eobi()
    wage("PB", "40000")
    ContributionRate.objects.filter(scheme="eobi").update(employee_percent=D(100))
    contract(boss, person("E3", province="PB", pays_eobi=True), "1000")
    assert "E3" in problem(work_out(boss))


def test_posting_books_both_shares_as_owed(boss: Member) -> None:  # noqa: F811
    eobi()
    social_security("SD")
    wage("SD", "43000")
    contract(boss, person(province="SD", pays_eobi=True, pays_social_security=True), "30000")
    run = work_out(boss).json()
    assert (run["employee_contributions"], run["employer_contributions"]) == ("430.00", "3950.00")
    assert post(boss, run["id"]).json()["posted"] is True
    entry = JournalEntry.objects.get(source_type="payroll_run")
    amounts = {
        line.account.role: (line.debit, line.credit)
        for line in entry.lines.select_related("account")
    }
    assert amounts["salaries"] == (D("30000.00"), D("0.00"))
    assert amounts["employer_contributions"] == (D("3950.00"), D("0.00"))
    assert amounts["contributions_payable"] == (D("0.00"), D("4380.00"))
    assert amounts["salaries_payable"] == (D("0.00"), D("29570.00"))
    assert "payroll_deductions" not in amounts


def test_a_rate_change_after_working_out_is_shown_before_posting(boss: Member) -> None:  # noqa: F811
    rate = eobi()
    wage("ICT", "40700")
    contract(boss, person(province="ICT", pays_eobi=True), "60000")
    run = work_out(boss).json()
    rate.employer_percent = D(6)
    rate.save()
    reply = post(boss, run["id"]).json()
    assert reply["posted"] is False
    assert reply["run"]["employer_contributions"] == "2442.00"


def test_a_payslip_shows_the_employers_share(boss: Member) -> None:  # noqa: F811
    eobi()
    wage("ICT", "40700")
    contract(boss, person(province="ICT", pays_eobi=True), "60000")
    post(boss, work_out(boss).json()["id"])
    slip = Payslip.objects.get()
    english = documents.payslip_html(slip, "en")
    for text in ("EOBI", "2,035.00", "407.00", "40,700.00"):
        assert text in english
    assert "ای او بی آئی" in documents.payslip_html(slip, "ur")


# Employees and settings


def test_a_new_employee_starts_in_the_default_province(boss: Member) -> None:  # noqa: F811
    client = boss.client()
    assert (
        client.patch("/api/hr/settings/", {"default_province": "KP"}, format="json").status_code
        == 200
    )
    assert HrSettings.objects.get().default_province == "KP"
    body = {"code": "N1", "full_name": "Invented New", "joined_on": "2026-07-01"}
    made = client.post("/api/hr/employees/", body, format="json").json()
    assert (made["province"], made["pays_eobi"], made["pays_social_security"]) == (
        "KP",
        False,
        False,
    )
    chosen = client.post(
        "/api/hr/employees/",
        {**body, "code": "N2", "province": "SD", "pays_eobi": True},
        format="json",
    ).json()
    assert (chosen["province"], chosen["pays_eobi"]) == ("SD", True)


# Books


def test_new_businesses_have_accounts_for_contributions(boss: Member) -> None:  # noqa: F811
    owed = Account.objects.get(role="contributions_payable")
    cost = Account.objects.get(role="employer_contributions")
    assert (owed.code, owed.type, cost.code, cost.type) == ("2180", "liability", "6150", "expense")


def test_older_businesses_get_contribution_accounts(boss: Member) -> None:  # noqa: F811
    Account.objects.filter(role__in=["contributions_payable", "employer_contributions"]).delete()
    Account.objects.create(code="2180", name="Taken", type="liability")
    migration = importlib.import_module("apps.accounting.migrations.0009_contribution_accounts")
    migration.add_roles(django_apps, None)
    migration.add_roles(django_apps, None)
    owed = Account.objects.get(role="contributions_payable")
    cost = Account.objects.get(role="employer_contributions")
    assert (owed.code, owed.parent.code if owed.parent else None) == ("2181", "2100")
    assert (cost.code, cost.parent.code if cost.parent else None) == ("6150", "6000")
