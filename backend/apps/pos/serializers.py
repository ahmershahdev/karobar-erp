from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.accounting.models import TaxRate
from apps.inventory.models import Product, Unit, Warehouse
from apps.inventory.serializers import scoped
from apps.purchasing.serializers import capped

from .models import PosSale, PosSession


def money(**kwargs: Any) -> serializers.DecimalField:
    return serializers.DecimalField(max_digits=18, decimal_places=2, **kwargs)


class OpenTillSerializer(serializers.Serializer[Any]):
    warehouse = scoped(Warehouse)
    opening_float = money(min_value=Decimal(0), required=False, default=Decimal(0))


class TillSerializer(serializers.ModelSerializer[PosSession]):
    status = serializers.CharField(read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    opened_by = serializers.EmailField(source="opened_by.email", read_only=True)
    sales_count = serializers.IntegerField(read_only=True)
    cash_sales = money(read_only=True)
    card_sales = money(read_only=True)

    class Meta:
        model = PosSession
        fields = (
            "id",
            "status",
            "warehouse",
            "warehouse_name",
            "opening_float",
            "expected_cash",
            "counted_cash",
            "difference",
            "opened_by",
            "opened_at",
            "closed_at",
            "sales_count",
            "cash_sales",
            "card_sales",
        )
        read_only_fields = fields


class CartLineSerializer(serializers.Serializer[Any]):
    product = scoped(Product)
    unit = scoped(Unit)
    quantity = serializers.DecimalField(
        max_digits=18, decimal_places=4, min_value=Decimal("0.0001")
    )


class SaleRequestSerializer(serializers.Serializer[Any]):
    lines = CartLineSerializer(many=True)
    method = serializers.ChoiceField(choices=PosSale.Method.choices)
    tendered = money(min_value=Decimal(0), required=False, allow_null=True)
    tax_rate = scoped(TaxRate, allow_null=True, required=False)

    def validate_lines(self, value: list[Any]) -> list[Any]:
        return capped(value)


class SaleResultSerializer(serializers.ModelSerializer[PosSale]):
    number = serializers.CharField(source="invoice.number", read_only=True)

    class Meta:
        model = PosSale
        fields = ("id", "number", "method", "amount", "tendered", "change")
        read_only_fields = fields


class CloseTillSerializer(serializers.Serializer[Any]):
    counted_cash = money(min_value=Decimal(0))


class FoundProductSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField(source="product.pk")
    sku = serializers.CharField(source="product.sku")
    name = serializers.CharField(source="product.name")
    unit = serializers.IntegerField(source="unit.pk")
    unit_code = serializers.CharField(source="unit.code")
    price = serializers.DecimalField(max_digits=18, decimal_places=4, allow_null=True)
    exact = serializers.BooleanField()


class PosWarehouseSerializer(serializers.ModelSerializer[Warehouse]):
    class Meta:
        model = Warehouse
        fields = ("id", "code", "name")
        read_only_fields = fields
