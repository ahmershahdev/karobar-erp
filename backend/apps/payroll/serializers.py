from decimal import Decimal
from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounting.models import Account
from apps.hr.models import Employee
from apps.hr.time_off import COUNTRIES
from apps.inventory.serializers import scoped

from .gratuity import GRATUITY_COUNTRIES
from .models import (
    ContributionRate,
    GratuityPayout,
    GratuityRule,
    MinimumWage,
    OpeningPay,
    PayrollRun,
    Payslip,
    SalaryPayment,
    TaxTable,
)

MAX_SLABS = 20
MAX_BANDS = 10


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
            "gratuity_accrued",
            "gratuity_change",
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
            "gratuity_change",
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


class ResignationBandSerializer(serializers.Serializer[Any]):
    years = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal(0))
    # A fraction such as "1/3", so a third stays exactly a third.
    share = serializers.RegexField(r"^\d{1,3}/\d{1,3}$")
    after = serializers.BooleanField(default=False)


class GratuityRuleSerializer(serializers.ModelSerializer[GratuityRule]):
    country = serializers.ChoiceField(choices=sorted(GRATUITY_COUNTRIES))
    resignation = ResignationBandSerializer(many=True, required=False)

    class Meta:
        model = GratuityRule
        fields = (
            "id",
            "country",
            "starts_on",
            "first_years",
            "first_days",
            "later_days",
            "month_days",
            "min_years",
            "cap_months",
            "wage",
            "excludes_nationals",
            "excludes_unpaid_days",
            "resignation",
            "source",
        )
        extra_kwargs = {
            "month_days": {"required": False},
            "min_years": {"required": False},
            "cap_months": {"required": False, "allow_null": True},
            "excludes_nationals": {"required": False},
            "excludes_unpaid_days": {"required": False},
        }

    def validate_resignation(self, bands: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(bands) > MAX_BANDS:
            raise serializers.ValidationError(f"Give at most {MAX_BANDS} bands.")
        return [{**b, "years": str(b["years"])} for b in bands]


class GratuityPayoutSerializer(serializers.ModelSerializer[GratuityPayout]):
    paid_from = scoped(Account)
    paid_from_name = serializers.CharField(source="paid_from.name", read_only=True)
    entry_number = serializers.CharField(source="entry.number", read_only=True)

    class Meta:
        model = GratuityPayout
        fields = (
            "id",
            "reason",
            "service_days",
            "wage",
            "full",
            "share",
            "amount",
            "provision",
            "paid_on",
            "paid_from",
            "paid_from_name",
            "entry_number",
        )
        read_only_fields = (
            "service_days",
            "wage",
            "full",
            "share",
            "amount",
            "provision",
        )


class GratuityQuoteSerializer(serializers.Serializer[Any]):
    # Built up so far: the provision on the latest posted payslip.
    accrued = serializers.DecimalField(max_digits=18, decimal_places=2)
    # Only for someone who left and isn't paid yet: what each reason would pay.
    service_days = serializers.IntegerField(allow_null=True)
    if_ended = serializers.DecimalField(max_digits=18, decimal_places=2, allow_null=True)
    if_resigned = serializers.DecimalField(max_digits=18, decimal_places=2, allow_null=True)
    payout = GratuityPayoutSerializer(allow_null=True)
