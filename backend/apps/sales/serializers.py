from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.accounting.models import Account, TaxRate
from apps.inventory.models import Product, Unit, Warehouse
from apps.inventory.serializers import scoped
from apps.purchasing.serializers import AgeingRowSerializer, capped

from .models import (
    CreditNote,
    CreditNoteLine,
    Customer,
    CustomerReceipt,
    Invoice,
    InvoiceLine,
    ReceiptAllocation,
    SalesOrder,
    SalesOrderLine,
)

DOCUMENT_FIELDS = ("id", "number", "status", "date", "memo", "customer", "customer_name")
DOCUMENT_READ_ONLY = ("id", "number", "status", "posted_at")
OPTIONAL_MEMO = {"memo": {"required": False, "max_length": 255}}


class CustomerSerializer(serializers.ModelSerializer[Customer]):
    balance = serializers.DecimalField(
        max_digits=18, decimal_places=2, read_only=True, default=None, allow_null=True
    )

    class Meta:
        model = Customer
        fields = (
            "id",
            "code",
            "name",
            "phone",
            "email",
            "address",
            "tax_number",
            "payment_terms_days",
            "credit_limit",
            "is_active",
            "balance",
        )
        extra_kwargs = {
            "phone": {"required": False},
            "email": {"required": False},
            "address": {"required": False},
            "tax_number": {"required": False},
            "payment_terms_days": {"required": False, "max_value": 365},
            "credit_limit": {"required": False, "allow_null": True, "min_value": Decimal(0)},
        }


class _ProductLine(serializers.ModelSerializer[Any]):
    product = scoped(Product)
    unit = scoped(Unit)
    sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit_code = serializers.CharField(source="unit.code", read_only=True)


class _DocumentSerializer(serializers.ModelSerializer[Any]):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    created_by = serializers.EmailField(source="created_by.email", read_only=True)

    def validate_lines(self, value: list[Any]) -> list[Any]:
        return capped(value)


class SalesOrderLineSerializer(_ProductLine):
    tax_rate = scoped(TaxRate, allow_null=True, required=False)

    class Meta:
        model = SalesOrderLine
        fields = (
            "id",
            "product",
            "sku",
            "product_name",
            "unit",
            "unit_code",
            "quantity",
            "unit_price",
            "tax_rate",
            "tax_amount",
            "invoiced_quantity",
        )
        read_only_fields = ("id", "invoiced_quantity")
        extra_kwargs = {
            "quantity": {"min_value": Decimal("0.0001")},
            "unit_price": {"min_value": Decimal(0)},
            "tax_amount": {"required": False, "min_value": Decimal(0)},
        }


class SalesOrderSerializer(_DocumentSerializer):
    customer = scoped(Customer)
    warehouse = scoped(Warehouse)
    lines = SalesOrderLineSerializer(many=True)

    class Meta:
        model = SalesOrder
        fields = (
            *DOCUMENT_FIELDS,
            "quote_number",
            "valid_until",
            "warehouse",
            "total",
            "lines",
            "created_by",
            "posted_at",
        )
        read_only_fields = (*DOCUMENT_READ_ONLY, "quote_number", "total")
        extra_kwargs = {
            **OPTIONAL_MEMO,
            "valid_until": {"required": False, "allow_null": True},
        }


class InvoiceLineSerializer(_ProductLine):
    order_line = scoped(SalesOrderLine, allow_null=True, required=False)
    tax_rate = scoped(TaxRate, allow_null=True, required=False)

    class Meta:
        model = InvoiceLine
        fields = (
            "id",
            "order_line",
            "product",
            "sku",
            "product_name",
            "unit",
            "unit_code",
            "quantity",
            "unit_price",
            "amount",
            "tax_rate",
            "tax_amount",
            "batch_number",
            "returned_quantity",
        )
        read_only_fields = ("id", "amount", "returned_quantity")
        extra_kwargs = {
            "quantity": {"min_value": Decimal("0.0001")},
            "unit_price": {"min_value": Decimal(0)},
            "tax_amount": {"required": False, "min_value": Decimal(0)},
            "batch_number": {"required": False, "max_length": 40},
        }


