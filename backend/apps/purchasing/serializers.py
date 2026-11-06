from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.accounting.models import Account
from apps.inventory.models import Product, Unit, Warehouse
from apps.inventory.serializers import scoped

from .models import (
    Bill,
    BillLine,
    GoodsReceipt,
    GoodsReceiptLine,
    PaymentAllocation,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierPayment,
)

MAX_LINES = 500


def capped(value: list[Any]) -> list[Any]:
    if len(value) > MAX_LINES:
        raise serializers.ValidationError(f"A document can have at most {MAX_LINES} lines.")
    return value


class SupplierSerializer(serializers.ModelSerializer[Supplier]):
    balance = serializers.DecimalField(
        max_digits=18, decimal_places=2, read_only=True, default=None, allow_null=True
    )

    class Meta:
        model = Supplier
        fields = (
            "id",
            "code",
            "name",
            "phone",
            "email",
            "address",
            "tax_number",
            "payment_terms_days",
            "is_active",
            "balance",
        )
        extra_kwargs = {
            "phone": {"required": False},
            "email": {"required": False},
            "address": {"required": False},
            "tax_number": {"required": False},
            "payment_terms_days": {"required": False, "max_value": 365},
        }


class _ProductLine(serializers.ModelSerializer[Any]):
    product = scoped(Product)
    unit = scoped(Unit)
    sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit_code = serializers.CharField(source="unit.code", read_only=True)


class OrderLineSerializer(_ProductLine):
    class Meta:
        model = PurchaseOrderLine
        fields = (
            "id",
            "product",
            "sku",
            "product_name",
            "unit",
            "unit_code",
            "quantity",
            "unit_price",
            "received_quantity",
        )
        read_only_fields = ("id", "received_quantity")
        extra_kwargs = {
            "quantity": {"min_value": Decimal("0.0001")},
            "unit_price": {"min_value": 0},
        }


class _DocumentSerializer(serializers.ModelSerializer[Any]):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    created_by = serializers.EmailField(source="created_by.email", read_only=True)

    def validate_lines(self, value: list[Any]) -> list[Any]:
        return capped(value)


DOCUMENT_FIELDS = ("id", "number", "status", "date", "memo", "supplier", "supplier_name")
DOCUMENT_READ_ONLY = ("id", "number", "status", "posted_at")


class PurchaseOrderSerializer(_DocumentSerializer):
    supplier = scoped(Supplier)
    warehouse = scoped(Warehouse)
    lines = OrderLineSerializer(many=True)

    class Meta:
        model = PurchaseOrder
        fields = (
            *DOCUMENT_FIELDS,
            "expected_date",
            "warehouse",
            "total",
            "lines",
            "created_by",
            "posted_at",
        )
        read_only_fields = (*DOCUMENT_READ_ONLY, "total")
        extra_kwargs = {
            "memo": {"required": False, "max_length": 255},
            "expected_date": {"required": False, "allow_null": True},
        }


class ReceiptLineSerializer(_ProductLine):
    order_line = scoped(PurchaseOrderLine, allow_null=True, required=False)

    class Meta:
        model = GoodsReceiptLine
        fields = (
            "id",
            "order_line",
            "product",
            "sku",
            "product_name",
            "unit",
            "unit_code",
            "quantity",
            "unit_cost",
            "batch_number",
            "expiry_date",
            "value",
            "billed_quantity",
        )
        read_only_fields = ("id", "value", "billed_quantity")
        extra_kwargs = {
            "quantity": {"min_value": Decimal("0.0001")},
            "unit_cost": {"min_value": 0},
            "batch_number": {"required": False, "max_length": 40},
            "expiry_date": {"required": False, "allow_null": True},
        }


class GoodsReceiptSerializer(_DocumentSerializer):
    supplier = scoped(Supplier)
    warehouse = scoped(Warehouse)
    purchase_order = scoped(PurchaseOrder, allow_null=True, required=False)
    order_number = serializers.CharField(
        source="purchase_order.number", read_only=True, default=None, allow_null=True
    )
    lines = ReceiptLineSerializer(many=True)

    class Meta:
        model = GoodsReceipt
        fields = (
            *DOCUMENT_FIELDS,
            "purchase_order",
            "order_number",
            "warehouse",
            "lines",
            "created_by",
            "posted_at",
        )
        read_only_fields = DOCUMENT_READ_ONLY
        extra_kwargs = {"memo": {"required": False, "max_length": 255}}


