import threading
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.utils import timezone

from apps.accounting.models import Account, PostedEntryError
from apps.accounting.reports import trial_balance
from apps.accounts.models import User
from apps.inventory.models import StockLevel
from apps.purchasing import services
from apps.purchasing.models import (
    Bill,
    GoodsReceipt,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierPayment,
)
from apps.tenancy.context import tenant_context
from apps.tenancy.models import AuditEvent
from tests.conftest import make_member
from tests.inventory.conftest import Shop, make_shop

pytestmark = pytest.mark.django_db
D = Decimal


@dataclass
class Buyer:
    shop: Shop
    supplier: Supplier
    other: Supplier

    @property
    def user(self) -> User:
        return self.shop.member.user


def make_buyer() -> Buyer:
    shop = make_shop()
    with tenant_context(shop.member.tenant):
        supplier = Supplier.objects.create(
            code="S1", name="Invented Traders", payment_terms_days=30
        )
        other = Supplier.objects.create(code="S2", name="Imaginary Wholesale")
    return Buyer(shop, supplier, other)


@pytest.fixture
def buyer(db: None) -> Iterator[Buyer]:
    built = make_buyer()
    with tenant_context(built.shop.member.tenant):
        yield built


def balance(code: str) -> Decimal:
    report = trial_balance(timezone.localdate())
    return next((row.debit - row.credit for row in report.rows if row.code == code), D(0))


def order(
    b: Buyer, quantity: str = "10", price: str = "100", confirm: bool = True
) -> PurchaseOrder:
    draft = services.save_order(
        b.user,
        {"supplier": b.supplier, "date": timezone.localdate(), "warehouse": b.shop.main},
        [services.OrderLineInput(b.shop.soap, b.shop.pcs, D(quantity), D(price))],
    )
    return services.confirm_order(b.user, draft) if confirm else draft


def receive(b: Buyer, po: PurchaseOrder, quantity: str | None = None) -> GoodsReceipt:
    receipt = services.receive_order(b.user, po, timezone.localdate())
    if quantity is not None:
        line = receipt.lines.get()
        services.save_receipt(
            b.user,
            {},
            [
                services.ReceiptLineInput(
                    line.product, line.unit, D(quantity), line.unit_cost, line.order_line
                )
            ],
            receipt,
        )
    return services.post_receipt(b.user, receipt)


def bill(b: Buyer, receipt: GoodsReceipt, price: str | None = None, tax: str = "0") -> Bill:
    draft = services.bill_receipt(b.user, receipt, timezone.localdate())
    if price is not None or tax != "0":
        line = draft.lines.get()
        services.save_bill(
            b.user,
            {},
            [
                services.BillLineInput(
                    line.quantity,
                    D(price) if price else line.unit_price,
                    receipt_line=line.receipt_line,
                    tax_amount=D(tax),
                )
            ],
            draft,
        )
    return services.post_bill(b.user, draft)


def pay(b: Buyer, amount: str, allocations: list[tuple[Bill, str]]) -> SupplierPayment:
    draft = services.save_payment(
        b.user,
        {
            "supplier": b.supplier,
            "date": timezone.localdate(),
            "amount": D(amount),
            "paid_from": Account.objects.get(role="bank"),
        },
        [services.AllocationInput(target, D(value)) for target, value in allocations],
    )
    return services.post_payment(b.user, draft)


def test_order_to_payment_keeps_every_book_straight(buyer: Buyer) -> None:
    po = order(buyer)
    assert po.number == "PO-000001"
    assert po.total == D("1000.00")

    receipt = receive(buyer, po)
    assert receipt.number == "GRN-000001"
    assert PurchaseOrder.objects.get(pk=po.pk).status == PurchaseOrder.Status.CLOSED
    assert StockLevel.objects.get(product=buyer.shop.soap).value == D("1000.00")
    assert balance("2160") == D("-1000.00")

    posted = bill(buyer, receipt, tax="180")
    assert posted.number == "BILL-000001"
    assert posted.due_date == timezone.localdate() + timedelta(days=30)
    assert (posted.net, posted.tax, posted.total) == (D("1000.00"), D("180.00"), D("1180.00"))
    assert balance("2160") == D(0)
    assert balance("1150") == D("180.00")
    assert balance("2110") == D("-1180.00")

    payment = pay(buyer, "1500", [(posted, "1180")])
    assert payment.number == "PAY-000001"
    assert Bill.objects.get(pk=posted.pk).amount_paid == D("1180.00")
    # The extra 320 is an advance: payables swing to a debit balance.
    assert balance("2110") == D("320.00")
    assert balance("1120") == D("-1500.00")
    assert services.outstanding_bills(buyer.supplier).count() == 0
    actions = set(AuditEvent.objects.values_list("action", flat=True))
    assert {"create", "post"} <= actions


