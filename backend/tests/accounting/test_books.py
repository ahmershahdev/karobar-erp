import threading
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounting import services
from apps.accounting.models import (
    Account,
    FiscalPeriod,
    FiscalYear,
    JournalEntry,
    NumberSeries,
    PostedEntryError,
)
from apps.platform.csv_export import safe_cell
from apps.tenancy.context import tenant_context
from apps.tenancy.models import AuditEvent
from tests.conftest import Member, make_member
from tests.factories import create_user

from .conftest import account, draft, lines_payload, with_books

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate


def test_a_new_business_gets_a_chart_a_year_and_a_series() -> None:
    owner = create_user(email_verified_at=timezone.now())
    client = APIClient()
    client.force_login(owner)
    body = client.post(
        "/api/tenants/", {"name": "Invented Books", "fiscal_year_start_month": 7}, format="json"
    ).json()
    client.credentials(HTTP_X_TENANT=body["tenant_id"])
    accounts = client.get("/api/accounting/accounts/").json()
    assert len(accounts) == 36
    assert {a["role"] for a in accounts} >= {"cash", "receivables", "sales", "tax_output"}
    years = client.get("/api/accounting/fiscal-years/").json()
    assert len(years) == 1
    assert len(years[0]["periods"]) == 12
    assert years[0]["start"].endswith("-07-01")


def test_entry_lifecycle(bookkeeper: Member) -> None:
    client = bookkeeper.client()
    cash, sales = account("cash").pk, account("sales").pk
    unbalanced = [
        {"account": cash, "debit": "100", "credit": "0"},
        {"account": sales, "debit": "0", "credit": "90"},
    ]
    created = client.post(
        "/api/accounting/entries/",
        {"date": str(TODAY()), "memo": "Counter sale", "lines": unbalanced},
        format="json",
    )
    assert created.status_code == 201, created.json()
    entry_id = created.json()["id"]
    assert created.json()["status"] == "draft"
    assert created.json()["number"] is None

    refused = client.post(f"/api/accounting/entries/{entry_id}/post/")
    assert refused.status_code == 400
    assert "Debits and credits" in refused.json()["detail"]

    fixed = client.put(
        f"/api/accounting/entries/{entry_id}/",
        {"date": str(TODAY()), "memo": "Counter sale", "lines": lines_payload(cash, sales)},
        format="json",
    )
    assert fixed.status_code == 200
    posted = client.post(f"/api/accounting/entries/{entry_id}/post/").json()
    assert posted["status"] == "posted"
    assert posted["number"] == "JV-000001"
    assert posted["total"] == "250.00"

    assert client.post(f"/api/accounting/entries/{entry_id}/post/").status_code == 400
    edit = client.put(
        f"/api/accounting/entries/{entry_id}/",
        {"date": str(TODAY()), "lines": lines_payload(cash, sales, "1")},
        format="json",
    )
    assert edit.status_code == 400
    assert client.delete(f"/api/accounting/entries/{entry_id}/").status_code == 400
    actions = list(
        AuditEvent.objects.filter(model="accounting.JournalEntry").values_list("action", flat=True)
    )
    assert actions == ["create", "update", "post"]


def test_posted_entries_are_immutable_at_the_model_level(bookkeeper: Member) -> None:
    entry = services.post_entry(bookkeeper.user, draft(bookkeeper))
    entry.memo = "Tampered"
    with pytest.raises(PostedEntryError):
        entry.save()
    with pytest.raises(PostedEntryError):
        entry.delete()
    line = entry.lines.first()
    assert line is not None
    line.debit = Decimal("1")
    with pytest.raises(PostedEntryError):
        line.save()


