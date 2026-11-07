import importlib
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from django.apps import apps as django_apps
from django.utils import timezone

from apps.accounting.models import Account
from apps.pos import services as pos
from apps.sales import documents, services
from apps.sales.models import Invoice, SalesOrder
from apps.tenancy.context import tenant_context
from tests.conftest import Member
from tests.factories import create_membership, create_role
from tests.sales.test_sales import Seller, gst, make_seller, role_balance

pytestmark = pytest.mark.django_db
D = Decimal


@pytest.fixture
def seller(db: None) -> Iterator[Seller]:
    built = make_seller()
    with tenant_context(built.shop.member.tenant):
        yield built


def line(s: Seller, quantity: str = "10", price: str = "100", **extra: Any) -> Any:
    return services.InvoiceLineInput(s.shop.soap, s.shop.pcs, D(quantity), D(price), **extra)


def header(s: Seller, **extra: Any) -> dict[str, Any]:
    return {
        "customer": s.customer,
        "warehouse": s.shop.main,
        "date": timezone.localdate(),
        **extra,
    }


def clerk(s: Seller, limit: str) -> Member:
    role = create_role(
        permissions={"sales": ["view", "create", "update", "post"]},
        max_discount_percent=D(limit),
    )
    membership = create_membership(role=role)
    return Member(user=membership.user, tenant=s.shop.member.tenant, membership=membership)


def test_a_line_percentage_comes_off_before_tax(seller: Seller) -> None:
    invoice = services.save_invoice(
        seller.user, header(seller), [line(seller, discount_percent=D("10"), tax_rate=gst())]
    )
    row = invoice.lines.get()
    assert (row.discount, row.bill_share, row.amount) == (D("100.00"), D("0.00"), D("900.00"))
    assert row.tax_amount == D("162.00")
    assert (invoice.discount, invoice.net, invoice.tax, invoice.total) == (
        D("100.00"),
        D("900.00"),
        D("162.00"),
        D("1062.00"),
    )


def test_a_line_amount_discount(seller: Seller) -> None:
    invoice = services.save_invoice(
        seller.user, header(seller), [line(seller, quantity="3", discount=D("25.50"))]
    )
    assert invoice.lines.get().amount == D("274.50")


def test_a_bill_percentage_is_spread_over_the_lines_and_adds_up(seller: Seller) -> None:
    lines = [line(seller, "1", "10"), line(seller, "1", "10"), line(seller, "1", "10.01")]
    invoice = services.save_invoice(seller.user, header(seller, discount_percent=D("10")), lines)
    shares = [row.bill_share for row in invoice.lines.order_by("id")]
    assert sum(shares) == invoice.bill_discount == D("3.00")
    assert invoice.discount == D("3.00")
    assert invoice.net == D("27.01")
    assert invoice.discount_percent == D("10")


def test_a_bill_amount_comes_after_line_discounts(seller: Seller) -> None:
    lines = [line(seller, "1", "100", discount_percent=D("50")), line(seller, "1", "50")]
    invoice = services.save_invoice(seller.user, header(seller, bill_discount=D("10")), lines)
    # 50 and 50 are left after the line discount, so the 10 off the bill splits evenly.
    assert [row.bill_share for row in invoice.lines.order_by("id")] == [D("5.00"), D("5.00")]
    assert invoice.discount == D("60.00")
    assert invoice.net == D("90.00")


@pytest.mark.parametrize(
    ("extra", "bill"),
    [
        ({"discount": D("1000.01")}, {}),
        ({}, {"bill_discount": D("1000.01")}),
        ({"discount_percent": D("101")}, {}),
    ],
)
def test_a_discount_bigger_than_the_price_is_refused(
    seller: Seller, extra: dict[str, Any], bill: dict[str, Any]
) -> None:
    with pytest.raises(services.DiscountTooLargeError):
        services.save_invoice(seller.user, header(seller, **bill), [line(seller, **extra)])


def test_posting_shows_the_discount_on_its_own_account(seller: Seller) -> None:
    invoice = services.save_invoice(
        seller.user, header(seller, discount_percent=D("10")), [line(seller)]
    )
    services.post_invoice(seller.user, invoice)
    assert role_balance("sales") == D("-1000.00")
    assert role_balance("sales_discounts") == D("100.00")
    assert role_balance("receivables") == D("900.00")


def test_a_return_refunds_what_was_paid_after_the_discount(seller: Seller) -> None:
    invoice = services.save_invoice(
        seller.user, header(seller), [line(seller, discount_percent=D("20"))]
    )
    posted = services.post_invoice(seller.user, invoice)
    note = services.credit_invoice(seller.user, posted, timezone.localdate())
    assert note.net == D("800.00")


def test_an_order_discount_carries_onto_its_invoices(seller: Seller) -> None:
    order = services.save_order(
        seller.user,
        header(seller, bill_discount=D("50")),
        [
            services.OrderLineInput(
                seller.shop.soap, seller.shop.pcs, D("10"), D("100"), discount_percent=D("10")
            )
        ],
    )
    assert order.discount == D("150.00")
    assert order.total == D("850.00")
    services.confirm_order(seller.user, order)
    invoice = services.invoice_order(seller.user, order, timezone.localdate())
    assert invoice.net == D("850.00")
    assert invoice.discount == D("150.00")


def test_a_role_cannot_give_more_than_its_limit(seller: Seller) -> None:
    person = clerk(seller, "5")
    with pytest.raises(services.DiscountNotAllowedError):
        services.save_invoice(person.user, header(seller), [line(seller, discount_percent=D("6"))])
    # The bill discount counts too.
    with pytest.raises(services.DiscountNotAllowedError):
        services.save_invoice(
            person.user,
            header(seller, discount_percent=D("3")),
            [line(seller, discount_percent=D("3"))],
        )
    services.save_invoice(person.user, header(seller), [line(seller, discount_percent=D("5"))])


