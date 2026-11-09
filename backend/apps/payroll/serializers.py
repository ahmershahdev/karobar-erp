from decimal import Decimal
from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounting.models import Account
from apps.hr.models import Employee
from apps.hr.time_off import COUNTRIES
from apps.inventory.serializers import scoped

from .models import (
    ContributionRate,
    MinimumWage,
    OpeningPay,
    PayrollRun,
    Payslip,
    SalaryPayment,
    TaxTable,
)

MAX_SLABS = 20


def _money() -> serializers.DecimalField:
    return serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal(0))


class SlabSerializer(serializers.Serializer[Any]):
    over = _money()
    fixed = _money()
    rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal(0), max_value=Decimal(100)
    )


class TaxTableSerializer(serializers.ModelSerializer[TaxTable]):
    country = serializers.ChoiceField(choices=list(COUNTRIES))
    slabs = SlabSerializer(many=True)

    class Meta:
        model = TaxTable
        fields = ("id", "country", "name", "starts_on", "ends_on", "source", "slabs")

    def validate_slabs(self, slabs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not 1 <= len(slabs) <= MAX_SLABS:
            raise serializers.ValidationError(f"Give between 1 and {MAX_SLABS} slabs.")
        return slabs


class TablesFilledSerializer(serializers.Serializer[Any]):
    added = serializers.IntegerField()


class PayslipLineSerializer(serializers.Serializer[Any]):
    name = serializers.CharField()
    kind = serializers.CharField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    taxable = serializers.BooleanField()


class PayslipContributionSerializer(serializers.Serializer[Any]):
    scheme = serializers.CharField()
    base = serializers.DecimalField(max_digits=18, decimal_places=2)
    employer_percent = serializers.DecimalField(max_digits=5, decimal_places=2)
    employee_percent = serializers.DecimalField(max_digits=5, decimal_places=2)
    employer = serializers.DecimalField(max_digits=18, decimal_places=2)
    employee = serializers.DecimalField(max_digits=18, decimal_places=2)


class PayslipSerializer(serializers.ModelSerializer[Payslip]):
    employee_code = serializers.CharField(source="employee.code", read_only=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    lines = PayslipLineSerializer(many=True, read_only=True)
    contributions = PayslipContributionSerializer(many=True, read_only=True)

    class Meta:
        model = Payslip
        fields = (
            "id",
            "employee",
            "employee_code",
            "employee_name",
            "month_days",
            "paid_days",
            "unpaid_days",
            "lines",
            "gross",
            "deductions",
            "taxable",
            "tax",
            "net",
            "projected_income",
            "year_tax",
            "contributions",
            "employee_contributions",
            "employer_contributions",
        )
        read_only_fields = fields


class SalaryPaymentSerializer(serializers.ModelSerializer[SalaryPayment]):
    paid_from = scoped(Account)
    paid_from_name = serializers.CharField(source="paid_from.name", read_only=True)
    entry_number = serializers.CharField(source="entry.number", read_only=True)

    class Meta:
        model = SalaryPayment
        fields = (
            "id",
            "paid_on",
            "paid_from",
            "paid_from_name",
            "amount",
            "reference",
            "entry_number",
        )
        read_only_fields = ("amount",)


class PayrollRunSerializer(serializers.ModelSerializer[PayrollRun]):
    people = serializers.IntegerField(read_only=True)
    tax_table_name = serializers.CharField(
        source="tax_table.name", read_only=True, default=None, allow_null=True
    )
    entry_number = serializers.CharField(
        source="entry.number", read_only=True, default=None, allow_null=True
    )
    payment = serializers.SerializerMethodField()
    reversal_number = serializers.CharField(
        source="reversal.number", read_only=True, default=None, allow_null=True
    )

    class Meta:
        model = PayrollRun
        fields: tuple[str, ...] = (
            "id",
            "month",
            "status",
            "number",
            "people",
            "gross",
            "deductions",
            "tax",
            "net",
            "employee_contributions",
            "employer_contributions",
            "tax_table_name",
            "entry_number",
            "worked_out_at",
            "posted_at",
            "payment",
            "reversal_number",
            "reversed_at",
            "reversal_reason",
        )
        read_only_fields: tuple[str, ...] = fields

    @extend_schema_field(SalaryPaymentSerializer(allow_null=True))
    def get_payment(self, run: PayrollRun) -> Any:
        payment = getattr(run, "payment", None)
        return SalaryPaymentSerializer(payment).data if payment else None


class PayrollRunDetailSerializer(PayrollRunSerializer):
    payslips = PayslipSerializer(many=True, read_only=True)

    class Meta(PayrollRunSerializer.Meta):
        fields = (*PayrollRunSerializer.Meta.fields, "payslips")
        read_only_fields = fields


class WorkOutSerializer(serializers.Serializer[Any]):
    # Any day of the month; the run is for the whole month.
    month = serializers.DateField()


class PostedSerializer(serializers.Serializer[Any]):
    # False when pay changed since the draft was made: the draft was updated instead.
    posted = serializers.BooleanField()
    run = PayrollRunDetailSerializer()


class OpeningPaySerializer(serializers.ModelSerializer[OpeningPay]):
    employee = scoped(Employee)
    employee_code = serializers.CharField(source="employee.code", read_only=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    # Any day in the tax year the figures belong to.
    month = serializers.DateField(write_only=True)
    taxable = _money()
    tax = _money()

    class Meta:
        model = OpeningPay
        fields = (
            "id",
            "employee",
            "employee_code",
            "employee_name",
            "month",
            "year_starts",
            "taxable",
            "tax",
            "note",
        )
        read_only_fields = ("year_starts",)


class PayrollReverseSerializer(serializers.Serializer[Any]):
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)


class MinimumWageSerializer(serializers.ModelSerializer[MinimumWage]):
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0.01"))

    class Meta:
        model = MinimumWage
        fields = ("id", "province", "starts_on", "amount", "source")


class ContributionRateSerializer(serializers.ModelSerializer[ContributionRate]):
    employer_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal(0), max_value=Decimal(100)
    )
    employee_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal(0), max_value=Decimal(100)
    )
    wage_cap = serializers.DecimalField(
        max_digits=18,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = ContributionRate
        fields = (
            "id",
            "scheme",
            "province",
            "starts_on",
            "employer_percent",
            "employee_percent",
            "on_minimum_wage",
            "wage_cap",
            "source",
        )
        extra_kwargs = {"province": {"required": False}, "on_minimum_wage": {"required": False}}
