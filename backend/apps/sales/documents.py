"""Printed invoices and receipts.

WeasyPrint is imported where it is used: it needs the Pango libraries, which the production image
has and a Windows machine usually doesn't, and nothing else in the app should fail without them.
"""

from decimal import Decimal
from typing import Any

from django.template.loader import render_to_string

from apps.tenancy.context import get_current_tenant

from .models import CustomerReceipt, Invoice

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
    return {
        "business": tenant.name,
        "currency": tenant.base_currency,
        "labels": LABELS[language],
        "language": language,
        "dir": "ltr" if language == "en" else "rtl",
    }


def invoice_html(invoice: Invoice, language: str) -> str:
    left = invoice.total - invoice.amount_paid - invoice.amount_credited
    return render_to_string(
        "sales/invoice.html",
        {
            **_context(language),
            "invoice": invoice,
            "lines": [
                {
                    "name": line.product.name,
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