def test_reversal(bookkeeper: Member) -> None:
    client = bookkeeper.client()
    entry = services.post_entry(bookkeeper.user, draft(bookkeeper, "80"))
    response = client.post(
        f"/api/accounting/entries/{entry.pk}/reverse/", {"date": str(TODAY())}, format="json"
    )
    assert response.status_code == 201
    reversal = response.json()
    assert reversal["number"] == "JV-000002"
    assert reversal["reversal_of"] == entry.pk
    assert reversal["memo"] == "Reversal of JV-000001"
    assert [(line["debit"], line["credit"]) for line in reversal["lines"]] == [
        ("0.00", "80.00"),
        ("80.00", "0.00"),
    ]
    assert (
        client.get(f"/api/accounting/entries/{entry.pk}/").json()["reversed_by"] == reversal["id"]
    )
    again = client.post(
        f"/api/accounting/entries/{entry.pk}/reverse/", {"date": str(TODAY())}, format="json"
    )
    assert again.status_code == 400
    unposted = draft(bookkeeper)
    assert (
        client.post(
            f"/api/accounting/entries/{unposted.pk}/reverse/",
            {"date": str(TODAY())},
            format="json",
        ).status_code
        == 400
    )
    balance = client.get("/api/accounting/reports/trial-balance/").json()
    assert balance["rows"] == []


def test_closed_periods_and_dates_outside_any_year(bookkeeper: Member) -> None:
    client = bookkeeper.client()
    period = FiscalPeriod.objects.get(start__lte=TODAY(), end__gte=TODAY())
    closed = client.patch(f"/api/accounting/periods/{period.pk}/", {"closed": True}, format="json")
    assert closed.json()["closed"] is True
    entry = draft(bookkeeper)
    refused = client.post(f"/api/accounting/entries/{entry.pk}/post/")
    assert refused.status_code == 400
    assert "open fiscal period" in refused.json()["detail"]
    client.patch(f"/api/accounting/periods/{period.pk}/", {"closed": False}, format="json")
    assert client.post(f"/api/accounting/entries/{entry.pk}/post/").status_code == 200

    far = services.save_draft(
        bookkeeper.user,
        TODAY() + timedelta(days=800),
        "",
        [
            services.LineInput(account("cash"), Decimal(1), Decimal(0)),
            services.LineInput(account("sales"), Decimal(0), Decimal(1)),
        ],
    )
    with pytest.raises(services.NoOpenPeriodError):
        services.post_entry(bookkeeper.user, far)


def test_group_and_inactive_accounts_take_no_postings(bookkeeper: Member) -> None:
    group = Account.objects.get(code="1100")
    entry = services.save_draft(
        bookkeeper.user,
        TODAY(),
        "",
        [
            services.LineInput(group, Decimal(5), Decimal(0)),
            services.LineInput(account("sales"), Decimal(0), Decimal(5)),
        ],
    )
    with pytest.raises(services.AccountNotPostableError):
        services.post_entry(bookkeeper.user, entry)


def test_fiscal_years(bookkeeper: Member) -> None:
    client = bookkeeper.client()
    year = FiscalYear.objects.get()
    overlap = client.post(
        "/api/accounting/fiscal-years/",
        {"start": str(year.start), "end": str(year.end)},
        format="json",
    )
    assert overlap.status_code == 400
    following = year.end + timedelta(days=1)
    created = client.post(
        "/api/accounting/fiscal-years/",
        {
            "start": str(following),
            "end": str(following.replace(year=following.year + 1) - timedelta(days=1)),
        },
        format="json",
    )
    assert created.status_code == 201
    assert len(created.json()["periods"]) == 12
    backwards = client.post(
        "/api/accounting/fiscal-years/",
        {"start": "2040-02-01", "end": "2040-01-01"},
        format="json",
    )
    assert backwards.status_code == 400


