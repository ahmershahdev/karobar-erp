from dataclasses import replace
from datetime import date
from io import StringIO

import pytest
from django.apps import apps
from django.core.management import CommandError, call_command
from django.utils import timezone
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.accounting.models import JournalEntry
from apps.accounting.reports import trial_balance
from apps.accounts.models import User
from apps.demo import data, seed, wipe
from apps.demo.models import DemoBusiness
from apps.hr.models import Employee
from apps.inventory.models import BatchLevel, StockLevel, Warehouse
from apps.payroll import wps
from apps.payroll.models import PayrollRun, SalaryPayment
from apps.purchasing.models import Bill
from apps.sales.models import CreditNote, Invoice
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant
from tests.factories import create_tenant, create_user

pytestmark = pytest.mark.django_db

# A fixed day, so the history crosses a month end and a payroll month for both businesses.
TODAY = date(2026, 9, 20)


def light(kind: str) -> data.Plan:
    """The same business with fewer products and sales, for the tests that don't need volume."""
    plan = data.PLANS[kind]
    return replace(plan, items=plan.items[:12], sales_a_day=(1, 3))


@pytest.fixture
def owner() -> User:
    return create_user(email="demo@example.com", email_verified_at=timezone.now())


def rows() -> dict[str, int]:
    return {
        model._meta.label: model._default_manager.all().count()
        if not hasattr(model, "all_tenants")
        else model.all_tenants.count()
        for model in apps.get_models()
        if model._meta.app_label not in {"sessions", "contenttypes", "auth", "admin"}
    }


@pytest.mark.parametrize("kind", ["pk", "ae"])
def test_a_demo_business_has_balanced_books_and_real_documents(owner: User, kind: str) -> None:
    tenant, counts = seed.seed(owner, kind, TODAY, days=52, plan=light(kind))
    assert DemoBusiness.objects.get(tenant=tenant).kind == kind
    with tenant_context(tenant):
        books = trial_balance(TODAY)
        assert books.total_debit == books.total_credit
        assert books.total_debit > 0
        assert not JournalEntry.objects.filter(status="draft").exists()
        assert Invoice.objects.filter(status="posted").count() == counts["sales bills"] > 40
        assert Bill.objects.filter(status="posted").exists()
        assert CreditNote.objects.filter(status="posted").exists()
        assert Employee.objects.count() == 6
        # Nothing was sold that wasn't there.
        assert not StockLevel.objects.filter(quantity__lt=0).exists()
        assert not BatchLevel.objects.filter(quantity__lt=0).exists()
        # Payroll is posted and paid where the law's figures allow it.
        posted = PayrollRun.objects.filter(status="posted")
        assert posted.count() == counts.get("payroll months", 0)
        assert SalaryPayment.objects.count() == posted.count()
    # The history starts on 30 July, so August is the one whole month to pay.
    assert counts["payroll months"] == 1
    if kind == "ae":
        with tenant_context(tenant):
            name, text = wps.salary_file(PayrollRun.objects.get(status="posted"))
        assert name.endswith(".SIF")
        assert text.count("EDR,") == 6


def test_a_history_starting_on_the_first_pays_that_month(owner: User) -> None:
    # 1 September to 20 October: September is whole, October is not.
    _, counts = seed.seed(owner, "ae", date(2026, 10, 20), days=49, plan=light("ae"))
    assert counts["payroll months"] == 1


def test_two_runs_make_the_same_business(owner: User) -> None:
    first, counts = seed.seed(owner, "pk", TODAY, days=12, plan=light("pk"))
    wipe.wipe(first)
    again, recount = seed.seed(owner, "pk", TODAY, days=12, plan=light("pk"))
    assert counts == recount
    with tenant_context(again):
        assert trial_balance(TODAY).total_debit > 0


def test_a_wipe_leaves_nothing_behind_and_touches_no_one_else(owner: User) -> None:
    other = create_tenant(name="A real business")
    with tenant_context(other):
        kept = Warehouse.objects.create(code="MAIN", name="Real main store")
    before = rows()
    tenant, _ = seed.seed(owner, "ae", TODAY, days=12, plan=light("ae"))
    assert rows() != before
    wipe.wipe(tenant)
    assert rows() == before
    assert Tenant.objects.filter(pk=other.pk).exists()
    with tenant_context(other):
        assert Warehouse.objects.get(pk=kept.pk).name == "Real main store"


def test_a_real_business_can_never_be_wiped() -> None:
    real = create_tenant(name="A real business")
    with pytest.raises(wipe.NotDemoError):
        wipe.wipe(real)
    assert Tenant.objects.filter(pk=real.pk).exists()


def test_the_command_runs_only_in_demo_mode(settings: SettingsWrapper) -> None:
    settings.DEMO_MODE = False
    with pytest.raises(CommandError, match="DEMO_MODE"):
        call_command("seed_demo")
    settings.DEMO_MODE = True
    settings.DEMO_PASSWORD = ""
    with pytest.raises(CommandError, match="DEMO_PASSWORD"):
        call_command("seed_demo")


def test_the_command_replaces_the_demo_businesses(
    settings: SettingsWrapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(data.PLANS, "ae", light("ae"))
    settings.DEMO_MODE = True
    settings.DEMO_PASSWORD = "an invented demo passphrase"
    out = StringIO()
    call_command("seed_demo", "--days", "7", "--only", "ae", stdout=out)
    call_command("seed_demo", "--days", "7", "--only", "ae", stdout=out)
    assert DemoBusiness.objects.count() == 1
    owner = User.objects.get(email=settings.DEMO_EMAIL)
    assert owner.check_password("an invented demo passphrase")
    assert owner.email_verified_at is not None
    assert "Removed 1 old demo business" in out.getvalue()


def test_only_one_kind_leaves_the_other_demo_business(
    settings: SettingsWrapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(data.PLANS, "ae", light("ae"))
    monkeypatch.setitem(data.PLANS, "pk", light("pk"))
    settings.DEMO_MODE = True
    settings.DEMO_PASSWORD = "an invented demo passphrase"
    call_command("seed_demo", "--days", "7", stdout=StringIO())
    pakistan = DemoBusiness.objects.get(kind="pk").tenant_id
    call_command("seed_demo", "--days", "7", "--only", "ae", stdout=StringIO())
    assert DemoBusiness.objects.get(kind="pk").tenant_id == pakistan
    assert DemoBusiness.objects.filter(kind="ae").count() == 1
    with pytest.raises(CommandError, match="between 7 and 400"):
        call_command("seed_demo", "--days", "0")