def test_a_role_with_no_limit_set_gives_no_discount(seller: Seller) -> None:
    person = clerk(seller, "0")
    with pytest.raises(services.DiscountNotAllowedError):
        services.save_invoice(person.user, header(seller), [line(seller, discount=D("0.01"))])
    services.save_invoice(person.user, header(seller), [line(seller)])


def test_the_owner_has_no_limit(seller: Seller) -> None:
    services.save_invoice(seller.user, header(seller), [line(seller, discount_percent=D("100"))])


def test_invoicing_an_approved_order_is_not_checked_again(seller: Seller) -> None:
    order = services.save_order(
        seller.user,
        header(seller),
        [
            services.OrderLineInput(
                seller.shop.soap, seller.shop.pcs, D("10"), D("100"), discount_percent=D("30")
            )
        ],
    )
    services.confirm_order(seller.user, order)
    invoice = services.invoice_order(clerk(seller, "0").user, order, timezone.localdate())
    assert invoice.discount == D("300.00")


def test_the_api_takes_and_returns_discounts(seller: Seller) -> None:
    body = {
        "customer": seller.customer.pk,
        "warehouse": seller.shop.main.pk,
        "date": str(timezone.localdate()),
        "discount_percent": "10",
        "lines": [
            {
                "product": seller.shop.soap.pk,
                "unit": seller.shop.pcs.pk,
                "quantity": "2",
                "unit_price": "100",
                "discount": "20",
            }
        ],
    }
    client = seller.shop.member.client()
    reply = client.post("/api/sales/invoices/", body, format="json")
    assert reply.status_code == 201, reply.content
    data = reply.json()
    assert (data["discount"], data["bill_discount"], data["net"]) == ("38.00", "18.00", "162.00")
    assert data["lines"][0]["discount"] == "20.00"
    assert data["lines"][0]["bill_share"] == "18.00"
    order = client.post("/api/sales/orders/", body, format="json")
    assert order.status_code == 201, order.content
    assert order.json()["total"] == "162.00"
    assert SalesOrder.objects.get().discount == D("38.00")


def test_the_api_says_when_a_discount_is_too_high(seller: Seller) -> None:
    person = clerk(seller, "5")
    body = {
        "customer": seller.customer.pk,
        "warehouse": seller.shop.main.pk,
        "date": str(timezone.localdate()),
        "lines": [
            {
                "product": seller.shop.soap.pk,
                "unit": seller.shop.pcs.pk,
                "quantity": "1",
                "unit_price": "100",
                "discount_percent": "50",
            }
        ],
    }
    reply = person.client().post("/api/sales/invoices/", body, format="json")
    assert reply.status_code == 400
    assert "role allows" in str(reply.json())
    assert not Invoice.objects.exists()


def test_the_counter_takes_line_and_sale_discounts(seller: Seller) -> None:
    seller.shop.soap.sale_price = D("100")
    seller.shop.soap.save()
    session = pos.open_till(seller.user, seller.shop.main, D("0"))
    cart = [pos.CartLine(seller.shop.soap, seller.shop.pcs, D("2"), D("10"))]
    sale = pos.sell(seller.user, session, cart, "card", discount_percent=D("50"))
    assert sale.amount == D("90.00")
    assert sale.invoice.discount == D("110.00")


def test_the_counter_keeps_to_the_role_limit(seller: Seller) -> None:
    seller.shop.soap.sale_price = D("100")
    seller.shop.soap.save()
    cashier = clerk(seller, "10")
    session = pos.open_till(seller.user, seller.shop.main, D("0"))
    cart = [pos.CartLine(seller.shop.soap, seller.shop.pcs, D("1"), D("20"))]
    with pytest.raises(services.DiscountNotAllowedError):
        pos.sell(cashier.user, session, cart, "card")


def test_roles_carry_a_discount_limit(seller: Seller) -> None:
    client = seller.shop.member.client()
    made = client.post(
        "/api/roles/",
        {"name": "Cashier", "permissions": {"sales": ["view"]}, "max_discount_percent": "7.5"},
        format="json",
    )
    assert made.status_code == 201, made.content
    assert made.json()["max_discount_percent"] == "7.50"
    too_much = client.post(
        "/api/roles/",
        {"name": "Boss", "permissions": {}, "max_discount_percent": "101"},
        format="json",
    )
    assert too_much.status_code == 400


def test_older_businesses_get_a_sales_discounts_account(seller: Seller) -> None:
    Account.objects.filter(role="sales_discounts").delete()
    migration = importlib.import_module("apps.accounting.migrations.0007_sales_discounts")
    migration.add_role(django_apps, None)
    migration.add_role(django_apps, None)
    added = Account.objects.get(role="sales_discounts")
    assert (added.code, added.type, added.parent.code if added.parent else None) == (
        "4250",
        "income",
        "4000",
    )


def test_a_printed_bill_shows_the_discount_only_when_there_is_one(seller: Seller) -> None:
    plain = services.save_invoice(seller.user, header(seller), [line(seller)])
    assert "Discount" not in documents.invoice_html(plain, "en")
    cut = services.save_invoice(
        seller.user, header(seller, discount_percent=D("10")), [line(seller)]
    )
    html = documents.invoice_html(cut, "en")
    assert "Discount" in html
    assert "100.00" in html
    assert "رعایت" in documents.invoice_html(cut, "ur")
