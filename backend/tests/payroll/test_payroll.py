import importlib
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.apps import apps as django_apps

from apps.accounting import services as accounting
from apps.accounting.models import Account, FiscalPeriod, JournalEntry
from apps.core.salary_tax import Slab
from apps.hr import services as hr
from apps.hr.models import Attendance, Contract, Employee, HrSettings, LeaveRequest, LeaveType
from apps.payroll import documents, services
from apps.payroll.models import PayrollRun, Payslip, TaxTable
from apps.sales.documents import PdfUnavailableError
from apps.tenancy.context import tenant_context
from apps.tenancy.models import AuditEvent
from tests.conftest import Member, make_member
from tests.factories import create_membership, create_role

pytestmark = pytest.mark.django_db
D = Decimal

STANDARD = [
    hr.ComponentInput("House rent", "earning", None, D("45")),
    hr.ComponentInput("Medical", "earning", None, D("10"), taxable=False),
    hr.ComponentInput("Provident fund", "deduction", None, D("8.33")),
]


def books(member: Member) -> None:
    accounting.install_chart(member.tenant, member.user)
    accounting.create_fiscal_year(member.user, date(2026, 7, 1), date(2027, 6, 30))


@pytest.fixture
def boss(db: None) -> Iterator[Member]:
    member = make_member(owner=True)
    with tenant_context(member.tenant):
        books(member)
        services.fill_official(member.user)
        yield member


def plan(member: Member, parts: list[hr.ComponentInput] | None = None, name: str = "P") -> Any:
    return hr.save_structure(member.user, {"name": name}, parts or [])


def person(code: str = "E1", joined: date = date(2026, 1, 1), **extra: Any) -> Employee:
    worker: Employee = Employee.objects.create(
        code=code, full_name=f"Invented {code}", joined_on=joined, **extra
    )
    return worker


def contract(
    member: Member,
    worker: Employee,
    basic: str,
    starts: date = date(2026, 1, 1),
    ends: date | None = None,
    parts: list[hr.ComponentInput] | None = None,
) -> Contract:
    made: Contract = hr.save_contract(
        member.user,
        {
            "employee": worker,
            "structure": plan(member, parts, name=f"P{worker.code}{starts}"),
            "starts_on": starts,
            "ends_on": ends,
            "basic_salary": D(basic),
        },
    )
    return made


def work_out(member: Member, month: str = "2026-07-01") -> Any:
    return member.client().post("/api/payroll/runs/", {"month": month}, format="json")


def post(member: Member, run_id: int) -> Any:
    return member.client().post(f"/api/payroll/runs/{run_id}/post/")


def only_payslip(reply: Any) -> dict[str, Any]:
    assert reply.status_code == 200, reply.content
    slips: list[dict[str, Any]] = reply.json()["payslips"]
    assert len(slips) == 1
    return slips[0]


# Tax tables


def test_the_official_slabs_are_filled_in_once(boss: Member) -> None:
    table = TaxTable.objects.get()
    assert (table.country, table.starts_on, table.ends_on) == (
        "PK",
        date(2026, 7, 1),
        date(2027, 6, 30),
    )
    assert table.slabs.count() == 8
    assert "Finance Act 2026" in table.source
    assert services.fill_official(boss.user) == 0
    assert boss.client().post("/api/payroll/tax-tables/fill/").json() == {"added": 0}


def test_a_tax_table_is_kept_as_data_and_audited(boss: Member) -> None:
    body = {
        "country": "PK",
        "name": "Tax year 2028",
        "starts_on": "2027-07-01",
        "ends_on": "2028-06-30",
        "source": "Finance Act 2027",
        "slabs": [
            {"over": "0", "fixed": "0", "rate": "0"},
            {"over": "800000", "fixed": "0", "rate": "2"},
        ],
    }
    made = boss.client().post("/api/payroll/tax-tables/", body, format="json")
    assert made.status_code == 201, made.content
    pk = made.json()["id"]
    body["slabs"] = [{"over": "0", "fixed": "0", "rate": "0"}]
    changed = boss.client().put(f"/api/payroll/tax-tables/{pk}/", body, format="json")
    assert changed.status_code == 200, changed.content
    assert len(changed.json()["slabs"]) == 1
    assert AuditEvent.objects.filter(model="payroll.TaxTable", object_id=str(pk)).count() == 2
    assert boss.client().delete(f"/api/payroll/tax-tables/{pk}/").status_code == 204


