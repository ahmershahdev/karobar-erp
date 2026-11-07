import io
from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image, PngImagePlugin

from apps.accounting import services as accounting
from apps.accounting.models import NumberSeries
from apps.pos import services as pos
from apps.sales import billing, documents, services
from apps.sales.models import BillSettings
from apps.tenancy.context import tenant_context
from apps.tenancy.models import AuditEvent
from tests.conftest import Member
from tests.factories import create_membership, create_role
from tests.sales.test_sales import Seller, make_seller

pytestmark = pytest.mark.django_db
D = Decimal
URL = "/api/sales/bill-settings/"
LOGO = "/api/sales/bill-settings/logo/"


@pytest.fixture
def seller(db: None) -> Iterator[Seller]:
    built = make_seller()
    with tenant_context(built.shop.member.tenant):
        yield built


def picture(kind: str = "PNG", size: tuple[int, int] = (1200, 300), **save: Any) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(out, format=kind, **save)
    return out.getvalue()


def upload(member: Member, data: bytes, name: str = "logo.png") -> Any:
    return member.client().put(LOGO, {"logo": SimpleUploadedFile(name, data)}, format="multipart")


def sold(s: Seller) -> Any:
    invoice = services.save_invoice(
        s.user,
        {"customer": s.customer, "warehouse": s.shop.main, "date": timezone.localdate()},
        [services.InvoiceLineInput(s.shop.soap, s.shop.pcs, D(2), D(100), D(18))],
    )
    return services.post_invoice(s.user, invoice)


def test_a_new_business_sees_the_defaults(seller: Seller) -> None:
    body = seller.shop.member.client().get(URL).json()
    assert body["logo"] is None
    assert body["invoice_prefix"] == "INV-"
    assert body["accent"] == "#0b1a3c"
    assert (body["show_tax"], body["show_discount"], body["show_sku"]) == (True, True, False)
    assert body["counter_paper"] == "a4"
    assert not BillSettings.objects.exists()


def test_settings_are_saved_and_audited(seller: Seller) -> None:
    changes = {
        "address": "1 Invented Road, Lahore",
        "phone": "042-0000000",
        "tax_label": "NTN",
        "tax_number": "0000000-0",
        "title": "Tax Invoice",
        "thanks": "Thank you for shopping with us",
        "bank_details": "Invented Bank\nIBAN PK00 0000 0000 0000",
        "accent": "#1d4ed8",
        "show_sku": True,
        "counter_paper": "receipt",
    }
    reply = seller.shop.member.client().patch(URL, changes, format="json")
    assert reply.status_code == 200, reply.content
    assert reply.json()["title"] == "Tax Invoice"
    saved = BillSettings.objects.get()
    assert (saved.accent, saved.counter_paper) == ("#1d4ed8", "receipt")
    event = AuditEvent.objects.get(model="sales.BillSettings")
    assert event.changes["title"] == ["", "Tax Invoice"]


def test_a_new_prefix_numbers_bills_from_now_on(seller: Seller) -> None:
    first = sold(seller)
    reply = seller.shop.member.client().patch(URL, {"invoice_prefix": "KB/"}, format="json")
    assert reply.status_code == 200, reply.content
    second = sold(seller)
    assert first.number.startswith("INV-")
    assert second.number.startswith("KB/")
    # The counter carries on, so no number is given twice.
    assert int(second.number[3:]) == int(first.number[4:]) + 1
    assert NumberSeries.objects.get(key="INV").prefix == "KB/"


@pytest.mark.parametrize("prefix", ["", "inv-", "-INV", "TOO-LONG-PREFIX", "IN V"])
def test_a_strange_prefix_is_refused(seller: Seller, prefix: str) -> None:
    reply = seller.shop.member.client().patch(URL, {"invoice_prefix": prefix}, format="json")
    assert reply.status_code == 400


@pytest.mark.parametrize("accent", ["#ffcc00", "#ffffff", "red", "#12345g"])
def test_an_accent_that_cannot_be_read_on_white_is_refused(seller: Seller, accent: str) -> None:
    reply = seller.shop.member.client().patch(URL, {"accent": accent}, format="json")
    assert reply.status_code == 400
    assert not BillSettings.objects.exists()


def test_only_people_who_run_the_business_change_the_bill(seller: Seller) -> None:
    membership = create_membership(role=create_role(permissions={"sales": ["view", "create"]}))
    cashier = Member(user=membership.user, tenant=seller.shop.member.tenant, membership=membership)
    assert cashier.client().get(URL).status_code == 403
    assert cashier.client().patch(URL, {"title": "Mine"}, format="json").status_code == 403
    assert upload(cashier, picture()).status_code == 403


