import importlib
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.apps import apps as django_apps

from apps.accounting.models import Account, JournalEntry
from apps.core.gratuity import Rule, award
from apps.hr import services as hr
from apps.hr.models import Attendance, Employee, HrSettings
from apps.payroll import gratuity
from apps.payroll.models import GratuityPayout, GratuityRule, PayrollRun, Payslip, TaxTable
from tests.conftest import Member
from tests.factories import create_membership, create_role
from tests.payroll.test_payroll import boss, contract, person, post, work_out  # noqa: F401

pytestmark = pytest.mark.django_db
D = Decimal
ALLOWANCE = [hr.ComponentInput("Housing", "earning", D("2500"), None)]
UAE = Rule(D(5), D(21), D(30), min_years=D(1), cap_months=D(24))


def gulf(member: Member, country: str = "AE") -> None:
    TaxTable.objects.all().delete()
    HrSettings.objects.create(holiday_country=country, weekend=[5, 6])
    assert gratuity.fill_official(member.user) == 1


def entry_lines(source: str) -> dict[str | None, tuple[Decimal, Decimal]]:
    entry = JournalEntry.objects.get(source_type=source)
    return {
        line.account.role: (line.debit, line.credit)
        for line in entry.lines.select_related("account")
    }


def bank() -> Account:
    found: Account = Account.objects.get(role="bank")
    return found


def leave(worker: Employee, on: date) -> None:
    Employee.objects.filter(pk=worker.pk).update(left_on=on)
    worker.contracts.update(ends_on=on)
    worker.refresh_from_db()


def pay_out(member: Member, worker: Employee, reason: str, on: str = "2026-08-20") -> Any:
    body = {"reason": reason, "paid_on": on, "paid_from": bank().pk}
    return member.client().post(
        f"/api/payroll/employees/{worker.pk}/gratuity/pay/", body, format="json"
    )


# The rules


def test_the_uae_and_saudi_rules_ship_with_their_law(boss: Member) -> None:  # noqa: F811
    gulf(boss)
    rule = GratuityRule.objects.get()
    assert (rule.country, rule.starts_on, rule.first_days, rule.wage) == (
        "AE",
        date(2022, 2, 2),
        D("21.00"),
        "basic",
    )
    assert "Article 51" in rule.source
    assert boss.client().post("/api/payroll/gratuity-rules/fill/").json() == {"added": 0}
    HrSettings.objects.update(holiday_country="SA")
    assert gratuity.fill_official(boss.user) == 1
    saudi = GratuityRule.objects.get(country="SA")
    assert saudi.wage == "full"
    assert saudi.resignation[1] == {"years": "5", "share": "2/3", "after": True}
    HrSettings.objects.update(holiday_country="PK")
    assert gratuity.fill_official(boss.user) == 0


def test_a_rule_is_kept_as_data_and_audited(boss: Member) -> None:  # noqa: F811
    client = boss.client()
    body = {
        "country": "SA",
        "starts_on": "2027-01-01",
        "first_years": "5",
        "first_days": "15",
        "later_days": "30",
        "wage": "full",
        "resignation": [{"years": "2", "share": "1/3"}],
        "source": "Invented amendment",
    }
    made = client.post("/api/payroll/gratuity-rules/", body, format="json")
    assert made.status_code == 201, made.content
    pk = made.json()["id"]
    assert made.json()["resignation"] == [{"years": "2.00", "share": "1/3", "after": False}]
    changed = client.put(
        f"/api/payroll/gratuity-rules/{pk}/", {**body, "cap_months": "24"}, format="json"
    )
    assert changed.json()["cap_months"] == "24.00"
    again = client.put(f"/api/payroll/gratuity-rules/{pk}/", body, format="json")
    assert again.json()["cap_months"] is None
    assert client.patch(f"/api/payroll/gratuity-rules/{pk}/", {}).status_code == 405
    dup = client.post("/api/payroll/gratuity-rules/", body, format="json")
    assert "already a rule" in dup.json()["detail"]
    assert client.delete(f"/api/payroll/gratuity-rules/{pk}/").status_code == 204


@pytest.mark.parametrize(
    "change",
    [
        {"first_days": "-1"},
        {"cap_months": "0"},
        {"resignation": [{"years": "2", "share": "3/2"}]},
        {"resignation": [{"years": "5", "share": "2/3"}, {"years": "2", "share": "1/3"}]},
        {"resignation": [{"years": "2", "share": "1/0"}]},
        {"country": "PK"},
        {"wage": "gross"},
    ],
)
def test_strange_rules_are_refused(boss: Member, change: dict[str, Any]) -> None:  # noqa: F811
    body = {
        "country": "AE",
        "starts_on": "2027-01-01",
        "first_years": "5",
        "first_days": "21",
        "later_days": "30",
        "wage": "basic",
        "source": "N",
        **change,
    }
    reply = boss.client().post("/api/payroll/gratuity-rules/", body, format="json")
    assert reply.status_code == 400
    assert not GratuityRule.objects.exists()


# Building up the provision


