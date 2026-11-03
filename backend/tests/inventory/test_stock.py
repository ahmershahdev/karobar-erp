import threading
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounting.models import FiscalPeriod, JournalEntry, NumberSeries, PostedEntryError
from apps.accounting.reports import trial_balance
from apps.inventory import services
from apps.inventory.models import (
    Batch,
    BatchLevel,
    CostLayer,
    Product,
    StockEntry,
    StockLevel,
    StockMove,
)
from apps.inventory.tasks import send_stock_alerts
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Membership, Role
from tests.factories import create_user

from .conftest import Shop, line, make_shop, post

pytestmark = pytest.mark.django_db
D = Decimal


def level(shop: Shop, warehouse: object | None = None) -> StockLevel:
    found: StockLevel = StockLevel.objects.get(product=shop.soap, warehouse=warehouse or shop.main)
    return found


def inventory_balance() -> Decimal:
    report = trial_balance(timezone.localdate())
    return next((row.debit - row.credit for row in report.rows if row.code == "1140"), D(0))


def test_moving_average_receipt_and_issue_post_to_the_books(shop: Shop) -> None:
    receipt = post(shop, "receipt", [line(shop, "10", "100")])
    assert receipt.number == "GRN-000001"
    assert receipt.journal_entry is not None
    post(shop, "receipt", [line(shop, "10", "130")])
    issue = post(shop, "issue", [line(shop, "5")])
    assert issue.number == "GIN-000001"
    stock = level(shop)
    assert (stock.quantity, stock.value) == (D("15.0000"), D("1725.00"))
    assert inventory_balance() == D("1725.00")
    assert StockMove.objects.filter(product=shop.soap).count() == 3


def test_fifo_issues_the_oldest_cost_first(fifo_shop: Shop) -> None:
    post(fifo_shop, "receipt", [line(fifo_shop, "5", "10")])
    post(fifo_shop, "receipt", [line(fifo_shop, "10", "12")])
    issue = post(fifo_shop, "issue", [line(fifo_shop, "8")])
    move = StockMove.objects.get(entry=issue)
    assert move.value == D("-86.00")
    assert list(CostLayer.objects.order_by("id").values_list("quantity_left", flat=True)) == [
        D(0),
        D(7),
    ]
    assert level(fifo_shop).value == D("84.00")
    assert inventory_balance() == D("84.00")


def test_fifo_emptying_a_level_keeps_books_and_stock_equal(fifo_shop: Shop) -> None:
    post(fifo_shop, "receipt", [line(fifo_shop, "3", "10")])
    level(fifo_shop).value = D("30.01")
    StockLevel.objects.filter(pk=level(fifo_shop).pk).update(value=D("30.01"))
    issue = post(fifo_shop, "issue", [line(fifo_shop, "3")])
    assert StockMove.objects.get(entry=issue).value == D("-30.01")
    assert level(fifo_shop).value == D(0)


@pytest.mark.parametrize("issue_size", ["1", "7"])
def test_fifo_sub_paisa_costs_never_drift_below_zero(fifo_shop: Shop, issue_size: str) -> None:
    # 150 units: rounding every unit to 0.11 would have gone below zero after 145 issues.
    post(fifo_shop, "receipt", [line(fifo_shop, "150", "0.1060")])
    issued = D(0)
    total_cost = D(0)
    while level(fifo_shop).quantity >= D(issue_size):
        entry = post(fifo_shop, "issue", [line(fifo_shop, issue_size)])
        total_cost -= StockMove.objects.get(entry=entry).value
        issued += D(issue_size)
        assert level(fifo_shop).value >= 0
    if level(fifo_shop).quantity:
        entry = post(fifo_shop, "issue", [line(fifo_shop, str(level(fifo_shop).quantity))])
        total_cost -= StockMove.objects.get(entry=entry).value
    assert level(fifo_shop).value == D(0)
    assert total_cost == D("15.90")
    assert inventory_balance() == D(0)


def test_fifo_many_small_receipts_keep_their_rounding(fifo_shop: Shop) -> None:
    # 100 receipts of one unit at 0.1060 are booked at 0.11 each, 11.00 in all. Revaluing from
    # the unrounded layers (10.60) would charge the first issue 0.51.
    post(fifo_shop, "receipt", [line(fifo_shop, "1", "0.1060") for _ in range(100)])
    assert level(fifo_shop).value == D("11.00")
    issue = post(fifo_shop, "issue", [line(fifo_shop, "1")])
    assert StockMove.objects.get(entry=issue).value == D("-0.11")
    assert level(fifo_shop).value == D("10.89")


def test_alerts_skip_deactivated_owners_and_link_to_the_business(shop: Shop) -> None:
    post(shop, "receipt", [line(shop, "1", "10")])
    assert send_stock_alerts() == 1
    assert f"/app/t/{shop.member.tenant.public_id}/inventory/alerts" in str(mail.outbox[-1].body)
    shop.member.user.is_active = False
    shop.member.user.save()
    assert send_stock_alerts() == 0