def test_partial_receipts_and_bills_clear_grni_exactly(buyer: Buyer) -> None:
    po = order(buyer, quantity="3", price="3.3333")
    first = receive(buyer, po, quantity="1")
    assert PurchaseOrder.objects.get(pk=po.pk).status == PurchaseOrder.Status.CONFIRMED
    second = receive(buyer, PurchaseOrder.objects.get(pk=po.pk))
    assert [line.quantity for line in second.lines.all()] == [D(2)]
    assert PurchaseOrder.objects.get(pk=po.pk).status == PurchaseOrder.Status.CLOSED

    received = sum((line.value for r in (first, second) for line in r.lines.all()), D(0))
    assert balance("2160") == -received
    draft = services.bill_receipt(buyer.user, second, timezone.localdate())
    line = draft.lines.get()
    services.save_bill(
        buyer.user,
        {},
        [services.BillLineInput(D(1), line.unit_price, receipt_line=line.receipt_line)],
        draft,
    )
    services.post_bill(buyer.user, draft)
    bill(buyer, second)
    bill(buyer, first)
    assert balance("2160") == D(0)


def test_price_differences_go_to_purchase_variance(buyer: Buyer) -> None:
    dearer = receive(buyer, order(buyer, quantity="10", price="100"))
    bill(buyer, dearer, price="105")
    assert balance("5300") == D("50.00")
    cheaper = receive(buyer, order(buyer, quantity="10", price="100"))
    bill(buyer, cheaper, price="98")
    assert balance("5300") == D("30.00")
    assert balance("2160") == D(0)


def test_expense_bills_need_no_receipt(buyer: Buyer) -> None:
    rent = Account.objects.get(code="6200")
    draft = services.save_bill(
        buyer.user,
        {"supplier": buyer.supplier, "date": timezone.localdate(), "supplier_reference": "R-7"},
        [services.BillLineInput(D(1), D("25000"), account=rent, description="Shop rent")],
    )
    posted = services.post_bill(buyer.user, draft)
    assert posted.total == D("25000.00")
    assert balance("6200") == D("25000.00")


def test_over_receiving_and_over_billing_are_refused(buyer: Buyer) -> None:
    po = order(buyer, quantity="5")
    receipt = services.receive_order(buyer.user, po, timezone.localdate())
    line = receipt.lines.get()
    services.save_receipt(
        buyer.user,
        {},
        [services.ReceiptLineInput(line.product, line.unit, D(6), D(100), line.order_line)],
        receipt,
    )
    with pytest.raises(services.OverReceivedError):
        services.post_receipt(buyer.user, receipt)
    services.save_receipt(
        buyer.user,
        {},
        [services.ReceiptLineInput(line.product, line.unit, D(5), D(100), line.order_line)],
        receipt,
    )
    posted = services.post_receipt(buyer.user, receipt)
    with pytest.raises(services.OrderNotOpenError):
        services.receive_order(
            buyer.user, PurchaseOrder.objects.get(pk=po.pk), timezone.localdate()
        )

    first = services.bill_receipt(buyer.user, posted, timezone.localdate())
    second = services.bill_receipt(buyer.user, posted, timezone.localdate())
    services.post_bill(buyer.user, first)
    with pytest.raises(services.OverBilledError):
        services.post_bill(buyer.user, second)
    with pytest.raises(services.OverBilledError):
        services.bill_receipt(buyer.user, posted, timezone.localdate())
    assert balance("2160") == D(0)


