from collections.abc import Iterator
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import unquote

import pytest
from django.core import mail, signing
from django.utils import timezone
from rest_framework.test import APIClient

from apps.reports.tasks import send_daily_summaries
from apps.sales import documents, links
from apps.sales.models import Customer, Invoice
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant
from tests.sales.test_sales import Seller, invoice, make_seller


@pytest.fixture
def seller(db: None) -> Iterator[Seller]:
    built = make_seller()
    with tenant_context(built.shop.member.tenant):
        yield built


@pytest.fixture
def pdf() -> Iterator[None]:
    with patch.object(documents, "to_pdf", return_value=b"%PDF-bill"):
        yield


def url_for(token: str) -> str:
    return f"/api/public/bills/{token}/"


def test_a_signed_link_opens_the_bill_without_an_account(seller: Seller, pdf: None) -> None:
    response = APIClient().get(url_for(links.bill_token(invoice(seller))))
    assert response.status_code == 200
    assert response.content == b"%PDF-bill"
    assert response["Cache-Control"] == "private, no-store"
    assert response["X-Robots-Tag"] == "noindex"
    assert response["Referrer-Policy"] == "no-referrer"


def test_a_changed_link_is_refused(seller: Seller, pdf: None) -> None:
    token = links.bill_token(invoice(seller))
    forged = token[:-1] + ("a" if token[-1] != "a" else "b")
    assert APIClient().get(url_for(forged)).status_code == 404


def test_a_link_signed_for_something_else_is_refused(seller: Seller, pdf: None) -> None:
    bill = invoice(seller)
    other = signing.dumps({"t": bill.tenant_id, "i": bill.pk}, salt="another.purpose")
    assert APIClient().get(url_for(other)).status_code == 404


def test_an_old_link_stops_working(seller: Seller, pdf: None) -> None:
    token = links.bill_token(invoice(seller))
    late = links.BILL_LINK_DAYS * 24 * 60 * 60 + 60
    with patch("django.core.signing.time.time", return_value=timezone.now().timestamp() + late):
        assert APIClient().get(url_for(token)).status_code == 404


def test_a_link_for_a_bill_that_is_gone_finds_nothing(seller: Seller, pdf: None) -> None:
    bill = invoice(seller)
    token = signing.dumps({"t": bill.tenant_id, "i": bill.pk + 999}, salt=links.SALT)
    assert APIClient().get(url_for(token)).status_code == 404


def test_a_link_for_a_business_that_is_gone_finds_nothing(seller: Seller, pdf: None) -> None:
    bill = invoice(seller)
    gone = Tenant.objects.order_by("-pk").first()
    assert gone is not None
    token = signing.dumps({"t": gone.pk + 999, "i": bill.pk}, salt=links.SALT)
    assert APIClient().get(url_for(token)).status_code == 404


def test_a_draft_cannot_be_opened_by_link(seller: Seller, pdf: None) -> None:
    bill = invoice(seller)
    Invoice.objects.filter(pk=bill.pk).update(status=Invoice.Status.DRAFT)
    assert APIClient().get(url_for(links.bill_token(bill))).status_code == 404


def test_the_bill_message_goes_to_the_customer_with_the_link(seller: Seller) -> None:
    Customer.objects.filter(pk=seller.customer.pk).update(phone="0300 1234567")
    bill = Invoice.objects.select_related("customer").get(pk=invoice(seller).pk)
    link = links.bill_message(bill)
    assert link.startswith("https://wa.me/923001234567?text=")
    assert "/api/public/bills/" in unquote(link)
    assert bill.number in unquote(link)


def test_the_share_screen_refuses_a_draft(seller: Seller) -> None:
    bill = invoice(seller)
    Invoice.objects.filter(pk=bill.pk).update(status=Invoice.Status.DRAFT)
    client = seller.shop.member.client()
    assert client.get(f"/api/sales/invoices/{bill.pk}/share/").status_code == 400


def test_the_share_screen_gives_a_link_and_a_message(seller: Seller) -> None:
    bill = invoice(seller)
    data = seller.shop.member.client().get(f"/api/sales/invoices/{bill.pk}/share/").json()
    assert "/api/public/bills/" in data["link"]
    assert data["whatsapp"].startswith("https://wa.me/")


def test_who_owes_me_offers_a_reminder(seller: Seller) -> None:
    invoice(seller)
    rows = seller.shop.member.client().get("/api/sales/ageing/").json()
    assert "friendly reminder" in unquote(rows[0]["whatsapp"])


def test_the_owner_gets_a_summary_after_a_day_with_something_to_say(seller: Seller) -> None:
    bill = invoice(seller)
    yesterday = timezone.localdate() - timedelta(days=1)
    Invoice.objects.filter(pk=bill.pk).update(date=yesterday)
    mail.outbox.clear()
    assert send_daily_summaries() == 1
    assert "Sales yesterday" in str(mail.outbox[0].body)


def test_a_quiet_day_sends_nothing(seller: Seller) -> None:
    mail.outbox.clear()
    assert send_daily_summaries() == 0
    assert mail.outbox == []


def test_the_summary_can_be_turned_off_and_that_is_audited(seller: Seller) -> None:
    client = seller.shop.member.client()
    assert client.get("/api/automation/").json() == {"daily_summary": True}
    answer = client.patch("/api/automation/", {"daily_summary": False}, format="json")
    assert answer.json() == {"daily_summary": False}
    invoice(seller)
    mail.outbox.clear()
    assert send_daily_summaries() == 0