def test_stock_value_sums_every_row(shop: Shop) -> None:
    post(shop, "receipt", [line(shop, "2", "10")])
    post(shop, "transfer", [line(shop, "1")], to_warehouse=shop.branch)
    client = shop.member.client()
    assert client.get("/api/inventory/stock-value/").json() == {"total_value": "20.00", "lines": 2}
    branch = client.get(f"/api/inventory/stock-value/?warehouse={shop.branch.pk}").json()
    assert branch == {"total_value": "10.00", "lines": 1}


def test_packs_convert_to_base_units(shop: Shop) -> None:
    post(shop, "receipt", [line(shop, "2", "1200", unit=shop.ctn)])
    assert (level(shop).quantity, level(shop).value) == (D("24.0000"), D("2400.00"))
    other = Product.objects.create(sku="X", name="X", unit=shop.ctn)
    with pytest.raises(services.UnknownPackError):
        post(shop, "receipt", [services.LineInput(other, shop.pcs, D(1), D(1))])


def test_transfers_move_cost_without_a_journal_entry(fifo_shop: Shop) -> None:
    post(fifo_shop, "receipt", [line(fifo_shop, "4", "10")])
    post(fifo_shop, "receipt", [line(fifo_shop, "4", "20")])
    journals = JournalEntry.objects.count()
    transfer = post(fifo_shop, "transfer", [line(fifo_shop, "6")], to_warehouse=fifo_shop.branch)
    assert transfer.journal_entry is None
    assert JournalEntry.objects.count() == journals
    assert (level(fifo_shop).quantity, level(fifo_shop).value) == (D(2), D("40.00"))
    branch = level(fifo_shop, fifo_shop.branch)
    assert (branch.quantity, branch.value) == (D(6), D("80.00"))
    assert sorted(
        CostLayer.objects.filter(warehouse=fifo_shop.branch).values_list("unit_cost", flat=True)
    ) == [D(10), D(20)]
    with pytest.raises(services.BadTransferError):
        post(fifo_shop, "transfer", [line(fifo_shop, "1")], to_warehouse=fifo_shop.main)


def test_average_transfer(shop: Shop) -> None:
    post(shop, "receipt", [line(shop, "3", "10")])
    post(shop, "transfer", [line(shop, "1")], to_warehouse=shop.branch)
    assert level(shop, shop.branch).value == D("10.00")


def test_adjustments_count_up_and_down(shop: Shop) -> None:
    post(shop, "receipt", [line(shop, "10", "50")])
    found = post(shop, "adjustment", [line(shop, "12")])
    assert level(shop).quantity == D(12)
    assert level(shop).value == D("600.00")
    assert found.journal_entry is not None
    lost = post(shop, "adjustment", [line(shop, "9")])
    assert level(shop).quantity == D(9)
    assert lost.number == "ADJ-000002"
    same = post(shop, "adjustment", [line(shop, "9")])
    assert same.journal_entry is None
    priced = post(shop, "adjustment", [line(shop, "10", "80")])
    assert StockMove.objects.get(entry=priced).value == D("80.00")


def test_adjusting_an_empty_product_uses_zero_cost(shop: Shop) -> None:
    post(shop, "adjustment", [line(shop, "3")])
    assert (level(shop).quantity, level(shop).value) == (D(3), D(0))


def test_batches_and_alerts(shop: Shop) -> None:
    shop.soap.track_batches = True
    shop.soap.save()
    with pytest.raises(services.BatchRequiredError):
        post(shop, "receipt", [line(shop, "3", "10")])
    soon = timezone.localdate() + timedelta(days=10)
    post(shop, "receipt", [line(shop, "3", "10", batch_number="B1", expiry_date=soon)])
    with pytest.raises(services.NotEnoughStockError):
        post(shop, "issue", [line(shop, "1", batch_number="NOPE")])
    with pytest.raises(services.NotEnoughStockError):
        post(shop, "issue", [line(shop, "4", batch_number="B1")])
    post(shop, "issue", [line(shop, "1", batch_number="B1")])
    assert BatchLevel.objects.get(batch__number="B1").quantity == D(2)
    post(shop, "transfer", [line(shop, "1", batch_number="B1")], to_warehouse=shop.branch)
    post(shop, "adjustment", [line(shop, "3", batch_number="B1")])
    assert BatchLevel.objects.get(batch__number="B1", warehouse=shop.main).quantity == D(3)

    alerts = shop.member.client().get("/api/inventory/alerts/").json()
    assert [row["sku"] for row in alerts["low_stock"]] == ["SOAP-1"]
    assert {row["number"] for row in alerts["expiring"]} == {"B1"}
    assert send_stock_alerts() == 1
    assert "Invented Soap" in str(mail.outbox[-1].body)


def test_batch_creation_race_falls_back_to_the_existing_row(shop: Shop) -> None:
    shop.soap.track_batches = True
    shop.soap.save()
    Batch.objects.create(product=shop.soap, number="B9")
    post(shop, "receipt", [line(shop, "1", "1", batch_number="B9")])
    assert Batch.objects.filter(number="B9").count() == 1


