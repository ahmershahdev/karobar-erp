import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from django.db import connection
from django.utils import timezone

from apps.accounting.models import Account, PostedEntryError
from apps.accounting.reports import trial_balance
from apps.accounts.models import User
from apps.inventory import services as inventory
from apps.inventory.models import StockEntry, StockLevel
from apps.sales import documents, reports, services
from apps.sales.models import CreditNote, Customer, CustomerReceipt, Invoice, SalesOrder
from apps.tenancy.context import tenant_context
from tests.inventory.conftest import Shop, make_shop

pytestmark = pytest.mark.django_db
D = Decimal


@dataclass
class Seller:
    shop: Shop
    customer: Customer
    other: Customer

    @property
    def user(self) -> User:
        return self.shop.member.user


def stock_up(shop: Shop, quantity: str = "20", cost: str = "60") -> None:
    entry = inventory.save_draft(
        shop.member.user,
        {
            "kind": StockEntry.Kind.RECEIPT,
            "date": timezone.localdate(),
            "warehouse": shop.main,
            "contra_account": Account.objects.get(role="capital"),
        },
        [inventory.LineInput(shop.soap, shop.pcs, D(quantity), D(cost))],
    )
    inventory.post_entry(shop.member.user, entry)


def make_seller() -> Seller:
    shop = make_shop()
    with tenant_context(shop.member.tenant):
        stock_up(shop)
        customer = Customer.objects.create(
            code="C1", name="Invented Kiryana", payment_terms_days=15
        )
        other = Customer.objects.create(code="C2", name="Imaginary Store")
    return Seller(shop, customer, other)


@pytest.fixture
def seller(db: None) -> Iterator[Seller]:
    built = make_seller()
    with tenant_context(built.shop.member.tenant):
        yield built


def role_balance(role: str) -> Decimal:
    code = Account.objects.get(role=role).code
    report = trial_balance(timezone.localdate())
    row = next((row for row in report.rows if row.code == code), None)
    return (row.debit - row.credit) if row else D(0)


def owed(s: Seller, customer: Customer | None = None) -> Decimal:
    target = customer or s.customer
    return cast(Decimal, cast(Any, services.customers().get(pk=target.pk)).balance)


def order(s: Seller, quantity: str = "10", price: str = "100", tax: str = "180") -> SalesOrder:
    return services.save_order(
        s.user,
        {"customer": s.customer, "warehouse": s.shop.main, "date": timezone.localdate()},
        [services.OrderLineInput(s.shop.soap, s.shop.pcs, D(quantity), D(price), D(tax))],
    )


def invoice(s: Seller, quantity: str = "10", price: str = "100", tax: str = "180") -> Invoice:
    draft = services.save_invoice(
        s.user,
        {"customer": s.customer, "warehouse": s.shop.main, "date": timezone.localdate()},
        [services.InvoiceLineInput(s.shop.soap, s.shop.pcs, D(quantity), D(price), D(tax))],
    )
    return services.post_invoice(s.user, draft)


def receipt(s: Seller, amount: str, allocations: list[tuple[Invoice, str]]) -> CustomerReceipt:
    draft = services.save_receipt(
        s.user,
        {
            "customer": s.customer,
            "date": timezone.localdate(),
            "amount": D(amount),
            "received_into": Account.objects.get(role="bank"),
        },
        [services.AllocationInput(target, D(value)) for target, value in allocations],
    )
    return services.post_receipt(s.user, draft)


def stock(s: Seller) -> StockLevel:
    level: StockLevel = StockLevel.objects.get(product=s.shop.soap, warehouse=s.shop.main)
    return level