def test_chart_editing(bookkeeper: Member) -> None:
    client = bookkeeper.client()
    parent = Account.objects.get(code="6000").pk
    created = client.post(
        "/api/accounting/accounts/",
        {"code": "6600", "name": "Fuel", "type": "expense", "parent": parent},
        format="json",
    )
    assert created.status_code == 201, created.json()
    fuel = created.json()["id"]
    assert (
        client.post(
            "/api/accounting/accounts/",
            {"code": "6600", "name": "Again", "type": "expense"},
            format="json",
        ).status_code
        == 400
    )
    leaf_parent = client.post(
        "/api/accounting/accounts/",
        {"code": "6700", "name": "Child", "type": "expense", "parent": fuel},
        format="json",
    )
    assert leaf_parent.status_code == 400
    assert (
        client.patch(
            f"/api/accounting/accounts/{fuel}/", {"name": "Fuel and transport"}, format="json"
        ).json()["name"]
        == "Fuel and transport"
    )
    group = Account.objects.get(code="6000").pk
    assert (
        client.patch(
            f"/api/accounting/accounts/{group}/", {"parent": group}, format="json"
        ).status_code
        == 400
    )
    unused = Account.objects.get(code="1160").pk
    assert client.delete(f"/api/accounting/accounts/{unused}/").status_code == 204
    services.post_entry(bookkeeper.user, draft(bookkeeper))
    assert client.delete(f"/api/accounting/accounts/{account('sales').pk}/").status_code == 400
    assert client.delete(f"/api/accounting/accounts/{group}/").status_code == 400
    assert client.delete(f"/api/accounting/accounts/{fuel}/").status_code == 204


def test_reports_and_safe_csv(bookkeeper: Member) -> None:
    client = bookkeeper.client()
    sales = account("sales")
    sales.name = "=HYPERLINK(evil)"
    sales.save()
    services.post_entry(bookkeeper.user, draft(bookkeeper, "100"))
    services.post_entry(bookkeeper.user, draft(bookkeeper, "50"))

    report = client.get("/api/accounting/reports/trial-balance/").json()
    assert report["total_debit"] == report["total_credit"] == "150.00"
    assert {row["code"]: (row["debit"], row["credit"]) for row in report["rows"]} == {
        "1110": ("150.00", "0.00"),
        "4100": ("0.00", "150.00"),
    }
    later = client.get(
        f"/api/accounting/reports/trial-balance/?start={TODAY() + timedelta(days=1)}"
    ).json()
    assert later["rows"] == []

    csv = client.get("/api/accounting/reports/trial-balance/?export=csv")
    assert csv["Content-Type"].startswith("text/csv")
    text = csv.content.decode("utf-8-sig")
    assert "'=HYPERLINK(evil)" in text
    assert "Total,,150.00,150.00" in text

    ledger = client.get(f"/api/accounting/accounts/{account('cash').pk}/ledger/").json()
    assert [line["balance"] for line in ledger["lines"]] == ["100.00", "150.00"]
    assert ledger["closing"] == "150.00"
    tomorrow = TODAY() + timedelta(days=1)
    opening = client.get(
        f"/api/accounting/accounts/{account('cash').pk}/ledger/?start={tomorrow}"
    ).json()
    assert opening["opening"] == "150.00"
    assert opening["lines"] == []
    ledger_csv = client.get(
        f"/api/accounting/accounts/{account('cash').pk}/ledger/?export=csv&end={TODAY()}"
    )
    assert "Opening balance" in ledger_csv.content.decode("utf-8-sig")
    bad = client.get(
        f"/api/accounting/reports/trial-balance/?start={TODAY()}&end={TODAY() - timedelta(days=1)}"
    )
    assert bad.status_code == 400


def test_entry_list_filters(bookkeeper: Member) -> None:
    client = bookkeeper.client()
    services.post_entry(bookkeeper.user, draft(bookkeeper))
    draft(bookkeeper)
    assert len(client.get("/api/accounting/entries/?status=draft").json()["results"]) == 1
    assert len(client.get("/api/accounting/entries/?status=posted").json()["results"]) == 1
    assert (
        len(
            client.get(f"/api/accounting/entries/?start={TODAY()}&end={TODAY()}").json()["results"]
        )
        == 2
    )
    assert client.get("/api/accounting/entries/?start=yesterday").status_code == 400