def test_documents_must_stay_with_one_supplier(buyer: Buyer) -> None:
    posted = receive(buyer, order(buyer))
    line = posted.lines.get()
    with pytest.raises(services.WrongSupplierError):
        services.save_bill(
            buyer.user,
            {"supplier": buyer.other, "date": timezone.localdate()},
            [services.BillLineInput(D(1), D(100), receipt_line=line)],
        )
    own = bill(buyer, posted)
    with pytest.raises(services.WrongSupplierError):
        services.save_payment(
            buyer.user,
            {
                "supplier": buyer.other,
                "date": timezone.localdate(),
                "amount": D(10),
                "paid_from": Account.objects.get(role="cash"),
            },
            [services.AllocationInput(own, D(10))],
        )
    draft_order = order(buyer, confirm=False)
    with pytest.raises(services.OrderNotOpenError):
        services.save_receipt(
            buyer.user,
            {
                "supplier": buyer.supplier,
                "purchase_order": draft_order,
                "date": timezone.localdate(),
                "warehouse": buyer.shop.main,
            },
            [],
        )


def test_payments_cannot_overpay_or_use_the_wrong_account(buyer: Buyer) -> None:
    posted = bill(buyer, receive(buyer, order(buyer, quantity="1", price="100")))
    with pytest.raises(services.OverAllocatedError):
        pay(buyer, "50", [(posted, "60")])
    with pytest.raises(services.OverAllocatedError):
        pay(buyer, "500", [(posted, "101")])
    draft = services.save_payment(
        buyer.user,
        {
            "supplier": buyer.supplier,
            "date": timezone.localdate(),
            "amount": D(10),
            "paid_from": Account.objects.get(role="sales"),
        },
        [],
    )
    with pytest.raises(services.BadAccountError):
        services.post_payment(buyer.user, draft)
    assert Bill.objects.get(pk=posted.pk).amount_paid == D(0)
    assert SupplierPayment.objects.filter(status="posted").count() == 0


def test_empty_and_invalid_documents_are_refused(buyer: Buyer) -> None:
    with pytest.raises(services.NoLinesError):
        services.confirm_order(
            buyer.user,
            PurchaseOrder.objects.create(
                supplier=buyer.supplier,
                date=timezone.localdate(),
                warehouse=buyer.shop.main,
                created_by=buyer.user,
            ),
        )
    empty = services.save_bill(
        buyer.user, {"supplier": buyer.supplier, "date": timezone.localdate()}, []
    )
    with pytest.raises(services.NoLinesError):
        services.post_bill(buyer.user, empty)
    free = services.save_bill(
        buyer.user,
        {"supplier": buyer.supplier, "date": timezone.localdate()},
        [services.BillLineInput(D(1), D(0), account=Account.objects.get(code="6200"))],
    )
    with pytest.raises(services.EmptyDocumentError):
        services.post_bill(buyer.user, free)
    group = Account.objects.get(code="6000")
    grouped = services.save_bill(
        buyer.user,
        {"supplier": buyer.supplier, "date": timezone.localdate()},
        [services.BillLineInput(D(1), D(5), account=group)],
    )
    with pytest.raises(services.BadExpenseAccountError):
        services.post_bill(buyer.user, grouped)
    with pytest.raises(services.BadExpenseAccountError):
        services.save_bill(
            buyer.user,
            {"supplier": buyer.supplier, "date": timezone.localdate()},
            [services.BillLineInput(D(1), D(5))],
        )
    loose = services.save_receipt(
        buyer.user,
        {"supplier": buyer.supplier, "date": timezone.localdate(), "warehouse": buyer.shop.main},
        [],
    )
    with pytest.raises(services.NoLinesError):
        services.post_receipt(buyer.user, loose)
    unposted = services.save_receipt(
        buyer.user,
        {"supplier": buyer.supplier, "date": timezone.localdate(), "warehouse": buyer.shop.main},
        [services.ReceiptLineInput(buyer.shop.soap, buyer.shop.pcs, D(1), D(5))],
    )
    with pytest.raises(services.ReceiptNotPostedError):
        services.bill_receipt(buyer.user, unposted, timezone.localdate())
    with pytest.raises(services.ReceiptNotPostedError):
        services.save_bill(
            buyer.user,
            {"supplier": buyer.supplier, "date": timezone.localdate()},
            [services.BillLineInput(D(1), D(5), receipt_line=unposted.lines.get())],
        )