@pytest.mark.parametrize(
    "change",
    [
        {"starts_on": "2027-01-01", "ends_on": "2027-12-31"},  # Overlaps the 2027 table.
        {"slabs": [{"over": "100", "fixed": "0", "rate": "0"}]},
        {"slabs": [{"over": "0", "fixed": "0", "rate": "101"}]},
        {"slabs": []},
        {"slabs": [{"over": str(n), "fixed": "0", "rate": "0"} for n in range(21)]},
        {"ends_on": "2027-06-30"},  # Ends before it starts.
        {"country": "US"},
    ],
)
def test_strange_tax_tables_are_refused(boss: Member, change: dict[str, Any]) -> None:
    body = {
        "country": "PK",
        "name": "X",
        "starts_on": "2027-07-01",
        "ends_on": "2028-06-30",
        "source": "X",
        "slabs": [{"over": "0", "fixed": "0", "rate": "0"}],
        **change,
    }
    assert boss.client().post("/api/payroll/tax-tables/", body, format="json").status_code == 400


def test_a_table_posted_payroll_used_cannot_change(boss: Member) -> None:
    contract(boss, person(), "150000")
    run = work_out(boss).json()["id"]
    table = TaxTable.objects.get()
    assert boss.client().delete(f"/api/payroll/tax-tables/{table.pk}/").status_code == 400
    assert post(boss, run).json()["posted"] is True
    body = boss.client().get(f"/api/payroll/tax-tables/{table.pk}/").json()
    assert (
        boss.client().put(f"/api/payroll/tax-tables/{table.pk}/", body, format="json").status_code
        == 400
    )


# Working out pay


def test_a_steady_salary_withholds_a_twelfth_of_the_years_tax(boss: Member) -> None:
    contract(boss, person(), "150000")
    slip = only_payslip(work_out(boss))
    assert slip["gross"] == "150000.00"
    assert slip["projected_income"] == "1800000.00"
    assert slip["year_tax"] == "72000.00"
    assert slip["tax"] == "6000.00"
    assert slip["net"] == "144000.00"
    assert (slip["paid_days"], slip["unpaid_days"], slip["month_days"]) == ("31.0", "0.0", 31)


def test_allowances_deductions_and_tax_free_parts(boss: Member) -> None:
    contract(boss, person(), "50000", parts=STANDARD)
    slip = only_payslip(work_out(boss))
    assert [(line["name"], line["amount"]) for line in slip["lines"]] == [
        ("Basic", "50000.00"),
        ("House rent", "22500.00"),
        ("Medical", "5000.00"),
        ("Provident fund", "4165.00"),
    ]
    assert (slip["gross"], slip["deductions"], slip["taxable"]) == (
        "77500.00",
        "4165.00",
        "72500.00",
    )
    # 72,500 a month is 870,000 a year: 1% of the 270,000 above 600,000 is 2,700, so 225 a month.
    assert slip["tax"] == "225.00"
    assert slip["net"] == "73110.00"


def test_a_joiner_and_a_leaver_are_paid_for_their_days(boss: Member) -> None:
    contract(boss, person("J", joined=date(2026, 7, 16)), "31000", starts=date(2026, 7, 16))
    contract(boss, person("L", left_on=date(2026, 7, 10)), "31000", ends=date(2026, 7, 10))
    slips = {s["employee_code"]: s for s in work_out(boss).json()["payslips"]}
    assert (slips["J"]["paid_days"], slips["J"]["gross"]) == ("16.0", "16000.00")
    assert (slips["L"]["paid_days"], slips["L"]["gross"]) == ("10.0", "10000.00")


def test_a_raise_in_the_month_pays_each_contract_for_its_days(boss: Member) -> None:
    worker = person()
    contract(boss, worker, "31000", ends=date(2026, 7, 10))
    contract(boss, worker, "62000", starts=date(2026, 7, 11))
    slip = only_payslip(work_out(boss))
    assert slip["lines"] == [
        {"name": "Basic", "kind": "earning", "amount": "52000.00", "taxable": True}
    ]
    assert slip["paid_days"] == "31.0"


