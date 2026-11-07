from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from apps.hr import services
from apps.hr.models import Contract, Department, Employee, SalaryStructure
from apps.tenancy.context import tenant_context
from apps.tenancy.models import AuditEvent
from tests.conftest import Member, make_member

pytestmark = pytest.mark.django_db
D = Decimal


@pytest.fixture
def boss(db: None) -> Iterator[Member]:
    member = make_member(owner=True)
    with tenant_context(member.tenant):
        yield member


STANDARD = [
    {"name": "House rent", "kind": "earning", "percent": "45"},
    {"name": "Medical", "kind": "earning", "percent": "10", "taxable": False},
    {"name": "Provident fund", "kind": "deduction", "percent": "8.33"},
]


def structure(
    member: Member, name: str = "Staff", parts: list[dict[str, Any]] | None = None
) -> Any:
    body = {"name": name, "components": STANDARD if parts is None else parts}
    return member.client().post("/api/hr/salary-structures/", body, format="json")


def employee(member: Member, code: str = "E1", **extra: Any) -> Any:
    body = {"code": code, "full_name": "Invented Worker", "joined_on": "2026-01-01", **extra}
    return member.client().post("/api/hr/employees/", body, format="json")


def contract(member: Member, person: int, plan: int, starts: str, ends: str | None = None) -> Any:
    body = {
        "employee": person,
        "structure": plan,
        "starts_on": starts,
        "ends_on": ends,
        "basic_salary": "50000",
    }
    return member.client().post("/api/hr/contracts/", body, format="json")


def test_departments_are_made_and_listed(boss: Member) -> None:
    reply = boss.client().post(
        "/api/hr/departments/", {"code": "SALES", "name": "Sales"}, format="json"
    )
    assert reply.status_code == 201, reply.content
    assert boss.client().get("/api/hr/departments/").json()[0]["name"] == "Sales"
    again = boss.client().post(
        "/api/hr/departments/", {"code": "SALES", "name": "Other"}, format="json"
    )
    assert again.status_code == 400


def test_a_salary_structure_keeps_its_parts_in_order(boss: Member) -> None:
    reply = structure(boss)
    assert reply.status_code == 201, reply.content
    parts = [(row["name"], row["kind"]) for row in reply.json()["components"]]
    assert parts == [
        ("House rent", "earning"),
        ("Medical", "earning"),
        ("Provident fund", "deduction"),
    ]
    assert AuditEvent.objects.filter(model="hr.SalaryStructure", action="create").exists()


def test_a_structure_previews_a_month(boss: Member) -> None:
    pk = structure(boss).json()["id"]
    reply = boss.client().get(f"/api/hr/salary-structures/{pk}/preview/?basic=50000")
    assert reply.status_code == 200, reply.content
    body = reply.json()
    assert (body["gross"], body["deductions"], body["net"], body["taxable"]) == (
        "77500.00",
        "4165.00",
        "73335.00",
        "72500.00",
    )
    assert (
        boss.client().get(f"/api/hr/salary-structures/{pk}/preview/?basic=-1").status_code == 400
    )


@pytest.mark.parametrize(
    "part",
    [
        {"name": "Both", "kind": "earning", "amount": "10", "percent": "5"},
        {"name": "Neither", "kind": "earning"},
        {"name": "  ", "kind": "earning", "amount": "10"},
        {"name": "Odd", "kind": "bonus", "amount": "10"},
        {"name": "Too much", "kind": "earning", "percent": "101"},
    ],
)
def test_strange_parts_are_refused(boss: Member, part: dict[str, Any]) -> None:
    assert structure(boss, parts=[part]).status_code == 400
    assert not SalaryStructure.objects.exists()


def test_too_many_parts_are_refused(boss: Member) -> None:
    parts = [{"name": f"Part {n}", "kind": "earning", "amount": "1"} for n in range(31)]
    assert structure(boss, parts=parts).status_code == 400