def test_quote_to_order_to_invoice_to_cash_keeps_every_book_straight(seller: Seller) -> None:
    draft = order(seller)
    assert draft.total == D("1180.00")

    quoted = services.quote_order(seller.user, draft)
    assert quoted.quote_number == "QUO-000001"
    assert quoted.number is None

    confirmed = services.confirm_order(seller.user, quoted)
    assert confirmed.number == "SO-000001"
    assert confirmed.status == SalesOrder.Status.CONFIRMED

    posted = services.post_invoice(
        seller.user, services.invoice_order(seller.user, confirmed, timezone.localdate())
    )
    assert posted.number == "INV-000001"
    assert (posted.net, posted.tax, posted.total) == (D("1000.00"), D("180.00"), D("1180.00"))
    assert posted.cost == D("600.00")
    assert posted.due_date == posted.date + timedelta(days=15)
    assert SalesOrder.objects.get(pk=draft.pk).status == SalesOrder.Status.CLOSED
    assert stock(seller).quantity == D("10")
    assert role_balance("receivables") == D("1180.00")
    assert role_balance("sales") == D("-1000.00")
    assert role_balance("tax_output") == D("-180.00")
    assert role_balance("cogs") == D("600.00")
    assert owed(seller) == D("1180.00")

    paid = receipt(seller, "1500", [(posted, "1180")])
    assert paid.number == "RCT-000001"
    assert Invoice.objects.get(pk=posted.pk).amount_paid == D("1180.00")
    # The extra 320 is an advance, so the customer's balance goes below zero.
    assert role_balance("receivables") == D("-320.00")
    assert owed(seller) == D("-320.00")


def test_an_invoice_can_be_taken_in_parts(seller: Seller) -> None:
    confirmed = services.confirm_order(seller.user, order(seller, tax="100"))
    first = services.invoice_order(seller.user, confirmed, timezone.localdate())
    line = first.lines.get()
    part = services.save_invoice(
        seller.user,
        {},
        [
            services.InvoiceLineInput(
                line.product, line.unit, D(3), line.unit_price, D("30"), line.order_line
            )
        ],
        first,
    )
    services.post_invoice(seller.user, part)
    assert SalesOrder.objects.get(pk=confirmed.pk).status == SalesOrder.Status.CONFIRMED
    rest = services.invoice_order(seller.user, confirmed, timezone.localdate())
    assert rest.lines.get().quantity == D("7.0000")
    assert rest.tax == D("70.00")
    services.post_invoice(seller.user, rest)
    assert SalesOrder.objects.get(pk=confirmed.pk).status == SalesOrder.Status.CLOSED


def test_an_order_cannot_be_invoiced_twice(seller: Seller) -> None:
    confirmed = services.confirm_order(seller.user, order(seller))
    first = services.invoice_order(seller.user, confirmed, timezone.localdate())
    second = services.invoice_order(seller.user, confirmed, timezone.localdate())
    services.post_invoice(seller.user, first)
    with pytest.raises(services.OrderNotOpenError):
        services.post_invoice(seller.user, second)


def test_selling_more_than_is_in_stock_fails_and_leaves_nothing(seller: Seller) -> None:
    with pytest.raises(inventory.NotEnoughStockError):
        invoice(seller, quantity="500")
    assert stock(seller).quantity == D("20")
    assert role_balance("receivables") == D(0)
    assert not Invoice.objects.filter(status=Invoice.Status.POSTED).exists()


def test_credit_limit_is_checked_on_order_and_invoice(seller: Seller) -> None:
    seller.customer.credit_limit = D("1000")
    seller.customer.save()
    with pytest.raises(services.CreditLimitError):
        services.confirm_order(seller.user, order(seller))
    with pytest.raises(services.CreditLimitError):
        invoice(seller)
    invoice(seller, quantity="5", tax="0")
    assert owed(seller) == D("500.00")
    with pytest.raises(services.CreditLimitError):
        invoice(seller, quantity="6", tax="0")
    invoice(seller, quantity="5", tax="0")
    assert owed(seller) == D("1000.00")


def test_a_cash_only_customer_can_buy_with_an_advance(seller: Seller) -> None:
    seller.customer.credit_limit = D(0)
    seller.customer.save()
    with pytest.raises(services.CreditLimitError):
        invoice(seller, quantity="1", tax="0")
    receipt(seller, "100", [])
    invoice(seller, quantity="1", tax="0")
    assert owed(seller) == D(0)