def test_unpaid_days_come_off_on_working_days_only(boss: Member) -> None:
    worker = person()
    contract(boss, worker, "31000")
    unpaid = LeaveType.objects.create(name="Unpaid", paid=False)
    annual = LeaveType.objects.create(name="Annual", days_per_year=14)
    approved = LeaveRequest.Status.APPROVED
    # July 2026 starts on a Wednesday; the default weekend is Sunday.
    LeaveRequest.objects.create(
        employee=worker,
        leave_type=unpaid,
        starts_on=date(2026, 7, 6),
        ends_on=date(2026, 7, 7),
        days=2,
        status=approved,
    )
    LeaveRequest.objects.create(
        employee=worker,
        leave_type=annual,
        starts_on=date(2026, 7, 12),  # A Sunday, which isn't leave.
        ends_on=date(2026, 7, 13),
        days=1,
        status=approved,
    )
    LeaveRequest.objects.create(  # Not approved, so it doesn't count.
        employee=worker,
        leave_type=unpaid,
        starts_on=date(2026, 7, 20),
        ends_on=date(2026, 7, 20),
        days=1,
    )
    absent, half = Attendance.Status.ABSENT, Attendance.Status.HALF_DAY
    Attendance.objects.create(employee=worker, on=date(2026, 7, 8), status=absent)
    Attendance.objects.create(employee=worker, on=date(2026, 7, 9), status=half)
    Attendance.objects.create(employee=worker, on=date(2026, 7, 12), status=absent)  # Sunday.
    Attendance.objects.create(employee=worker, on=date(2026, 7, 13), status=absent)  # Paid leave.
    Attendance.objects.create(
        employee=worker, on=date(2026, 7, 6), status=absent
    )  # Already unpaid.
    slip = only_payslip(work_out(boss))
    assert (slip["paid_days"], slip["unpaid_days"]) == ("27.5", "3.5")
    assert slip["gross"] == "27500.00"


def test_rows_entered_around_the_checks_are_handled(boss: Member) -> None:
    # Contracts saved through the app can't do either of these; old or imported rows might.
    gone = person("G", left_on=date(2026, 7, 10))
    Contract.objects.create(
        employee=gone, structure=plan(boss), starts_on=date(2026, 7, 20), basic_salary=D(9000)
    )
    broke = person("B")
    owing = plan(boss, [hr.ComponentInput("Loan", "deduction", D("5000"), None)], name="Owing")
    Contract.objects.create(
        employee=broke, structure=owing, starts_on=date(2026, 7, 1), basic_salary=D(1000)
    )
    contract(boss, person("OK"), "40000")
    reply = work_out(boss)
    assert reply.status_code == 400
    assert reply.json()["detail"].endswith("B")
    Contract.objects.filter(employee=broke).delete()
    assert [s["employee_code"] for s in work_out(boss).json()["payslips"]] == ["OK"]


def test_a_tax_table_for_another_country_is_refused(boss: Member) -> None:
    with pytest.raises(services.BadCountryError):
        services.save_table(
            boss.user,
            {
                "country": "US",
                "name": "X",
                "starts_on": date(2030, 1, 1),
                "ends_on": date(2030, 12, 31),
                "source": "X",
            },
            [Slab(D(0), D(0), D(0))],
        )


def test_people_without_a_contract_this_month_are_left_out(boss: Member) -> None:
    contract(boss, person("A"), "40000")
    person("B")
    contract(boss, person("C"), "40000", starts=date(2026, 8, 1))
    contract(
        boss,
        person("D", joined=date(2026, 1, 1), left_on=date(2026, 6, 30)),
        "40000",
        ends=date(2026, 6, 30),
    )
    codes = [s["employee_code"] for s in work_out(boss).json()["payslips"]]
    assert codes == ["A"]


def test_working_out_again_replaces_the_draft(boss: Member) -> None:
    worker = person()
    contract(boss, worker, "150000")
    first = work_out(boss).json()
    contract(boss, person("E2"), "60000")
    again = work_out(boss).json()
    assert again["id"] == first["id"]
    assert again["people"] == 2
    assert Payslip.objects.count() == 2


def test_with_no_slabs_for_the_year_nothing_is_worked_out(boss: Member) -> None:
    TaxTable.objects.all().delete()
    contract(boss, person(), "150000")
    reply = work_out(boss)
    assert reply.status_code == 400
    assert "tax slabs" in reply.json()["detail"]


def test_a_country_without_salary_tax_needs_no_slabs(boss: Member) -> None:
    TaxTable.objects.all().delete()
    HrSettings.objects.create(holiday_country="AE", weekend=[5, 6])
    contract(boss, person(), "150000")
    slip = only_payslip(work_out(boss))
    assert (slip["tax"], slip["net"], slip["year_tax"]) == ("0.00", "150000.00", "0.00")
    assert work_out(boss, "2026-08-01").status_code == 200