def test_a_structure_is_edited_as_a_whole(boss: Member) -> None:
    pk = structure(boss).json()["id"]
    body = {
        "name": "Staff 2027",
        "components": [{"name": "Fuel", "kind": "earning", "amount": "5000"}],
    }
    reply = boss.client().put(f"/api/hr/salary-structures/{pk}/", body, format="json")
    assert reply.status_code == 200, reply.content
    assert [row["name"] for row in reply.json()["components"]] == ["Fuel"]
    assert structure(boss, name="Staff 2027").status_code == 400


def test_employees_are_made_searched_and_marked_as_left(boss: Member) -> None:
    dept = boss.client().post(
        "/api/hr/departments/", {"code": "OPS", "name": "Shop floor"}, format="json"
    )
    reply = employee(
        boss, department=dept.json()["id"], job_title="Cashier", national_id="00000-0000000-0"
    )
    assert reply.status_code == 201, reply.content
    assert reply.json()["department_name"] == "Shop floor"
    employee(boss, "E2", full_name="Second Worker")
    assert len(boss.client().get("/api/hr/employees/?q=cashier").json()["results"]) == 1
    pk = reply.json()["id"]
    left = boss.client().patch(
        f"/api/hr/employees/{pk}/", {"left_on": "2026-06-30"}, format="json"
    )
    assert left.status_code == 200
    assert [
        e["code"] for e in boss.client().get("/api/hr/employees/?status=active").json()["results"]
    ] == ["E2"]
    assert [
        e["code"] for e in boss.client().get("/api/hr/employees/?status=left").json()["results"]
    ] == ["E1"]


def test_someone_cannot_leave_before_joining(boss: Member) -> None:
    assert employee(boss, left_on="2025-12-31").status_code == 400


def test_a_contract_shows_its_pay_and_becomes_current(boss: Member) -> None:
    person, plan = employee(boss).json()["id"], structure(boss).json()["id"]
    reply = contract(boss, person, plan, "2026-01-01")
    assert reply.status_code == 201, reply.content
    assert reply.json()["pay"]["net"] == "73335.00"
    current = boss.client().get(f"/api/hr/employees/{person}/").json()["current_contract"]
    assert current["structure_name"] == "Staff"
    assert current["basic_salary"] == "50000.00"


def test_contracts_for_one_person_never_overlap(boss: Member) -> None:
    person, plan = employee(boss).json()["id"], structure(boss).json()["id"]
    assert contract(boss, person, plan, "2026-01-01", "2026-06-30").status_code == 201
    assert contract(boss, person, plan, "2026-06-30").status_code == 400
    assert contract(boss, person, plan, "2025-12-01", "2026-01-01").status_code == 400
    following = contract(boss, person, plan, "2026-07-01")
    assert following.status_code == 201
    # An open-ended contract runs for ever, so nothing may start after it either.
    assert contract(boss, person, plan, "2030-01-01").status_code == 400
    # Moving a contract onto another's dates is caught too.
    moved = boss.client().patch(
        f"/api/hr/contracts/{following.json()['id']}/", {"starts_on": "2026-06-01"}, format="json"
    )
    assert moved.status_code == 400


def test_a_contract_cannot_end_before_it_starts(boss: Member) -> None:
    person, plan = employee(boss).json()["id"], structure(boss).json()["id"]
    assert contract(boss, person, plan, "2026-05-01", "2026-04-30").status_code == 400


def test_a_switched_off_structure_cannot_be_given_to_a_new_contract(boss: Member) -> None:
    person = employee(boss).json()["id"]
    plan = structure(boss).json()["id"]
    SalaryStructure.objects.filter(pk=plan).update(is_active=False)
    assert contract(boss, person, plan, "2026-01-01").status_code == 400