def test_a_return_puts_stock_back_at_cost_and_undoes_the_sale(seller: Seller) -> None:
    sold = invoice(seller)
    note = services.post_credit_note(
        seller.user, services.credit_invoice(seller.user, sold, timezone.localdate())
    )
    assert note.number == "CN-000001"
    assert (note.net, note.tax, note.total) == (D("1000.00"), D("180.00"), D("1180.00"))
    assert note.applied == D("1180.00")
    assert stock(seller).quantity == D("20")
    assert stock(seller).value == D("1200.00")
    assert role_balance("receivables") == D(0)
    assert role_balance("sales_returns") == D("1000.00")
    assert role_balance("tax_output") == D(0)
    assert role_balance("cogs") == D(0)
    assert owed(seller) == D(0)
    assert Invoice.objects.get(pk=sold.pk).amount_credited == D("1180.00")


def test_partial_returns_add_up_to_the_exact_line(seller: Seller) -> None:
    sold = invoice(seller, quantity="3", price="33.33", tax="10")
    line = sold.lines.get()
    for _ in range(3):
        fresh = sold.lines.get()
        note = services.save_credit_note(
            seller.user,
            {"invoice": sold, "date": timezone.localdate()},
            [services.CreditLineInput(fresh, D(1))],
        )
        services.post_credit_note(seller.user, note)
    assert sum(n.total for n in CreditNote.objects.all()) == line.amount + line.tax_amount
    assert owed(seller) == D(0)
    assert role_balance("receivables") == D(0)


def test_nothing_can_be_returned_twice(seller: Seller) -> None:
    sold = invoice(seller)
    first = services.credit_invoice(seller.user, sold, timezone.localdate())
    second = services.credit_invoice(seller.user, sold, timezone.localdate())
    services.post_credit_note(seller.user, first)
    with pytest.raises(services.OverReturnedError):
        services.post_credit_note(seller.user, second)
    assert stock(seller).quantity == D("20")


def test_a_return_on_a_paid_invoice_leaves_credit_on_the_account(seller: Seller) -> None:
    sold = invoice(seller)
    receipt(seller, "1180", [(sold, "1180")])
    note = services.post_credit_note(
        seller.user, services.credit_invoice(seller.user, sold, timezone.localdate())
    )
    assert note.applied == D(0)
    assert owed(seller) == D("-1180.00")


def test_receipts_cannot_overpay_or_cross_customers(seller: Seller) -> None:
    sold = invoice(seller)
    with pytest.raises(services.OverAllocatedError):
        receipt(seller, "100", [(sold, "200")])
    with pytest.raises(services.OverAllocatedError):
        receipt(seller, "5000", [(sold, "2000")])
    draft = services.save_receipt(
        seller.user,
        {
            "customer": seller.other,
            "date": timezone.localdate(),
            "amount": D("10"),
            "received_into": Account.objects.get(role="bank"),
        },
        [services.AllocationInput(sold, D("10"))],
    )
    with pytest.raises(services.WrongCustomerError):
        services.post_receipt(seller.user, draft)


def test_money_must_go_into_a_cash_or_bank_account(seller: Seller) -> None:
    draft = services.save_receipt(
        seller.user,
        {
            "customer": seller.customer,
            "date": timezone.localdate(),
            "amount": D("10"),
            "received_into": Account.objects.get(role="sales"),
        },
        [],
    )
    with pytest.raises(services.BadAccountError):
        services.post_receipt(seller.user, draft)


def test_posted_documents_cannot_change(seller: Seller) -> None:
    sold = invoice(seller)
    sold.memo = "changed"
    with pytest.raises(PostedEntryError):
        sold.save()
    with pytest.raises(PostedEntryError):
        sold.delete()
    with pytest.raises(services.NotDraftError):
        services.post_invoice(seller.user, sold)


def test_draft_rules(seller: Seller) -> None:
    with pytest.raises(services.NoLinesError):
        services.save_order(seller.user, {}, [])
    with pytest.raises(services.OrderNotOpenError):
        services.invoice_order(seller.user, order(seller), timezone.localdate())
    draft = order(seller)
    services.delete_draft(seller.user, draft)
    assert not SalesOrder.objects.filter(pk=draft.pk).exists()
    closed = services.close_order(seller.user, services.confirm_order(seller.user, order(seller)))
    with pytest.raises(services.OrderClosedError):
        services.confirm_order(seller.user, closed)
    with pytest.raises(services.OrderNotOpenError):
        services.close_order(seller.user, closed)


