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


CONTENT_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}


def upload(
    member: Member,
    data: bytes,
    name: str = "logo.png",
    url: str = LOGO,
    content_type: str | None = None,
) -> Any:
    kind = content_type or CONTENT_TYPES.get(name[name.rfind(".") :], "image/png")
    file = SimpleUploadedFile(name, data, content_type=kind)
    return member.client().put(url, {"image": file}, format="multipart")


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
    [b"not a picture", b"", b"\x89PNG\r\n\x1a\n" + b"0" * (billing.MAX_IMAGE_BYTES + 1)],
)
def test_files_that_are_not_small_pictures_are_refused(seller: Seller, data: bytes) -> None:
    assert upload(seller.shop.member, data).status_code == 400
    assert not BillSettings.objects.exists()


def test_other_picture_formats_are_refused(seller: Seller) -> None:
    gif = picture("GIF")
    assert upload(seller.shop.member, gif, "logo.gif", content_type="image/gif").status_code == 400
    # Renamed to look like a PNG, it is still refused: the first bytes decide, not the name.
    assert upload(seller.shop.member, gif, "logo.png").status_code == 400


def test_a_picture_claiming_too_many_pixels_is_refused_before_decoding(seller: Seller) -> None:
    with patch.object(billing, "MAX_IMAGE_PIXELS", 100):
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
    billing.set_image(seller.user, "logo", picture())
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
    assert 'class="a4 t-classic"' in html


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
    assert 'class="receipt t-classic"' in documents.invoice_html(sale.invoice, "en")
    # Bills that didn't come from the counter stay on A4.
    assert 'class="a4 t-classic"' in documents.invoice_html(sold(seller), "en")


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


SIGNATURE = "/api/sales/bill-settings/signature/"


def test_a_file_named_like_a_picture_but_sent_as_something_else_is_refused(
    seller: Seller,
) -> None:
    member = seller.shop.member
    assert upload(member, picture(), "logo.exe").status_code == 400
    assert upload(member, picture(), "logo.png", content_type="text/html").status_code == 400


def test_a_web_page_dressed_as_a_png_is_refused(seller: Seller) -> None:
    page = b"<html><script>alert(1)</script></html>"
    assert upload(seller.shop.member, page, "logo.png").status_code == 400


def test_anything_hidden_after_the_picture_is_dropped(seller: Seller) -> None:
    hidden = picture() + b"<script>alert(1)</script>" + b"MZ" + b"\x00" * 64
    assert upload(seller.shop.member, hidden).status_code == 200
    stored = bytes(BillSettings.objects.get().logo or b"")
    assert b"<script>" not in stored
    assert b"MZ\x00" not in stored


def test_a_damaged_or_cut_off_picture_is_refused(seller: Seller) -> None:
    whole = picture()
    assert upload(seller.shop.member, whole[: len(whole) // 2]).status_code == 400
    broken = whole[:40] + b"\x00" * 40 + whole[80:]
    assert upload(seller.shop.member, broken).status_code == 400


@pytest.mark.parametrize("size", [(8, 8), (6000, 20), (20, 6000)])
def test_pictures_too_small_or_too_long_are_refused(seller: Seller, size: tuple[int, int]) -> None:
    assert upload(seller.shop.member, picture(size=size)).status_code == 400


def test_a_moving_picture_is_refused(seller: Seller) -> None:
    out = io.BytesIO()
    first = Image.new("RGB", (40, 40), (0, 0, 0))
    second = Image.new("RGB", (40, 40), (255, 255, 255))
    first.save(out, format="PNG", save_all=True, append_images=[second])
    assert upload(seller.shop.member, out.getvalue()).status_code == 400


def test_a_signature_picture_is_cleaned_and_printed(seller: Seller) -> None:
    reply = upload(seller.shop.member, picture(size=(1800, 300)), url=SIGNATURE)
    assert reply.status_code == 200, reply.content
    assert reply.json()["signature"].startswith("data:image/png;base64,")
    with Image.open(io.BytesIO(bytes(BillSettings.objects.get().signature or b""))) as clean:
        assert clean.size[0] <= 600
        assert clean.size[1] <= 200
    billing.save(seller.user, {"signature_text": "A. Invented"})
    html = documents.invoice_html(sold(seller), "en")
    assert "Authorised signature" in html
    # With a picture, the typed name goes underneath it as the signer's name.
    assert 'class="sign-name">A. Invented' in html
    assert seller.shop.member.client().delete(SIGNATURE).json()["signature"] is None


def test_a_typed_signature_prints_in_handwriting_style(seller: Seller) -> None:
    billing.save(seller.user, {"signature_text": "A. Invented"})
    html = documents.invoice_html(sold(seller), "ur")
    assert 'class="sign-text">A. Invented' in html
    assert "مجاز دستخط" in html


def test_no_signature_means_no_signature_line(seller: Seller) -> None:
    assert "Authorised signature" not in documents.invoice_html(sold(seller), "en")


@pytest.mark.parametrize(
    "template", ["classic", "modern", "minimal", "bold", "compact", "elegant"]
)
def test_each_template_can_be_chosen_and_printed(seller: Seller, template: str) -> None:
    reply = seller.shop.member.client().patch(URL, {"template": template}, format="json")
    assert reply.status_code == 200, reply.content
    assert f"t-{template}" in documents.invoice_html(sold(seller), "en")


def test_an_unknown_template_is_refused(seller: Seller) -> None:
    reply = seller.shop.member.client().patch(URL, {"template": "fancy"}, format="json")
    assert reply.status_code == 400