def test_nobody_to_pay_is_said_plainly(boss: Member) -> None:
    reply = work_out(boss)
    assert reply.status_code == 400
    assert "nothing to pay" in reply.json()["detail"]


def test_pay_that_cannot_cover_its_tax_names_the_people(boss: Member) -> None:
    contract(
        boss,
        person("E9"),
        "300000",
        parts=[hr.ComponentInput("Loan", "deduction", D("299000"), None)],
    )
    reply = work_out(boss)
    assert reply.status_code == 400
    assert reply.json()["detail"].endswith("E9")


# Posting


def test_posting_books_the_salaries_and_what_is_kept_back(boss: Member) -> None:
    contract(boss, person(), "50000", parts=STANDARD)
    run = work_out(boss).json()["id"]
    reply = post(boss, run)
    assert reply.status_code == 200, reply.content
    body = reply.json()
    assert body["posted"] is True
    assert body["run"]["status"] == "posted"
    assert body["run"]["number"] == "PAY-000001"
    entry = JournalEntry.objects.get(source_type="payroll_run", source_id=str(run))
    assert entry.date == date(2026, 7, 31)
    assert entry.status == JournalEntry.Status.POSTED
    assert body["run"]["entry_number"] == entry.number
    booked = {
        line.account.role: (line.debit, line.credit)
        for line in entry.lines.select_related("account")
    }
    assert booked == {
        "salaries": (D("77500.00"), D("0.00")),
        "withholding_payable": (D("0.00"), D("225.00")),
        "payroll_deductions": (D("0.00"), D("4165.00")),
        "salaries_payable": (D("0.00"), D("73110.00")),
    }
    actions = set(
        AuditEvent.objects.filter(model="payroll.PayrollRun").values_list("action", flat=True)
    )
    assert actions == {AuditEvent.Action.CREATE, AuditEvent.Action.POST}


def test_posted_payroll_is_fixed(boss: Member) -> None:
    contract(boss, person(), "150000")
    run = work_out(boss).json()["id"]
    post(boss, run)
    assert post(boss, run).status_code == 400
    assert work_out(boss).status_code == 400
    assert boss.client().delete(f"/api/payroll/runs/{run}/").status_code == 400


def test_a_draft_can_be_removed(boss: Member) -> None:
    contract(boss, person(), "150000")
    run = work_out(boss).json()["id"]
    assert boss.client().delete(f"/api/payroll/runs/{run}/").status_code == 204
    assert not PayrollRun.objects.exists()
    assert not Payslip.objects.exists()


def test_months_are_posted_in_order_and_each_counts_the_last(boss: Member) -> None:
    contract(boss, person(), "150000", parts=[])
    july = work_out(boss).json()["id"]
    august = work_out(boss, "2026-08-01").json()
    # Worked out before July was posted, August guesses 11 months of 150,000.
    assert august["payslips"][0]["tax"] == "5045.45"
    early = post(boss, august["id"])
    assert early.status_code == 400
    assert "in order" in early.json()["detail"]
    assert post(boss, july).json()["posted"] is True
    # July is posted now, so August's figures changed: the draft is updated, not posted.
    changed = post(boss, august["id"]).json()
    assert changed["posted"] is False
    assert changed["run"]["status"] == "draft"
    assert changed["run"]["payslips"][0]["tax"] == "6000.00"
    assert post(boss, august["id"]).json()["posted"] is True


def test_a_change_after_working_out_is_shown_before_posting(boss: Member) -> None:
    worker = person()
    contract(boss, worker, "31000")
    run = work_out(boss).json()["id"]
    Attendance.objects.create(
        employee=worker, on=date(2026, 7, 8), status=Attendance.Status.ABSENT
    )
    changed = post(boss, run).json()
    assert changed["posted"] is False
    assert changed["run"]["payslips"][0]["gross"] == "30000.00"
    assert post(boss, run).json()["posted"] is True


def test_an_earlier_month_cannot_change_once_a_later_one_is_posted(boss: Member) -> None:
    contract(boss, person(), "150000")
    post(boss, work_out(boss, "2026-08-01").json()["id"])
    reply = work_out(boss, "2026-07-01")
    assert reply.status_code == 400
    assert "later month" in reply.json()["detail"]