@pytest.mark.django_db(transaction=True)
def test_two_invoices_cannot_both_slip_under_a_credit_limit() -> None:
    built = make_seller()
    tenant = built.shop.member.tenant
    with tenant_context(tenant):
        built.customer.credit_limit = D("600")
        built.customer.save()
        drafts = [
            services.save_invoice(
                built.user,
                {
                    "customer": built.customer,
                    "warehouse": built.shop.main,
                    "date": timezone.localdate(),
                },
                [services.InvoiceLineInput(built.shop.soap, built.shop.pcs, D(5), D(100))],
            )
            for _ in range(2)
        ]
    outcomes: list[str] = []
    gate = threading.Barrier(2)

    def post(draft: Invoice) -> None:
        with tenant_context(tenant):
            gate.wait()
            try:
                services.post_invoice(built.user, draft)
                outcomes.append("posted")
            except services.CreditLimitError:
                outcomes.append("refused")
            finally:
                connection.close()

    threads = [threading.Thread(target=post, args=(draft,)) for draft in drafts]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["posted", "refused"]


def test_a_statement_runs_from_sale_to_payment_to_return(seller: Seller) -> None:
    sold = invoice(seller)
    receipt(seller, "180", [(sold, "180")])
    services.post_credit_note(
        seller.user, services.credit_invoice(seller.user, sold, timezone.localdate())
    )
    statement = reports.statement(seller.customer, None, timezone.localdate())
    assert sorted(line.entry.kind for line in statement.lines) == ["invoice", "receipt", "return"]
    assert statement.closing == owed(seller)


def test_ageing_splits_by_days_overdue_and_shows_advances(seller: Seller) -> None:
    today = timezone.localdate()
    sold = invoice(seller, quantity="1", tax="0")
    Invoice.objects.filter(pk=sold.pk).update(due_date=today - timedelta(days=45))
    invoice(seller, quantity="2", tax="0")
    row = reports.ageing(today)[0]
    assert row["name"] == "Invented Kiryana"
    assert row["days_31_60"] == D("100.00")
    assert row["total"] == D("300.00")
    assert row["advance"] == D(0)
    receipt(seller, "50", [])
    row = reports.ageing(today)[0]
    assert row["advance"] == D("50.00")
    assert row["total"] == D("250.00")


def test_paid_up_customers_are_left_out_of_ageing(seller: Seller) -> None:
    assert reports.ageing(timezone.localdate()) == []


@pytest.mark.parametrize("language", ["en", "ur", "ar"])
def test_invoices_and_receipts_print_in_each_language(seller: Seller, language: str) -> None:
    sold = invoice(seller)
    paid = receipt(seller, "100", [(sold, "100")])
    html = documents.invoice_html(Invoice.objects.get(pk=sold.pk), language)
    assert str(sold.number) in html
    assert documents.LABELS[language]["invoice"] in html
    assert "1,180.00" in html
    assert "1,080.00" not in html.split(documents.LABELS[language]["paid"])[0]
    assert ('dir="ltr"' if language == "en" else 'dir="rtl"') in html
    assert documents.LABELS[language]["receipt"] in documents.receipt_html(paid, language)


def test_a_customer_name_cannot_inject_html_into_a_printout(seller: Seller) -> None:
    seller.customer.name = "<script>alert(1)</script>"
    seller.customer.save()
    html = documents.invoice_html(invoice(seller), "en")
    assert "<script>" not in html


def test_printing_says_so_when_the_pdf_libraries_are_missing(
    seller: Seller, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "weasyprint", None)
    with pytest.raises(documents.PdfUnavailableError):
        documents.to_pdf("<p>x</p>")


def test_only_posted_documents_print(seller: Seller) -> None:
    client = seller.shop.member.client()
    draft = services.save_invoice(
        seller.user,
        {"customer": seller.customer, "warehouse": seller.shop.main, "date": timezone.localdate()},
        [services.InvoiceLineInput(seller.shop.soap, seller.shop.pcs, D(1), D(1))],
    )
    assert client.get(f"/api/sales/invoices/{draft.pk}/pdf/").status_code == 400


def test_small_unit_prices_are_not_rounded_away_on_a_printout() -> None:
    assert documents._price(D("0.0040")) == "0.004"
    assert documents._price(D("1250.5000")) == "1,250.50"
    assert documents._price(D("10.1234")) == "10.1234"
