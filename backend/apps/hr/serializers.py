from decimal import Decimal
from typing import Any

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.core.payroll import Breakdown
from apps.inventory.serializers import scoped

from . import services
from .models import Contract, Department, Employee, SalaryComponent, SalaryStructure

PERCENT = {
    "required": False,
    "allow_null": True,
    "min_value": Decimal(0),
    "max_value": Decimal(100),
}


class DepartmentSerializer(serializers.ModelSerializer[Department]):
    class Meta:
        model = Department
        fields = ("id", "code", "name", "is_active")
        extra_kwargs = {"is_active": {"required": False}}


class SalaryComponentSerializer(serializers.ModelSerializer[SalaryComponent]):
    class Meta:
        model = SalaryComponent
        fields = ("name", "kind", "amount", "percent", "taxable", "insurable")
        extra_kwargs = {
            "amount": {"required": False, "allow_null": True, "min_value": Decimal(0)},
            "percent": PERCENT,
            "taxable": {"required": False},
            "insurable": {"required": False},
        }


class SalaryStructureSerializer(serializers.ModelSerializer[SalaryStructure]):
    components = SalaryComponentSerializer(many=True)

    class Meta:
        model = SalaryStructure
        fields = ("id", "name", "note", "is_active", "components")
        extra_kwargs = {"note": {"required": False}, "is_active": {"required": False}}

    def validate_components(self, value: list[Any]) -> list[Any]:
        if len(value) > services.MAX_COMPONENTS:
            raise serializers.ValidationError(services.TooManyComponentsError.message)
        return value


class PayLineSerializer(serializers.Serializer[Any]):
    name = serializers.CharField()
    kind = serializers.CharField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    taxable = serializers.BooleanField()


class PaySerializer(serializers.Serializer[Any]):
    """What one month comes to under a structure, before income tax."""

    lines = PayLineSerializer(many=True)
    gross = serializers.DecimalField(max_digits=18, decimal_places=2)
    deductions = serializers.DecimalField(max_digits=18, decimal_places=2)
    net = serializers.DecimalField(max_digits=18, decimal_places=2)
    taxable = serializers.DecimalField(max_digits=18, decimal_places=2)


def pay(result: Breakdown) -> dict[str, Any]:
    return {
        "lines": [vars(line) for line in result.lines],
        "gross": result.gross,
        "deductions": result.deductions,
        "net": result.net,
        "taxable": result.taxable,
    }


class ContractSerializer(serializers.ModelSerializer[Contract]):
    employee = scoped(Employee)
    structure = scoped(SalaryStructure)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    structure_name = serializers.CharField(source="structure.name", read_only=True)
    pay = serializers.SerializerMethodField()

    class Meta:
        model = Contract
        fields = (
            "id",
            "employee",
            "employee_name",
            "kind",
            "starts_on",
            "ends_on",
            "structure",
            "structure_name",
            "basic_salary",
            "note",
            "pay",
        )
        extra_kwargs = {
            "ends_on": {"required": False, "allow_null": True},
            "note": {"required": False},
            "basic_salary": {"min_value": Decimal(0)},
        }

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        starts = attrs.get("starts_on", getattr(self.instance, "starts_on", None))
        ends = attrs.get("ends_on", getattr(self.instance, "ends_on", None))
        if starts and ends and ends < starts:
            raise serializers.ValidationError(
                {"ends_on": ["A contract can't end before it starts."]}
            )
        return attrs

    @extend_schema_field(PaySerializer(allow_null=True))
    def get_pay(self, contract: Contract) -> dict[str, Any] | None:
        try:
            result = services.structure_breakdown(contract.structure, contract.basic_salary)
            data: dict[str, Any] = PaySerializer(pay(result)).data
            return data
        except services.DeductionsTooLargeError:
            return None


class CurrentContractSerializer(serializers.ModelSerializer[Contract]):
    structure_name = serializers.CharField(source="structure.name", read_only=True)

    class Meta:
        model = Contract
        fields = ("id", "kind", "starts_on", "ends_on", "structure_name", "basic_salary")


class EmployeeSerializer(serializers.ModelSerializer[Employee]):
    department = scoped(Department, allow_null=True, required=False)
    department_name = serializers.CharField(
        source="department.name", read_only=True, default=None, allow_null=True
    )
    current_contract = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = (
            "id",
            "code",
            "full_name",
            "job_title",
            "department",
            "department_name",
            "phone",
            "email",
            "national_id",
            "bank_account",
            "joined_on",
            "left_on",
            "province",
            "nationality",
            "insured_since",
            "pays_eobi",
            "pays_social_security",
            "current_contract",
        )
        extra_kwargs = {
            "province": {"required": False},
            "nationality": {"required": False},
            "insured_since": {"required": False, "allow_null": True},
            "pays_eobi": {"required": False},
            "pays_social_security": {"required": False},
            "job_title": {"required": False},
            "phone": {"required": False},
            "email": {"required": False},
            "national_id": {"required": False},
            "bank_account": {"required": False},
            "left_on": {"required": False, "allow_null": True},
        }

    def validate_nationality(self, value: str) -> str:
        code = value.strip().upper()
        if code and not (len(code) == 2 and code.isascii() and code.isalpha()):
            raise serializers.ValidationError("Use the two-letter country code, such as AE.")
        return code

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        joined = attrs.get("joined_on", getattr(self.instance, "joined_on", None))
        left = attrs.get("left_on", getattr(self.instance, "left_on", None))
        if joined and left and left < joined:
            raise serializers.ValidationError({"left_on": ["Someone can't leave before joining."]})
        return attrs

    @extend_schema_field(CurrentContractSerializer(allow_null=True))
    def get_current_contract(self, employee: Employee) -> Any:
        contract = services.current_contract(employee, timezone.localdate())
        return CurrentContractSerializer(contract).data if contract else None


class PreviewSerializer(serializers.Serializer[Any]):
    basic = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal(0))