def test_posting_into_a_closed_month_is_refused(boss: Member) -> None:
    contract(boss, person(), "150000")
    run = work_out(boss).json()["id"]
    july = FiscalPeriod.objects.get(start=date(2026, 7, 1))
    accounting.set_period_closed(boss.user, july, closed=True)
    assert post(boss, run).status_code == 400
    assert PayrollRun.objects.get().status == PayrollRun.Status.DRAFT


# Payslips


def test_a_payslip_prints_once_posted(boss: Member, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("apps.sales.documents.to_pdf", lambda html: b"%PDF")
    contract(boss, person(), "150000")
    run = work_out(boss).json()
    slip = run["payslips"][0]["id"]
    assert boss.client().get(f"/api/payroll/payslips/{slip}/pdf/").status_code == 400
    post(boss, run["id"])
    reply = boss.client().get(f"/api/payroll/payslips/{slip}/pdf/?lang=xx")
    assert reply.status_code == 200
    assert reply["Content-Type"] == "application/pdf"
    assert reply["Content-Disposition"] == 'inline; filename="PAY-000001-E1.pdf"'


def test_without_the_pdf_libraries_printing_says_so(
    boss: Member, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(html: str) -> bytes:
        raise PdfUnavailableError

    monkeypatch.setattr("apps.sales.documents.to_pdf", broken)
    contract(boss, person(), "150000")
    run = work_out(boss).json()
    post(boss, run["id"])
    reply = boss.client().get(f"/api/payroll/payslips/{run['payslips'][0]['id']}/pdf/")
    assert reply.status_code == 503


def test_a_payslip_shows_the_pay_and_how_the_tax_was_reached(boss: Member) -> None:
    contract(boss, person(job_title="Cashier"), "50000", parts=STANDARD)
    post(boss, work_out(boss).json()["id"])
    slip = Payslip.objects.get()
    english = documents.payslip_html(slip, "en")
    for text in (
        "Payslip",
        "Invented E1",
        "Basic salary",
        "House rent",
        "Net pay",
        "73,110.00",
        "870,000.00",
        "Cashier",
    ):
        assert text in english
    urdu = documents.payslip_html(slip, "ur")
    assert "تنخواہ کی پرچی" in urdu
    assert 'dir="rtl"' in urdu


def test_a_payslip_with_unpaid_days_and_no_tax_says_so(boss: Member) -> None:
    TaxTable.objects.all().delete()
    HrSettings.objects.create(holiday_country="SA", weekend=[4, 5])
    worker = person()
    contract(boss, worker, "31000")
    Attendance.objects.create(
        employee=worker, on=date(2026, 7, 8), status=Attendance.Status.ABSENT
    )
    post(boss, work_out(boss).json()["id"])
    arabic = documents.payslip_html(Payslip.objects.get(), "ar")
    assert "أيام بلا أجر" in arabic
    assert "الراتب الخاضع للضريبة المقدر" not in arabic


# Who may do what


def test_payroll_has_its_own_rights(boss: Member) -> None:
    contract(boss, person(), "150000")
    run = work_out(boss).json()["id"]

    def member_with(permissions: dict[str, list[str]]) -> Any:
        joined = create_membership(role=create_role(permissions=permissions))
        return Member(user=joined.user, tenant=boss.tenant, membership=joined).client()

    hr_only = member_with({"hr": ["view", "create", "update", "delete"]})
    clerk = member_with({"payroll": ["view", "create"]})
    assert hr_only.get("/api/payroll/runs/").status_code == 403
    assert clerk.get("/api/payroll/runs/").status_code == 200
    month = {"month": "2026-07-01"}
    assert clerk.post("/api/payroll/runs/", month, format="json").status_code == 200
    assert clerk.post(f"/api/payroll/runs/{run}/post/").status_code == 403


# Books


def test_new_businesses_have_an_account_for_payroll_deductions(boss: Member) -> None:
    account = Account.objects.get(role="payroll_deductions")
    assert (account.code, account.type) == ("2170", "liability")


def test_older_businesses_get_a_payroll_deductions_account(boss: Member) -> None:
    Account.objects.filter(role="payroll_deductions").delete()
    migration = importlib.import_module("apps.accounting.migrations.0008_payroll_deductions")
    migration.add_role(django_apps, None)
    migration.add_role(django_apps, None)
    added = Account.objects.get(role="payroll_deductions")
    assert (added.code, added.type, added.parent.code if added.parent else None) == (
        "2170",
        "liability",
        "2100",
    )
