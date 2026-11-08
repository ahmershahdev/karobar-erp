"""Printed invoices and receipts.

WeasyPrint is imported where it is used: it needs the Pango libraries, which the production image
has and a Windows machine usually doesn't, and nothing else in the app should fail without them.
"""

from decimal import Decimal
from typing import Any

from django.template.loader import render_to_string

from apps.pos.models import PosSale
from apps.tenancy.context import get_current_tenant

from . import billing
from .models import BillSettings, CustomerReceipt, Invoice

LANGUAGES = ("en", "ur", "ar")

LABELS: dict[str, dict[str, str]] = {
    "en": {
        "invoice": "Invoice",
        "receipt": "Receipt",
        "number": "Number",
        "date": "Date",
        "due": "Due",
        "customer": "Customer",
        "item": "Item",
        "quantity": "Quantity",
        "price": "Price",
        "discount": "Discount",
        "tax": "Sales tax",
        "amount": "Amount",
        "net": "Before tax",
        "total": "Total",
        "paid": "Paid",
        "left": "Still to pay",
        "received": "Received with thanks",
        "reference": "Reference",
        "tax_number": "Tax number",
        "payment_terms": "Payment terms",
        "bank_details": "Bank details",
        "return_policy": "Returns",
        "signature": "Authorised signature",
    },
    "ur": {
        "invoice": "بل",
        "receipt": "رسید",
        "number": "نمبر",
        "date": "تاریخ",
        "due": "آخری تاریخ",
        "customer": "گاہک",
        "item": "چیز",
        "quantity": "تعداد",
        "price": "قیمت",
        "discount": "رعایت",
        "tax": "سیلز ٹیکس",
        "amount": "رقم",
        "net": "ٹیکس سے پہلے",
        "total": "کل",
        "paid": "ادا شدہ",
        "left": "باقی رقم",
        "received": "شکریہ کے ساتھ وصول ہوئی",
        "reference": "حوالہ",
        "tax_number": "ٹیکس نمبر",
        "payment_terms": "ادائیگی کی شرائط",
        "bank_details": "بینک کی تفصیل",
        "return_policy": "واپسی",
        "signature": "مجاز دستخط",
    },
    "ar": {
        "invoice": "فاتورة",
        "receipt": "إيصال",
        "number": "الرقم",
        "date": "التاريخ",
        "due": "الاستحقاق",
        "customer": "الزبون",
        "item": "الصنف",
        "quantity": "الكمية",
        "price": "السعر",
        "discount": "الخصم",
        "tax": "ضريبة المبيعات",
        "amount": "المبلغ",
        "net": "قبل الضريبة",
        "total": "الإجمالي",
        "paid": "المدفوع",
        "left": "المتبقي",
        "received": "استلمنا مع الشكر",
        "reference": "المرجع",
        "tax_number": "الرقم الضريبي",
        "payment_terms": "شروط الدفع",
        "bank_details": "بيانات البنك",
        "return_policy": "الإرجاع",
        "signature": "التوقيع المعتمد",
    },
}


class PdfUnavailableError(Exception):
    message = "Printing isn't available on this computer yet. It works on the live site."


def _money(value: Decimal) -> str:
    return f"{value:,.2f}"


def _price(value: Decimal) -> str:
    """Unit prices keep up to four places, or a price of 0.0040 would print as 0.00."""
    whole = f"{value:,.2f}"
    exact = f"{value:,.4f}".rstrip("0")
    return exact if len(exact) > len(whole) else whole


def _quantity(value: Decimal) -> str:
    return f"{value.normalize():f}"


def _context(language: str) -> dict[str, Any]:
    tenant = get_current_tenant()
    settings = billing.current()
    return {
        "business": tenant.name,
        "currency": tenant.base_currency,
        "labels": LABELS[language],
        "language": language,
        "dir": "ltr" if language == "en" else "rtl",
        "bill": settings,
        "logo": billing.data_uri(settings.logo),
        "signature": billing.data_uri(settings.signature),
        "template": settings.template,
        # Checked to be six hex digits when saved, so it is safe inside the style sheet.
        "accent": settings.accent,
        "paper": BillSettings.Paper.A4,
    }


def letterhead(language: str) -> dict[str, Any]:
    """The business's name, logo and look from its bill design, for other printed papers such
    as payslips."""
    return _context(language)


def invoice_html(invoice: Invoice, language: str) -> str:
    left = invoice.total - invoice.amount_paid - invoice.amount_credited
    context = _context(language)
    settings: BillSettings = context["bill"]
    if PosSale.objects.filter(invoice=invoice).exists():
        context["paper"] = settings.counter_paper
    # The till roll is too narrow for the extra columns, and a counter sale is paid already, so
    # it leaves out what only a credit bill needs. The totals still show tax and discount.
    roll = context["paper"] == BillSettings.Paper.RECEIPT
    return render_to_string(
        "sales/invoice.html",
        {
            **context,
            "roll": roll,
            "title": settings.title or LABELS[language]["invoice"],
            "show_tax": settings.show_tax and not roll,
            "show_sku": settings.show_sku and not roll,
            "show_discount": settings.show_discount and bool(invoice.discount) and not roll,
            "invoice": invoice,
            "lines": [
                {
                    "name": line.product.name,
                    "sku": line.product.sku,
                    "quantity": f"{_quantity(line.quantity)} {line.unit.code}",
                    "price": _price(line.unit_price),
                    # Its own discount and its share of the bill's, so the column adds up.
                    "discount": _money(line.discount + line.bill_share),
                    "tax": _money(line.tax_amount),
                    "amount": _money(line.amount),
                }
                for line in invoice.lines.select_related("product", "unit")
            ],
            "discount": _money(invoice.discount) if invoice.discount else None,
            "net": _money(invoice.net),
            "tax": _money(invoice.tax),
            "total": _money(invoice.total),
            "paid": _money(invoice.amount_paid + invoice.amount_credited),
            "left": _money(left),
        },
    )


def receipt_html(receipt: CustomerReceipt, language: str) -> str:
    return render_to_string(
        "sales/receipt.html",
        {**_context(language), "receipt": receipt, "amount": _money(receipt.amount)},
    )


def to_pdf(html: str) -> bytes:
    try:
        from weasyprint import HTML  # type: ignore[import-untyped]  # noqa: PLC0415
    except (ImportError, OSError) as exc:
        raise PdfUnavailableError from exc
    pdf: bytes = HTML(string=html).write_pdf()
    return pdf
