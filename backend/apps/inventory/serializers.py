from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.accounting.models import Account

from .models import (
    Batch,
    Category,
    Product,
    ProductUnit,
    StockEntry,
    StockEntryLine,
    StockLevel,
    StockMove,
    Unit,
    Warehouse,
)


def scoped(model: Any, **kwargs: Any) -> serializers.PrimaryKeyRelatedField[Any]:
    """A related field that only accepts rows of the active tenant, resolved at request time."""

    class Field(serializers.PrimaryKeyRelatedField[Any]):
        def get_queryset(self) -> Any:
            return model.objects.all()

    return Field(queryset=model.all_tenants.none(), **kwargs)


class UnitSerializer(serializers.ModelSerializer[Unit]):
    class Meta:
        model = Unit
        fields = ("id", "code", "name")
        extra_kwargs = {"code": {"max_length": 10}, "name": {"max_length": 50}}


class CategorySerializer(serializers.ModelSerializer[Category]):
    class Meta:
        model = Category
        fields = ("id", "name")
        extra_kwargs = {"name": {"max_length": 80}}


class WarehouseSerializer(serializers.ModelSerializer[Warehouse]):
    class Meta:
        model = Warehouse
        fields = ("id", "code", "name", "is_active")
        extra_kwargs = {"code": {"max_length": 20}, "name": {"max_length": 100}}


class PackSerializer(serializers.ModelSerializer[ProductUnit]):
    unit = scoped(Unit)
    unit_code = serializers.CharField(source="unit.code", read_only=True)

    class Meta:
        model = ProductUnit
        fields = ("unit", "unit_code", "factor", "barcode")
        extra_kwargs = {
            "factor": {"min_value": Decimal("0.0001")},
            "barcode": {
                "required": False,
                "allow_null": True,
                "allow_blank": True,
                "max_length": 64,
            },
        }


class ProductSerializer(serializers.ModelSerializer[Product]):
    unit = scoped(Unit)
    unit_code = serializers.CharField(source="unit.code", read_only=True)
    category = scoped(Category, allow_null=True, required=False)
    variant_of = scoped(Product, allow_null=True, required=False)
    packs = PackSerializer(many=True, required=False)
    on_hand = serializers.DecimalField(
        max_digits=18, decimal_places=4, read_only=True, required=False
    )

    class Meta:
        model = Product
        fields = (
            "id",
            "sku",
            "name",
            "category",
            "unit",
            "unit_code",
            "variant_of",
            "attributes",
            "track_batches",
            "reorder_level",
            "is_active",
            "packs",
            "on_hand",
        )
        read_only_fields = ("id",)
        extra_kwargs = {
            "sku": {"max_length": 40},
            "name": {"max_length": 150},
            "reorder_level": {"min_value": 0, "required": False},
            "attributes": {"required": False},
        }

    def validate_attributes(self, value: Any) -> dict[str, str]:
        if not isinstance(value, dict) or len(value) > 10:
            raise serializers.ValidationError('Use up to 10 attributes, like {"size": "L"}.')
        if not all(
            isinstance(k, str) and isinstance(v, str) and len(k) <= 40 and len(v) <= 80
            for k, v in value.items()
        ):
            raise serializers.ValidationError("Attribute names and values must be short text.")
        return value

    def validate_packs(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(value) > 20:
            raise serializers.ValidationError("A product can have at most 20 packs.")
        units = [pack["unit"].pk for pack in value]
        if len(units) != len(set(units)):
            raise serializers.ValidationError("Each unit can appear once.")
        return value


class BatchSerializer(serializers.ModelSerializer[Batch]):
    class Meta:
        model = Batch
        fields = ("id", "product", "number", "expiry_date")
        read_only_fields = fields


class StockLevelSerializer(serializers.ModelSerializer[StockLevel]):
    sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit_code = serializers.CharField(source="product.unit.code", read_only=True)
    warehouse_code = serializers.CharField(source="warehouse.code", read_only=True)

    class Meta:
        model = StockLevel
        fields = (
            "id",
            "product",
            "sku",
            "product_name",
            "unit_code",
            "warehouse",
            "warehouse_code",
            "quantity",
            "value",
        )
        read_only_fields = fields


class StockMoveSerializer(serializers.ModelSerializer[StockMove]):
    number = serializers.CharField(
        source="entry.number", read_only=True, default=None, allow_null=True
    )
    warehouse_code = serializers.CharField(source="warehouse.code", read_only=True)
    batch_number = serializers.CharField(
        source="batch.number", read_only=True, default=None, allow_null=True
    )

    class Meta:
        model = StockMove
        fields = (
            "id",
            "date",
            "number",
            "product",
            "warehouse",
            "warehouse_code",
            "batch_number",
            "quantity",
            "value",
        )
        read_only_fields = fields


class StockEntryLineSerializer(serializers.ModelSerializer[StockEntryLine]):
    product = scoped(Product)
    unit = scoped(Unit)
    sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit_code = serializers.CharField(source="unit.code", read_only=True)

    class Meta:
        model = StockEntryLine
        fields = (
            "id",
            "product",
            "sku",
            "product_name",
            "unit",
            "unit_code",
            "quantity",
            "unit_cost",
            "batch_number",
            "expiry_date",
        )
        read_only_fields = ("id", "sku", "product_name", "unit_code")
        extra_kwargs = {
            "quantity": {"min_value": 0},
            "unit_cost": {"min_value": 0, "required": False, "allow_null": True},
            "batch_number": {"required": False, "max_length": 40},
            "expiry_date": {"required": False, "allow_null": True},
        }


class StockEntrySerializer(serializers.ModelSerializer[StockEntry]):
    warehouse = scoped(Warehouse)
    to_warehouse = scoped(Warehouse, allow_null=True, required=False)
    contra_account = scoped(Account, allow_null=True, required=False)
    lines = StockEntryLineSerializer(many=True)
    journal_number = serializers.CharField(
        source="journal_entry.number", read_only=True, default=None, allow_null=True
    )
    created_by = serializers.EmailField(source="created_by.email", read_only=True)

    class Meta:
        model = StockEntry
        fields = (
            "id",
            "kind",
            "number",
            "date",
            "memo",
            "status",
            "warehouse",
            "to_warehouse",
            "contra_account",
            "lines",
            "journal_number",
            "created_by",
            "posted_at",
        )
        read_only_fields = ("id", "number", "status", "posted_at")
        extra_kwargs = {"memo": {"required": False, "max_length": 255}}

    def validate_lines(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(value) > 500:
            raise serializers.ValidationError("An entry can have at most 500 lines.")
        return value


class AlertsSerializer(serializers.Serializer[None]):
    low_stock = serializers.ListField(child=serializers.DictField())
    expiring = serializers.ListField(child=serializers.DictField())
