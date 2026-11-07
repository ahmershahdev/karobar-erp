from typing import Any

from rest_framework import serializers


def money(**kwargs: Any) -> serializers.DecimalField:
    return serializers.DecimalField(max_digits=18, decimal_places=2, **kwargs)


class PeriodSerializer(serializers.Serializer[Any]):
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)


class ReportLineSerializer(serializers.Serializer[Any]):
    code = serializers.CharField()
    name = serializers.CharField()
    amount = money()


class ReportSectionSerializer(serializers.Serializer[Any]):
    lines = ReportLineSerializer(many=True)
    total = money()


class ProfitLossSerializer(serializers.Serializer[Any]):
    income = ReportSectionSerializer()
    cost_of_sales = ReportSectionSerializer()
    gross_profit = money()
    expenses = ReportSectionSerializer()
    net_profit = money()


class BalanceSheetSerializer(serializers.Serializer[Any]):
    assets = ReportSectionSerializer()
    liabilities = ReportSectionSerializer()
    equity = ReportSectionSerializer()
    profit_to_date = money()
    total_liabilities_and_equity = money()
    balanced = serializers.BooleanField()


class CashFlowSerializer(serializers.Serializer[Any]):
    opening = money()
    from_customers = money()
    to_suppliers = money()
    other = money()
    closing = money()


class SalesTaxSerializer(serializers.Serializer[Any]):
    taxable_sales = money()
    output_tax = money()
    taxable_purchases = money()
    input_tax = money()
    payable = money()


class DayAmountSerializer(serializers.Serializer[Any]):
    date = serializers.DateField()
    amount = money()


class ProductAmountSerializer(serializers.Serializer[Any]):
    name = serializers.CharField()
    amount = money()


class HomeSetupSerializer(serializers.Serializer[Any]):
    store = serializers.BooleanField()
    product = serializers.BooleanField()
    price = serializers.BooleanField()
    sale = serializers.BooleanField()


class HomeAttentionSerializer(serializers.Serializer[Any]):
    low_stock = serializers.IntegerField()
    overdue = serializers.IntegerField()
    open_tills = serializers.IntegerField()


class HomeSerializer(serializers.Serializer[Any]):
    setup = HomeSetupSerializer()
    attention = HomeAttentionSerializer()


class DashboardSerializer(serializers.Serializer[Any]):
    sales_today = money()
    sales_month = money()
    gross_profit_month = money()
    margin_percent = money(allow_null=True)
    stock_value = money()
    receivable = money()
    payable = money()
    sales_by_day = DayAmountSerializer(many=True)
    top_products = ProductAmountSerializer(many=True)