def test_a_stale_draft_object_cannot_change_or_delete_a_posted_entry(bookkeeper: Member) -> None:
    stale = draft(bookkeeper)
    services.post_entry(bookkeeper.user, JournalEntry.objects.get(pk=stale.pk))
    assert stale.status == JournalEntry.Status.DRAFT
    with pytest.raises(services.AlreadyPostedError):
        services.delete_draft(bookkeeper.user, stale)
    with pytest.raises(services.AlreadyPostedError):
        services.save_draft(bookkeeper.user, TODAY(), "Edited", [], stale)
    with pytest.raises(PostedEntryError):
        stale.delete()
    assert JournalEntry.objects.get(pk=stale.pk).lines.count() == 2


def test_account_parents_cannot_loop(bookkeeper: Member) -> None:
    client = bookkeeper.client()
    top = Account.objects.get(code="6000")
    middle = client.post(
        "/api/accounting/accounts/",
        {"code": "6800", "name": "Office", "type": "expense", "is_group": True, "parent": top.pk},
        format="json",
    ).json()["id"]
    looped = client.patch(f"/api/accounting/accounts/{top.pk}/", {"parent": middle}, format="json")
    assert looped.status_code == 400


def test_odd_account_codes_still_export(bookkeeper: Member) -> None:
    cash = account("cash")
    cash.code = 'C"1'
    cash.save()
    response = bookkeeper.client().get(f"/api/accounting/accounts/{cash.pk}/ledger/?export=csv")
    assert response.status_code == 200
    assert "attachment" in response["Content-Disposition"]


def test_drafts_can_be_deleted(bookkeeper: Member) -> None:
    entry = draft(bookkeeper)
    assert bookkeeper.client().delete(f"/api/accounting/entries/{entry.pk}/").status_code == 204
    assert not JournalEntry.objects.filter(pk=entry.pk).exists()


def test_roles_decide_who_may_post(bookkeeper: Member) -> None:
    clerk = with_books(make_member(permissions={"accounting": ["view", "create"]}))
    with tenant_context(clerk.tenant):
        entry = draft(clerk)
        client = clerk.client()
        assert client.get("/api/accounting/entries/").status_code == 200
        assert client.post(f"/api/accounting/entries/{entry.pk}/post/").status_code == 403


def test_safe_cell() -> None:
    assert safe_cell(None) == ""
    assert safe_cell(Decimal("-5.00")) == "-5.00"
    assert safe_cell("-5") == "'-5"
    assert safe_cell("@SUM(A1)") == "'@SUM(A1)"
    assert safe_cell("Rent") == "Rent"


@pytest.mark.django_db(transaction=True)
def test_parallel_posts_get_consecutive_numbers_without_gaps() -> None:
    member = with_books(make_member(owner=True))
    with tenant_context(member.tenant):
        drafts = [draft(member, str(10 + i)) for i in range(6)]
        # One more that will fail, to prove a rolled-back post doesn't burn a number.
        broken = services.save_draft(
            member.user,
            TODAY(),
            "",
            [services.LineInput(account("cash"), Decimal(1), Decimal(0))],
        )
    errors: list[BaseException] = []
    barrier = threading.Barrier(len(drafts) + 1)

    def post(entry: JournalEntry) -> None:
        try:
            with tenant_context(member.tenant):
                barrier.wait()
                services.post_entry(member.user, entry)
        except services.UnbalancedError:
            pass
        except BaseException as exc:
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=post, args=(entry,)) for entry in [*drafts, broken]]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    with tenant_context(member.tenant):
        numbers = sorted(
            JournalEntry.objects.exclude(number=None).values_list("number", flat=True)
        )
        series = NumberSeries.objects.get(key="JV")
    assert numbers == [f"JV-{n:06d}" for n in range(1, 7)]
    assert series.next_number == 7