def test_deductions_larger_than_pay_are_refused(boss: Member) -> None:
    person = employee(boss).json()["id"]
    plan = structure(
        boss, parts=[{"name": "Loan", "kind": "deduction", "amount": "60000"}]
    ).json()["id"]
    assert contract(boss, person, plan, "2026-01-01").status_code == 400
    assert not Contract.objects.exists()


def test_things_in_use_cannot_be_deleted(boss: Member) -> None:
    dept = (
        boss.client()
        .post("/api/hr/departments/", {"code": "OPS", "name": "Ops"}, format="json")
        .json()["id"]
    )
    person = employee(boss, department=dept).json()["id"]
    plan = structure(boss).json()["id"]
    contract(boss, person, plan, "2026-01-01")
    assert boss.client().delete(f"/api/hr/departments/{dept}/").status_code == 400
    assert boss.client().delete(f"/api/hr/salary-structures/{plan}/").status_code == 400
    assert boss.client().delete(f"/api/hr/employees/{person}/").status_code == 400
    assert Employee.objects.filter(pk=person).exists()
    assert Department.objects.filter(pk=dept).exists()


def test_an_unused_employee_can_be_deleted(boss: Member) -> None:
    person = employee(boss).json()["id"]
    assert boss.client().delete(f"/api/hr/employees/{person}/").status_code == 204


def test_hr_follows_the_role(boss: Member) -> None:
    viewer = make_member(permissions={"hr": ["view"]})
    nobody = make_member(permissions={"sales": ["view"]})
    with tenant_context(viewer.tenant):
        assert viewer.client().get("/api/hr/employees/").status_code == 200
        assert employee(viewer).status_code == 403
    with tenant_context(nobody.tenant):
        assert nobody.client().get("/api/hr/employees/").status_code == 403


def test_the_current_contract_follows_the_date(boss: Member) -> None:
    person = Employee.objects.get(pk=employee(boss).json()["id"])
    plan = structure(boss).json()["id"]
    contract(boss, person.pk, plan, "2026-01-01", "2026-03-31")
    assert services.current_contract(person, date(2026, 2, 1)) is not None
    assert services.current_contract(person, date(2026, 4, 1)) is None


def test_a_department_can_be_renamed(boss: Member) -> None:
    pk = (
        boss.client()
        .post("/api/hr/departments/", {"code": "OPS", "name": "Ops"}, format="json")
        .json()["id"]
    )
    reply = boss.client().patch(
        f"/api/hr/departments/{pk}/", {"name": "Shop floor"}, format="json"
    )
    assert reply.json()["name"] == "Shop floor"


def test_a_contract_can_be_deleted(boss: Member) -> None:
    person, plan = employee(boss).json()["id"], structure(boss).json()["id"]
    pk = contract(boss, person, plan, "2026-01-01").json()["id"]
    assert boss.client().delete(f"/api/hr/contracts/{pk}/").status_code == 204
    assert AuditEvent.objects.filter(model="hr.Contract", action="delete").exists()


def test_a_contract_whose_structure_no_longer_adds_up_shows_no_pay(boss: Member) -> None:
    person, plan = employee(boss).json()["id"], structure(boss).json()["id"]
    pk = contract(boss, person, plan, "2026-01-01").json()["id"]
    body = {
        "name": "Staff",
        "components": [{"name": "Loan", "kind": "deduction", "amount": "99999"}],
    }
    boss.client().put(f"/api/hr/salary-structures/{plan}/", body, format="json")
    assert boss.client().get(f"/api/hr/contracts/{pk}/").json()["pay"] is None
    assert len(boss.client().get(f"/api/hr/contracts/?employee={person}").json()["results"]) == 1


def test_the_service_checks_parts_even_without_the_api(boss: Member) -> None:
    blank = services.ComponentInput("  ", "earning", D(1), None)
    with pytest.raises(services.BadComponentError):
        services.save_structure(boss.user, {"name": "X"}, [blank])
    many = [services.ComponentInput(f"P{n}", "earning", D(1), None) for n in range(31)]
    with pytest.raises(services.TooManyComponentsError):
        services.save_structure(boss.user, {"name": "Y"}, many)