def test_a_logo_is_rewritten_as_a_small_clean_png(seller: Seller) -> None:
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", "hidden words")
    reply = upload(seller.shop.member, picture(pnginfo=info))
    assert reply.status_code == 200, reply.content
    assert reply.json()["logo"].startswith("data:image/png;base64,")
    stored = bytes(BillSettings.objects.get().logo or b"")
    with Image.open(io.BytesIO(stored)) as clean:
        assert clean.format == "PNG"
        assert max(clean.size) <= 600
        assert "Comment" not in clean.info
    served = seller.shop.member.client().get(LOGO)
    assert served.status_code == 200
    assert served["Content-Type"] == "image/png"
    assert served.content == stored


def test_jpeg_and_webp_logos_are_accepted(seller: Seller) -> None:
    assert upload(seller.shop.member, picture("JPEG"), "logo.jpg").status_code == 200
    assert upload(seller.shop.member, picture("WEBP"), "logo.webp").status_code == 200


@pytest.mark.parametrize(
    "data",
    [b"not a picture", b"", b"\x89PNG\r\n\x1a\n" + b"0" * (billing.MAX_LOGO_BYTES + 1)],
)
def test_files_that_are_not_small_pictures_are_refused(seller: Seller, data: bytes) -> None:
    assert upload(seller.shop.member, data).status_code == 400
    assert not BillSettings.objects.exists()


def test_other_picture_formats_are_refused(seller: Seller) -> None:
    assert upload(seller.shop.member, picture("GIF"), "logo.gif").status_code == 400


def test_a_picture_claiming_too_many_pixels_is_refused_before_decoding(seller: Seller) -> None:
    with patch.object(billing, "MAX_LOGO_PIXELS", 100):
        assert upload(seller.shop.member, picture(size=(20, 20))).status_code == 400


def test_a_logo_can_be_taken_off(seller: Seller) -> None:
    upload(seller.shop.member, picture())
    reply = seller.shop.member.client().delete(LOGO)
    assert reply.json()["logo"] is None
    assert seller.shop.member.client().get(LOGO).status_code == 404


def test_the_printed_bill_carries_the_business_details_and_footer(seller: Seller) -> None:
    billing.save(
        seller.user,
        {
            "address": "1 Invented Road",
            "phone": "042-0000000",
            "email": "shop@example.invalid",
            "tax_number": "0000000-0",
            "title": "Cash Memo",
            "thanks": "Come again",
            "payment_terms": "Pay within 15 days",
            "return_policy": "Returns within 7 days with this bill",
            "accent": "#1d4ed8",
            "show_tax": False,
            "show_sku": True,
        },
    )
    billing.set_logo(seller.user, picture())
    html = documents.invoice_html(sold(seller), "en")
    for text in (
        "1 Invented Road",
        "042-0000000",
        "shop@example.invalid",
        "Tax number",
        "Cash Memo",
        "Come again",
        "Pay within 15 days",
        "Returns within 7 days",
        "#1d4ed8",
        "SOAP-1",
        "data:image/png;base64,",
    ):
        assert text in html
    # The tax column goes, but the tax total stays on the bill.
    assert html.count(">Sales tax<") == 1
    assert 'class="a4"' in html


def test_a_tax_label_replaces_the_default_words(seller: Seller) -> None:
    billing.save(seller.user, {"tax_label": "STRN", "tax_number": "1234"})
    html = documents.invoice_html(sold(seller), "ur")
    assert "STRN" in html
    assert "ٹیکس نمبر" not in html


def test_counter_sales_print_on_a_till_roll_when_chosen(seller: Seller) -> None:
    billing.save(seller.user, {"counter_paper": "receipt"})
    seller.shop.soap.sale_price = D("100")
    seller.shop.soap.save()
    session = pos.open_till(seller.user, seller.shop.main, D("0"))
    sale = pos.sell(
        seller.user, session, [pos.CartLine(seller.shop.soap, seller.shop.pcs, D(1))], "card"
    )
    assert 'class="receipt"' in documents.invoice_html(sale.invoice, "en")
    # Bills that didn't come from the counter stay on A4.
    assert 'class="a4"' in documents.invoice_html(sold(seller), "en")


def test_receipts_carry_the_business_details_too(seller: Seller) -> None:
    billing.save(seller.user, {"address": "1 Invented Road", "thanks": "Thank you"})
    receipt = services.save_receipt(
        seller.user,
        {
            "customer": seller.customer,
            "date": timezone.localdate(),
            "amount": D(5),
            "received_into": accounting.account_for_role("cash"),
        },
        [],
    )
    html = documents.receipt_html(receipt, "en")
    assert "1 Invented Road" in html
    assert "Thank you" in html