class InvoiceSerializer(_DocumentSerializer):
    customer = scoped(Customer)
    order = scoped(SalesOrder, allow_null=True, required=False)
    warehouse = scoped(Warehouse)
    lines = InvoiceLineSerializer(many=True)
    journal_number = serializers.CharField(
        source="journal_entry.number", read_only=True, default=None, allow_null=True
    )

    class Meta:
        model = Invoice
        fields = (
            *DOCUMENT_FIELDS,
            "order",
            "warehouse",
            "due_date",
            "net",
            "tax",
            "total",
            "amount_paid",
            "amount_credited",
            "lines",
            "journal_number",
            "created_by",
            "posted_at",
        )
        read_only_fields = (
            *DOCUMENT_READ_ONLY,
            "net",
            "tax",
            "total",
            "amount_paid",
            "amount_credited",
        )
        extra_kwargs = {
            **OPTIONAL_MEMO,
            "due_date": {"required": False, "allow_null": True},
        }


class ReceiptAllocationSerializer(serializers.ModelSerializer[ReceiptAllocation]):
    invoice = scoped(Invoice)
    invoice_number = serializers.CharField(
        source="invoice.number", read_only=True, allow_null=True
    )

    class Meta:
        model = ReceiptAllocation
        fields = ("id", "invoice", "invoice_number", "amount")
        read_only_fields = ("id",)
        extra_kwargs = {"amount": {"min_value": Decimal("0.01")}}


class CustomerReceiptSerializer(_DocumentSerializer):
    customer = scoped(Customer)
    received_into = scoped(Account)
    allocations = ReceiptAllocationSerializer(many=True, required=False)
    journal_number = serializers.CharField(
        source="journal_entry.number", read_only=True, default=None, allow_null=True
    )

    class Meta:
        model = CustomerReceipt
        fields = (
            *DOCUMENT_FIELDS,
            "amount",
            "received_into",
            "reference",
            "allocations",
            "journal_number",
            "created_by",
            "posted_at",
        )
        read_only_fields = DOCUMENT_READ_ONLY
        extra_kwargs = {
            **OPTIONAL_MEMO,
            "reference": {"required": False, "max_length": 60},
            "amount": {"min_value": Decimal("0.01")},
        }

    def validate_allocations(self, value: list[Any]) -> list[Any]:
        return capped(value)


class CreditLineSerializer(serializers.ModelSerializer[CreditNoteLine]):
    invoice_line = scoped(InvoiceLine)
    product_name = serializers.CharField(source="invoice_line.product.name", read_only=True)

    class Meta:
        model = CreditNoteLine
        fields = ("id", "invoice_line", "product_name", "quantity", "amount", "tax_amount")
        read_only_fields = ("id", "amount", "tax_amount")
        extra_kwargs = {"quantity": {"min_value": Decimal("0.0001")}}


class CreditNoteSerializer(_DocumentSerializer):
    invoice = scoped(Invoice)
    invoice_number = serializers.CharField(
        source="invoice.number", read_only=True, allow_null=True
    )
    lines = CreditLineSerializer(many=True)
    journal_number = serializers.CharField(
        source="journal_entry.number", read_only=True, default=None, allow_null=True
    )

    class Meta:
        model = CreditNote
        fields = (
            *DOCUMENT_FIELDS,
            "invoice",
            "invoice_number",
            "net",
            "tax",
            "total",
            "applied",
            "lines",
            "journal_number",
            "created_by",
            "posted_at",
        )
        read_only_fields = (*DOCUMENT_READ_ONLY, "customer", "net", "tax", "total", "applied")
        extra_kwargs = OPTIONAL_MEMO


class ReceivableRowSerializer(AgeingRowSerializer):
    whatsapp = serializers.CharField()


class BillShareSerializer(serializers.Serializer[Any]):
    link = serializers.CharField()
    whatsapp = serializers.CharField()