def test_receipts_without_an_order_and_closing_orders(buyer: Buyer) -> None:
    loose = services.save_receipt(
        buyer.user,
        {"supplier": buyer.supplier, "date": timezone.localdate(), "warehouse": buyer.shop.main},
        [services.ReceiptLineInput(buyer.shop.soap, buyer.shop.pcs, D(4), D(25))],
    )
    services.post_receipt(buyer.user, loose)
    assert balance("2160") == D("-100.00")
    po = order(buyer)
    closed = services.close_order(buyer.user, po)
    assert closed.status == PurchaseOrder.Status.CLOSED
    with pytest.raises(services.OrderNotOpenError):
        services.close_order(buyer.user, closed)
    with pytest.raises(services.OrderNotOpenError):
        services.receive_order(buyer.user, closed, timezone.localdate())


def test_order_line_must_match_and_belong_to_the_order(buyer: Buyer) -> None:
    po = order(buyer)
    other_po = order(buyer)
    foreign_line = other_po.lines.get()
    with pytest.raises(services.WrongSupplierError):
        services.save_receipt(
            buyer.user,
            {
                "supplier": buyer.supplier,
                "purchase_order": po,
                "date": timezone.localdate(),
                "warehouse": buyer.shop.main,
            },
            [services.ReceiptLineInput(buyer.shop.soap, buyer.shop.pcs, D(1), D(1), foreign_line)],
        )
    receipt = services.receive_order(buyer.user, po, timezone.localdate())
    line = receipt.lines.get()
    services.save_receipt(
        buyer.user,
        {},
        [services.ReceiptLineInput(line.product, buyer.shop.ctn, D(1), D(1), line.order_line)],
        receipt,
    )
    with pytest.raises(services.LineMismatchError):
        services.post_receipt(buyer.user, receipt)


def test_posted_documents_are_immutable(buyer: Buyer) -> None:
    posted = bill(buyer, receive(buyer, order(buyer)))
    posted.memo = "changed"
    with pytest.raises(PostedEntryError):
        posted.save()
    with pytest.raises(PostedEntryError):
        posted.delete()
    stale = Bill.objects.get(pk=posted.pk)
    stale.status = "draft"
    with pytest.raises(services.NotDraftError):
        services.post_bill(buyer.user, stale)
    with pytest.raises(services.NotDraftError):
        services.delete_draft(buyer.user, stale)
    draft = order(buyer, confirm=False)
    services.delete_draft(buyer.user, draft)
    assert not PurchaseOrder.objects.filter(pk=draft.pk).exists()
    assert PurchaseOrderLine.objects.filter(order_id=draft.pk).count() == 0