def test_a_uae_month_books_the_gratuity_built_up(boss: Member) -> None:  # noqa: F811
    gulf(boss)
    worker = person(joined=date(2025, 1, 1))
    contract(boss, worker, "10000", starts=date(2025, 1, 1), parts=ALLOWANCE)
    july = work_out(boss).json()
    slip = july["payslips"][0]
    # Basic only: the housing allowance doesn't count in the UAE.
    expected = award(UAE, (date(2026, 7, 31) - date(2025, 1, 1)).days + 1, D(10000)).full
    assert (slip["gratuity_accrued"], slip["gratuity_change"]) == (str(expected),) * 2
    assert post(boss, july["id"]).json()["posted"] is True
    lines = entry_lines("payroll_run")
    assert lines["gratuity_expense"] == (expected, D("0.00"))
    assert lines["gratuity_provision"] == (D("0.00"), expected)

    august = work_out(boss, "2026-08-01").json()["payslips"][0]
    grown = award(UAE, (date(2026, 8, 31) - date(2025, 1, 1)).days + 1, D(10000)).full
    assert D(august["gratuity_change"]) == grown - expected


def test_nothing_builds_up_in_the_first_year_in_the_uae(boss: Member) -> None:  # noqa: F811
    gulf(boss)
    contract(boss, person(joined=date(2026, 1, 1)), "10000", starts=date(2026, 1, 1))
    assert work_out(boss).json()["payslips"][0]["gratuity_accrued"] == "0.00"


def test_unpaid_days_are_left_out_of_uae_service(boss: Member) -> None:  # noqa: F811
    gulf(boss)
    worker = person(joined=date(2025, 1, 1))
    contract(boss, worker, "10000", starts=date(2025, 1, 1))
    Attendance.objects.create(employee=worker, on=date(2026, 7, 6), status="absent")
    slip = work_out(boss).json()["payslips"][0]
    days = (date(2026, 7, 31) - date(2025, 1, 1)).days
    assert slip["gratuity_accrued"] == str(award(UAE, days, D(10000)).full)


def test_uae_nationals_have_no_gratuity(boss: Member) -> None:  # noqa: F811
    gulf(boss)
    contract(boss, person(joined=date(2020, 1, 1), nationality="AE"), "10000")
    run = work_out(boss).json()
    assert run["payslips"][0]["gratuity_accrued"] == "0.00"
    assert run["gratuity_change"] == "0.00"


def test_saudi_gratuity_counts_the_allowances(boss: Member) -> None:  # noqa: F811
    gulf(boss, "SA")
    contract(
        boss, person(joined=date(2024, 7, 1)), "10000", starts=date(2024, 7, 1), parts=ALLOWANCE
    )
    slip = work_out(boss).json()["payslips"][0]
    days = (date(2026, 7, 31) - date(2024, 7, 1)).days + 1
    rule = gratuity.as_rule(GratuityRule.objects.get())
    assert slip["gratuity_accrued"] == str(award(rule, days, D(12500)).full)


def test_without_a_rule_a_gulf_month_stops(boss: Member) -> None:  # noqa: F811
    gulf(boss)
    GratuityRule.objects.all().delete()
    contract(boss, person(), "10000")
    reply = work_out(boss)
    assert reply.status_code == 400
    assert "End of service screen" in reply.json()["detail"]


def test_gulf_months_are_posted_in_order(boss: Member) -> None:  # noqa: F811
    gulf(boss)
    contract(boss, person(joined=date(2025, 1, 1)), "10000", starts=date(2025, 1, 1))
    work_out(boss)
    august = work_out(boss, "2026-08-01").json()["id"]
    assert post(boss, august).status_code == 400


def test_a_pakistan_business_builds_up_no_gratuity(boss: Member) -> None:  # noqa: F811
    contract(boss, person(joined=date(2020, 1, 1)), "150000")
    run = work_out(boss).json()
    assert run["gratuity_change"] == "0.00"


# Paying it out


def leaver(member: Member, country: str = "AE", joined: date = date(2023, 8, 1)) -> Employee:
    gulf(member, country)
    worker = person(joined=joined)
    contract(member, worker, "9000", starts=joined)
    post(member, work_out(member).json()["id"])
    leave(worker, date(2026, 8, 15))
    post(member, work_out(member, "2026-08-01").json()["id"])
    return worker


def test_a_leaver_sees_what_each_reason_would_pay(boss: Member) -> None:  # noqa: F811
    worker = leaver(boss, "SA")
    quote = boss.client().get(f"/api/payroll/employees/{worker.pk}/gratuity/").json()
    days = (date(2026, 8, 15) - date(2023, 8, 1)).days + 1
    rule = gratuity.as_rule(GratuityRule.objects.get())
    assert quote["service_days"] == days
    assert quote["if_ended"] == str(award(rule, days, D(9000)).amount)
    assert quote["if_resigned"] == str(award(rule, days, D(9000), resigned=True).amount)
    assert quote["accrued"] == quote["if_ended"]
    assert quote["payout"] is None