def test_records_name_themselves(boss: Member) -> None:
    person, plan = employee(boss).json()["id"], structure(boss).json()["id"]
    pk = contract(boss, person, plan, "2026-01-01").json()["id"]
    saved = Contract.objects.get(pk=pk)
    assert str(saved) == f"{person} from 2026-01-01"
    assert str(saved.structure.components.first()) == "House rent"
    assert str(saved.structure) == "Staff"
    assert str(saved.employee) == "E1 Invented Worker"


def test_a_percentage_over_100_is_refused_by_the_service(boss: Member) -> None:
    over = services.ComponentInput("Rent", "earning", None, D(101))
    with pytest.raises(services.BadComponentError):
        services.save_structure(boss.user, {"name": "Z"}, [over])


def test_a_contract_sits_inside_employment(boss: Member) -> None:
    person = employee(boss, joined_on="2026-03-01").json()["id"]
    plan = structure(boss).json()["id"]
    assert contract(boss, person, plan, "2026-02-01").status_code == 400
    boss.client().patch(f"/api/hr/employees/{person}/", {"left_on": "2026-12-31"}, format="json")
    assert contract(boss, person, plan, "2026-03-01").status_code == 400
    assert contract(boss, person, plan, "2026-03-01", "2027-01-31").status_code == 400
    assert contract(boss, person, plan, "2026-03-01", "2026-12-31").status_code == 201


def test_leaving_ends_a_contract_that_runs_past_it(boss: Member) -> None:
    person = employee(boss).json()["id"]
    plan = structure(boss).json()["id"]
    pk = contract(boss, person, plan, "2026-01-01").json()["id"]
    reply = boss.client().patch(
        f"/api/hr/employees/{person}/", {"left_on": "2026-08-31"}, format="json"
    )
    assert reply.status_code == 200, reply.content
    assert str(Contract.objects.get(pk=pk).ends_on) == "2026-08-31"


def test_leaving_before_a_contract_starts_is_refused(boss: Member) -> None:
    person = employee(boss).json()["id"]
    plan = structure(boss).json()["id"]
    contract(boss, person, plan, "2026-09-01")
    reply = boss.client().patch(
        f"/api/hr/employees/{person}/", {"left_on": "2026-08-31"}, format="json"
    )
    assert reply.status_code == 400
    assert Employee.objects.get(pk=person).left_on is None


def test_joining_after_a_contract_starts_is_refused(boss: Member) -> None:
    person = employee(boss).json()["id"]
    plan = structure(boss).json()["id"]
    contract(boss, person, plan, "2026-01-01")
    reply = boss.client().patch(
        f"/api/hr/employees/{person}/", {"joined_on": "2026-02-01"}, format="json"
    )
    assert reply.status_code == 400


def test_a_contract_checks_the_latest_leaving_day(boss: Member) -> None:
    stale = Employee.objects.get(pk=employee(boss).json()["id"])
    plan = SalaryStructure.objects.get(pk=structure(boss).json()["id"])
    Employee.objects.filter(pk=stale.pk).update(left_on=date(2026, 6, 30))
    values = {
        "employee": stale,
        "structure": plan,
        "starts_on": date(2026, 1, 1),
        "basic_salary": D(1000),
    }
    with pytest.raises(services.OutsideEmploymentError):
        services.save_contract(boss.user, values)


def test_saving_an_old_copy_keeps_a_leaving_day_saved_meanwhile(boss: Member) -> None:
    stale = Employee.objects.get(pk=employee(boss).json()["id"])
    Employee.objects.filter(pk=stale.pk).update(left_on=date(2026, 6, 30))
    services.save_employee(boss.user, stale, {"phone": "0300 0000000"})
    fresh = Employee.objects.get(pk=stale.pk)
    assert (fresh.phone, fresh.left_on) == ("0300 0000000", date(2026, 6, 30))