def test_failed_posts_change_nothing(shop: Shop) -> None:
    post(shop, "receipt", [line(shop, "1", "10")])
    before = (
        level(shop).quantity,
        NumberSeries.objects.get(key="GIN").next_number
        if NumberSeries.objects.filter(key="GIN").exists()
        else 1,
    )
    with pytest.raises(services.NotEnoughStockError):
        post(shop, "issue", [line(shop, "2")])
    after_series = (
        NumberSeries.objects.filter(key="GIN").values_list("next_number", flat=True).first() or 1
    )
    assert (level(shop).quantity, after_series) == before
    with pytest.raises(services.CostRequiredError):
        post(shop, "receipt", [line(shop, "1")])
    empty = services.save_draft(
        shop.member.user,
        {"kind": "receipt", "date": timezone.localdate(), "memo": "", "warehouse": shop.main},
        [],
    )
    with pytest.raises(services.NoLinesError):
        services.post_entry(shop.member.user, empty)


def test_closed_periods_block_stock_posting(shop: Shop) -> None:
    period = FiscalPeriod.objects.get(
        start__lte=timezone.localdate(), end__gte=timezone.localdate()
    )
    period.closed_at = timezone.now()
    period.save()
    client = shop.member.client()
    draft = services.save_draft(
        shop.member.user,
        {"kind": "receipt", "date": timezone.localdate(), "memo": "", "warehouse": shop.main},
        [line(shop, "1", "10")],
    )
    response = client.post(f"/api/inventory/stock-entries/{draft.pk}/post/")
    assert response.status_code == 400
    assert "open fiscal period" in response.json()["detail"]
    assert StockLevel.objects.filter(product=shop.soap, quantity__gt=0).count() == 0


def test_posted_stock_entries_are_immutable(shop: Shop) -> None:
    entry = post(shop, "receipt", [line(shop, "1", "10")])
    entry.memo = "Changed"
    with pytest.raises(PostedEntryError):
        entry.save()
    with pytest.raises(PostedEntryError):
        entry.delete()
    stale = StockEntry.objects.get(pk=entry.pk)
    stale.status = StockEntry.Status.DRAFT
    with pytest.raises(services.AlreadyPostedError):
        services.delete_draft(shop.member.user, stale)
    with pytest.raises(services.AlreadyPostedError):
        services.post_entry(shop.member.user, stale)


@pytest.mark.django_db(transaction=True)
def test_two_cashiers_cannot_both_sell_the_last_item() -> None:
    shop = make_shop()
    with tenant_context(shop.member.tenant):
        post(shop, "receipt", [line(shop, "1", "10")])
        drafts = [
            services.save_draft(
                shop.member.user,
                {
                    "kind": "issue",
                    "date": timezone.localdate(),
                    "memo": "",
                    "warehouse": shop.main,
                },
                [line(shop, "1")],
            )
            for _ in range(2)
        ]
    results: list[str] = []
    barrier = threading.Barrier(2)

    def sell(entry: StockEntry) -> None:
        try:
            with tenant_context(shop.member.tenant):
                barrier.wait()
                services.post_entry(shop.member.user, entry)
                results.append("sold")
        except services.NotEnoughStockError:
            results.append("refused")
        finally:
            connection.close()

    threads = [threading.Thread(target=sell, args=(entry,)) for entry in drafts]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == ["refused", "sold"]
    with tenant_context(shop.member.tenant):
        assert level(shop).quantity == 0


@pytest.mark.django_db(transaction=True)
def test_first_receipts_racing_on_a_new_level_both_land() -> None:
    shop = make_shop()
    with tenant_context(shop.member.tenant):
        drafts = [
            services.save_draft(
                shop.member.user,
                {
                    "kind": "receipt",
                    "date": timezone.localdate(),
                    "memo": "",
                    "warehouse": shop.main,
                },
                [line(shop, "2", "5")],
            )
            for _ in range(3)
        ]
    errors: list[BaseException] = []
    barrier = threading.Barrier(3)

    def receive(entry: StockEntry) -> None:
        try:
            with tenant_context(shop.member.tenant):
                barrier.wait()
                services.post_entry(shop.member.user, entry)
        except BaseException as exc:
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=receive, args=(entry,)) for entry in drafts]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    with tenant_context(shop.member.tenant):
        assert (level(shop).quantity, level(shop).value) == (D(6), D("30.00"))


def test_permissions_follow_the_role(shop: Shop) -> None:
    role = Role.objects.create(name="Clerk", permissions={"inventory": ["view", "create"]})
    clerk = create_user()
    Membership.objects.create(user=clerk, role=role)
    client = APIClient()
    client.force_login(clerk)
    client.credentials(HTTP_X_TENANT=str(shop.member.tenant.public_id))
    draft = services.save_draft(
        shop.member.user,
        {"kind": "receipt", "date": timezone.localdate(), "memo": "", "warehouse": shop.main},
        [line(shop, "1", "1")],
    )
    assert client.get("/api/inventory/products/").status_code == 200
    assert client.post(f"/api/inventory/stock-entries/{draft.pk}/post/").status_code == 403