def test_a_saudi_resignation_gives_back_part_of_the_provision(boss: Member) -> None:  # noqa: F811
    worker = leaver(boss, "SA")
    provision = Payslip.objects.filter(employee=worker).order_by("run__month").last()
    assert provision is not None
    reply = pay_out(boss, worker, "resigned")
    assert reply.status_code == 201, reply.content
    payout = GratuityPayout.objects.get()
    assert payout.provision == provision.gratuity_accrued
    assert payout.amount == (payout.full * payout.share).quantize(D("0.01"))
    lines = entry_lines("gratuity_payout")
    assert lines["gratuity_provision"] == (payout.provision, D("0.00"))
    assert lines["gratuity_expense"] == (D("0.00"), payout.provision - payout.amount)
    assert lines["bank"] == (D("0.00"), payout.amount)
    assert pay_out(boss, worker, "resigned").status_code == 400
    quote = boss.client().get(f"/api/payroll/employees/{worker.pk}/gratuity/").json()
    assert quote["payout"]["amount"] == str(payout.amount)


def test_a_uae_payout_matches_the_provision(boss: Member) -> None:  # noqa: F811
    worker = leaver(boss)
    assert pay_out(boss, worker, "ended").status_code == 201
    payout = GratuityPayout.objects.get()
    assert payout.amount == payout.provision
    assert "gratuity_expense" not in entry_lines("gratuity_payout")


def test_a_month_with_a_paid_gratuity_cant_be_undone(boss: Member) -> None:  # noqa: F811
    worker = leaver(boss)
    pay_out(boss, worker, "ended")
    august = PayrollRun.objects.get(month=date(2026, 8, 1))
    reply = boss.client().post(f"/api/payroll/runs/{august.pk}/reverse/", {}, format="json")
    assert "end-of-service gratuity" in reply.json()["detail"]


def test_a_payout_needs_a_leaver_with_the_last_month_posted(boss: Member) -> None:  # noqa: F811
    gulf(boss)
    worker = person(joined=date(2023, 8, 1))
    contract(boss, worker, "9000", starts=date(2023, 8, 1))
    assert "day this person left" in pay_out(boss, worker, "ended").json()["detail"]
    leave(worker, date(2026, 7, 15))
    assert "Post the payroll" in pay_out(boss, worker, "ended").json()["detail"]
    post(boss, work_out(boss).json()["id"])
    early = pay_out(boss, worker, "ended", on="2026-07-01")
    assert "before the day" in early.json()["detail"]
    body = {
        "reason": "ended",
        "paid_on": "2026-07-20",
        "paid_from": Account.objects.get(role="sales").pk,
    }
    wrong = boss.client().post(
        f"/api/payroll/employees/{worker.pk}/gratuity/pay/", body, format="json"
    )
    assert "cash or bank" in wrong.json()["detail"]


def test_a_national_has_no_payout(boss: Member) -> None:  # noqa: F811
    gulf(boss)
    worker = person(joined=date(2023, 8, 1), nationality="AE")
    contract(boss, worker, "9000", starts=date(2023, 8, 1))
    leave(worker, date(2026, 7, 15))
    post(boss, work_out(boss).json()["id"])
    assert "No end-of-service gratuity" in pay_out(boss, worker, "ended").json()["detail"]
    quote = boss.client().get(f"/api/payroll/employees/{worker.pk}/gratuity/").json()
    assert quote["if_ended"] is None


def test_paying_needs_the_right_to_post(boss: Member) -> None:  # noqa: F811
    worker = leaver(boss)
    joined = create_membership(role=create_role(permissions={"payroll": ["view", "create"]}))
    clerk = Member(user=joined.user, tenant=boss.tenant, membership=joined)
    assert clerk.client().get(f"/api/payroll/employees/{worker.pk}/gratuity/").status_code == 200
    assert pay_out(clerk, worker, "ended").status_code == 403


def test_a_rule_used_by_a_payout_stays(boss: Member) -> None:  # noqa: F811
    worker = leaver(boss)
    pay_out(boss, worker, "ended")
    rule = GratuityRule.objects.get()
    reply = boss.client().delete(f"/api/payroll/gratuity-rules/{rule.pk}/")
    assert "stays" in reply.json()["detail"]


# Books


def test_new_businesses_have_gratuity_accounts(boss: Member) -> None:  # noqa: F811
    owed = Account.objects.get(role="gratuity_provision")
    cost = Account.objects.get(role="gratuity_expense")
    assert (owed.code, owed.type, cost.code, cost.type) == ("2190", "liability", "6160", "expense")


def test_older_businesses_get_gratuity_accounts(boss: Member) -> None:  # noqa: F811
    Account.objects.filter(role__in=["gratuity_provision", "gratuity_expense"]).delete()
    migration = importlib.import_module("apps.accounting.migrations.0010_gratuity_accounts")
    migration.add_roles(django_apps, None)
    migration.add_roles(django_apps, None)
    assert Account.objects.get(role="gratuity_provision").code == "2190"
    assert Account.objects.get(role="gratuity_expense").code == "6160"