def test_supplier_balance_and_api_flow(buyer: Buyer) -> None:
    client = buyer.shop.member.client()
    created = client.post(
        "/api/purchasing/suppliers/",
        {"code": "S3", "name": "Made-up Mills", "payment_terms_days": 15},
        format="json",
    )
    assert created.status_code == 201, created.json()
    supplier = created.json()["id"]
    assert (
        client.post(
            "/api/purchasing/suppliers/", {"code": "S3", "name": "Again"}, format="json"
        ).status_code
        == 400
    )

    today = str(timezone.localdate())
    po = client.post(
        "/api/purchasing/orders/",
        {
            "supplier": supplier,
            "date": today,
            "warehouse": buyer.shop.main.pk,
            "lines": [
                {
                    "product": buyer.shop.soap.pk,
                    "unit": buyer.shop.pcs.pk,
                    "quantity": "4",
                    "unit_price": "50",
                }
            ],
        },
        format="json",
    )
    assert po.status_code == 201, po.json()
    po_id = po.json()["id"]
    assert po.json()["total"] == "200.00"
    assert client.post(f"/api/purchasing/orders/{po_id}/confirm/").json()["number"] == "PO-000001"
    receipt = client.post(f"/api/purchasing/orders/{po_id}/receive/", {}, format="json")
    assert receipt.status_code == 201, receipt.json()
    receipt_id = receipt.json()["id"]
    posted = client.post(f"/api/purchasing/receipts/{receipt_id}/post/")
    assert posted.json()["status"] == "posted"
    draft_bill = client.post(
        f"/api/purchasing/receipts/{receipt_id}/bill/", {"date": today}, format="json"
    )
    assert draft_bill.status_code == 201
    bill_id = draft_bill.json()["id"]
    assert client.post(f"/api/purchasing/bills/{bill_id}/post/").json()["total"] == "200.00"
    listed = client.get("/api/purchasing/suppliers/?q=made").json()["results"]
    assert listed[0]["balance"] == "200.00"
    payment = client.post(
        "/api/purchasing/payments/",
        {
            "supplier": supplier,
            "date": today,
            "amount": "200",
            "paid_from": Account.objects.get(role="cash").pk,
            "allocations": [{"bill": bill_id, "amount": "200"}],
        },
        format="json",
    )
    assert payment.status_code == 201, payment.json()
    paid = client.post(f"/api/purchasing/payments/{payment.json()['id']}/post/")
    assert paid.json()["number"] == "PAY-000001"
    assert client.get(f"/api/purchasing/suppliers/{supplier}/").json()["balance"] == "0.00"
    assert (
        client.get("/api/purchasing/bills/?status=posted&supplier=" + str(supplier)).json()[
            "results"
        ][0]["amount_paid"]
        == "200.00"
    )

    refused = client.post(f"/api/purchasing/bills/{bill_id}/post/")
    assert refused.status_code == 400
    assert refused.json()["detail"] == services.NotDraftError.message
    assert client.delete(f"/api/purchasing/suppliers/{supplier}/").status_code == 400
    bad_line = client.post(
        "/api/purchasing/bills/",
        {"supplier": supplier, "date": today, "lines": [{"quantity": "1", "unit_price": "1"}]},
        format="json",
    )
    assert bad_line.status_code == 400
    po2 = client.post(
        "/api/purchasing/orders/",
        {"supplier": supplier, "date": today, "warehouse": buyer.shop.main.pk, "lines": []},
        format="json",
    ).json()["id"]
    assert (
        client.put(
            f"/api/purchasing/orders/{po2}/",
            {"supplier": supplier, "date": today, "warehouse": buyer.shop.main.pk, "lines": []},
            format="json",
        ).status_code
        == 200
    )
    assert client.post(f"/api/purchasing/orders/{po2}/close/").status_code == 400
    assert client.delete(f"/api/purchasing/orders/{po2}/").status_code == 204


def test_purchasing_needs_permission() -> None:
    client = make_member({"purchasing": ["view"]}).client()
    assert client.get("/api/purchasing/suppliers/").status_code == 200
    assert (
        make_member({"inventory": ["view"]}).client().get("/api/purchasing/suppliers/").status_code
        == 403
    )
    assert client.get("/api/purchasing/suppliers/").status_code == 200
    assert (
        client.post(
            "/api/purchasing/suppliers/", {"code": "X", "name": "X"}, format="json"
        ).status_code
        == 403
    )


@pytest.mark.django_db(transaction=True)
def test_two_payments_cannot_both_settle_one_bill() -> None:
    b = make_buyer()
    with tenant_context(b.shop.member.tenant):
        posted = bill(b, receive(b, order(b, quantity="1", price="100")))
        drafts = [
            services.save_payment(
                b.user,
                {
                    "supplier": b.supplier,
                    "date": timezone.localdate(),
                    "amount": D(100),
                    "paid_from": Account.objects.get(role="cash"),
                },
                [services.AllocationInput(posted, D(100))],
            )
            for _ in range(2)
        ]
    results: list[str] = []
    barrier = threading.Barrier(2)

    def settle(payment: SupplierPayment) -> None:
        try:
            with tenant_context(b.shop.member.tenant):
                barrier.wait()
                services.post_payment(b.user, payment)
                results.append("paid")
        except services.OverAllocatedError:
            results.append("refused")
        finally:
            connection.close()

    threads = [threading.Thread(target=settle, args=(draft,)) for draft in drafts]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == ["paid", "refused"]
    with tenant_context(b.shop.member.tenant):
        assert Bill.objects.get(pk=posted.pk).amount_paid == D("100.00")