class BillLineSerializer(serializers.ModelSerializer[BillLine]):
    receipt_line = scoped(GoodsReceiptLine, allow_null=True, required=False)
    account = scoped(Account, allow_null=True, required=False)
    account_name = serializers.CharField(
        source="account.name", read_only=True, default=None, allow_null=True
    )

    class Meta:
        model = BillLine
        fields = (
            "id",
            "receipt_line",
            "account",
            "account_name",
            "description",
            "quantity",
            "unit_price",
            "amount",
            "tax_amount",
        )
        read_only_fields = ("id", "amount")
        extra_kwargs = {
            "description": {"required": False, "max_length": 255},
            "quantity": {"min_value": Decimal("0.0001")},
            "unit_price": {"min_value": 0},
            "tax_amount": {"min_value": 0, "required": False},
        }

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if (attrs.get("receipt_line") is None) == (attrs.get("account") is None):
            raise serializers.ValidationError("Each line needs a receipt line or an account.")
        return attrs


class BillSerializer(_DocumentSerializer):
    supplier = scoped(Supplier)
    lines = BillLineSerializer(many=True)
    journal_number = serializers.CharField(
        source="journal_entry.number", read_only=True, default=None, allow_null=True
    )

    class Meta:
        model = Bill
        fields = (
            *DOCUMENT_FIELDS,
            "supplier_reference",
            "due_date",
            "net",
            "tax",
            "total",
            "amount_paid",
            "lines",
            "journal_number",
            "created_by",
            "posted_at",
        )
        read_only_fields = (*DOCUMENT_READ_ONLY, "net", "tax", "total", "amount_paid")
        extra_kwargs = {
            "memo": {"required": False, "max_length": 255},
            "supplier_reference": {"required": False, "max_length": 40},
            "due_date": {"required": False, "allow_null": True},
        }


class AllocationSerializer(serializers.ModelSerializer[PaymentAllocation]):
    bill = scoped(Bill)
    bill_number = serializers.CharField(source="bill.number", read_only=True, allow_null=True)

    class Meta:
        model = PaymentAllocation
        fields = ("id", "bill", "bill_number", "amount")
        read_only_fields = ("id",)
        extra_kwargs = {"amount": {"min_value": Decimal("0.01")}}


class SupplierPaymentSerializer(_DocumentSerializer):
    supplier = scoped(Supplier)
    paid_from = scoped(Account)
    allocations = AllocationSerializer(many=True, required=False)
    journal_number = serializers.CharField(
        source="journal_entry.number", read_only=True, default=None, allow_null=True
    )

    class Meta:
        model = SupplierPayment
        fields = (
            *DOCUMENT_FIELDS,
            "amount",
            "paid_from",
            "reference",
            "allocations",
            "journal_number",
            "created_by",
            "posted_at",
        )
        read_only_fields = DOCUMENT_READ_ONLY
        extra_kwargs = {
            "memo": {"required": False, "max_length": 255},
            "reference": {"required": False, "max_length": 60},
            "amount": {"min_value": Decimal("0.01")},
        }

    def validate_allocations(self, value: list[Any]) -> list[Any]:
        return capped(value)


class StatementQuerySerializer(serializers.Serializer[Any]):
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)


class StatementLineSerializer(serializers.Serializer[Any]):
    date = serializers.DateField(source="entry.date")
    number = serializers.CharField(source="entry.number")
    kind = serializers.CharField(source="entry.kind")
    charged = serializers.DecimalField(source="entry.charged", max_digits=18, decimal_places=2)
    paid = serializers.DecimalField(source="entry.paid", max_digits=18, decimal_places=2)
    balance = serializers.DecimalField(max_digits=18, decimal_places=2)


class StatementSerializer(serializers.Serializer[Any]):
    opening = serializers.DecimalField(max_digits=18, decimal_places=2)
    lines = StatementLineSerializer(many=True)
    closing = serializers.DecimalField(max_digits=18, decimal_places=2)


class AgeingRowSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    name = serializers.CharField()
    current = serializers.DecimalField(max_digits=18, decimal_places=2)
    days_1_30 = serializers.DecimalField(max_digits=18, decimal_places=2)
    days_31_60 = serializers.DecimalField(max_digits=18, decimal_places=2)
    days_61_90 = serializers.DecimalField(max_digits=18, decimal_places=2)
    over_90 = serializers.DecimalField(max_digits=18, decimal_places=2)
    advance = serializers.DecimalField(max_digits=18, decimal_places=2)
    total = serializers.DecimalField(max_digits=18, decimal_places=2)


class DateSerializer(serializers.Serializer[None]):
    date = serializers.DateField(required=False)
