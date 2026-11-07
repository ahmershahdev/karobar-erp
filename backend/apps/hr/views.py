from typing import Any, cast

from django.db.models import Q, QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.inventory.services import InventoryError
from apps.tenancy.permissions import HasModulePermission

from . import services
from .models import Contract, Department, Employee, SalaryStructure
from .serializers import (
    ContractSerializer,
    DepartmentSerializer,
    EmployeeSerializer,
    PaySerializer,
    PreviewSerializer,
    SalaryStructureSerializer,
    pay,
)


def actor(request: Request) -> User:
    return cast(User, request.user)


def run(call: Any, *args: Any) -> Any:
    try:
        return call(*args)
    except (services.HrError, InventoryError) as exc:
        raise ValidationError({"detail": type(exc).message}) from exc


class HrView(APIView):
    permission_classes = [HasModulePermission]
    module = "hr"
    throttle_scope = "tenancy"


# Departments


class DepartmentListView(HrView, generics.ListCreateAPIView[Department]):
    serializer_class = DepartmentSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[Department]:
        return Department.objects.all()

    def perform_create(self, serializer: DepartmentSerializer) -> None:  # type: ignore[override]
        serializer.instance = run(
            services.save_department, actor(self.request), Department(), serializer.validated_data
        )


class DepartmentDetailView(HrView, generics.RetrieveUpdateDestroyAPIView[Department]):
    serializer_class = DepartmentSerializer
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[Department]:
        return Department.objects.all()

    def perform_update(self, serializer: DepartmentSerializer) -> None:  # type: ignore[override]
        run(
            services.save_department,
            actor(self.request),
            serializer.instance,
            serializer.validated_data,
        )

    def perform_destroy(self, instance: Department) -> None:
        run(services.delete_department, actor(self.request), instance)


# Salary structures


def _component_inputs(data: dict[str, Any]) -> list[services.ComponentInput]:
    return [
        services.ComponentInput(
            row["name"],
            row["kind"],
            row.get("amount"),
            row.get("percent"),
            row.get("taxable", True),
        )
        for row in data.get("components", [])
    ]


def _structures() -> QuerySet[SalaryStructure]:
    return SalaryStructure.objects.prefetch_related("components")


class SalaryStructureListView(HrView, generics.ListCreateAPIView[SalaryStructure]):
    serializer_class = SalaryStructureSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[SalaryStructure]:
        return _structures()

    def perform_create(self, serializer: SalaryStructureSerializer) -> None:  # type: ignore[override]
        data = serializer.validated_data
        saved = run(services.save_structure, actor(self.request), data, _component_inputs(data))
        serializer.instance = _structures().get(pk=saved.pk)


class SalaryStructureDetailView(HrView, generics.RetrieveUpdateDestroyAPIView[SalaryStructure]):
    serializer_class = SalaryStructureSerializer
    http_method_names = ["get", "put", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[SalaryStructure]:
        return _structures()

    def perform_update(self, serializer: SalaryStructureSerializer) -> None:  # type: ignore[override]
        data = serializer.validated_data
        structure = cast(SalaryStructure, serializer.instance)
        run(services.save_structure, actor(self.request), data, _component_inputs(data), structure)
        serializer.instance = _structures().get(pk=structure.pk)

    def perform_destroy(self, instance: SalaryStructure) -> None:
        run(services.delete_structure, actor(self.request), instance)


class SalaryPreviewView(HrView, generics.GenericAPIView[SalaryStructure]):
    """What a month comes to under this structure for a given basic, before income tax."""

    def get_queryset(self) -> QuerySet[SalaryStructure]:
        return _structures()

    @extend_schema(
        parameters=[OpenApiParameter("basic", str, required=True)], responses=PaySerializer
    )
    def get(self, request: Request, pk: int) -> Response:
        body = PreviewSerializer(data=request.query_params)
        body.is_valid(raise_exception=True)
        result = run(services.structure_breakdown, self.get_object(), body.validated_data["basic"])
        return Response(PaySerializer(pay(result)).data)


# Employees


def _employees() -> QuerySet[Employee]:
    return Employee.objects.select_related("department")


@extend_schema(
    parameters=[
        OpenApiParameter("q", str),
        OpenApiParameter("status", str, enum=["active", "left"]),
    ]
)
class EmployeeListView(HrView, generics.ListCreateAPIView[Employee]):
    serializer_class = EmployeeSerializer

    def get_queryset(self) -> QuerySet[Employee]:
        query = _employees()
        params = self.request.query_params
        if term := params.get("q", "").strip()[:80]:
            query = query.filter(
                Q(full_name__icontains=term)
                | Q(code__icontains=term)
                | Q(job_title__icontains=term)
            )
        status = params.get("status")
        if status == "active":
            query = query.filter(left_on__isnull=True)
        elif status == "left":
            query = query.filter(left_on__isnull=False)
        return query

    def perform_create(self, serializer: EmployeeSerializer) -> None:  # type: ignore[override]
        created = run(
            services.save_employee, actor(self.request), Employee(), serializer.validated_data
        )
        serializer.instance = _employees().get(pk=created.pk)


class EmployeeDetailView(HrView, generics.RetrieveUpdateDestroyAPIView[Employee]):
    serializer_class = EmployeeSerializer
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[Employee]:
        return _employees()

    def perform_update(self, serializer: EmployeeSerializer) -> None:  # type: ignore[override]
        employee = cast(Employee, serializer.instance)
        run(services.save_employee, actor(self.request), employee, serializer.validated_data)
        serializer.instance = _employees().get(pk=employee.pk)

    def perform_destroy(self, instance: Employee) -> None:
        run(services.delete_employee, actor(self.request), instance)


# Contracts


def _contracts() -> QuerySet[Contract]:
    return Contract.objects.select_related("employee", "structure").prefetch_related(
        "structure__components"
    )


@extend_schema(parameters=[OpenApiParameter("employee", int)])
class ContractListView(HrView, generics.ListCreateAPIView[Contract]):
    serializer_class = ContractSerializer

    def get_queryset(self) -> QuerySet[Contract]:
        query = _contracts()
        if self.request.query_params.get("employee", "").isdigit():
            query = query.filter(employee_id=self.request.query_params["employee"])
        return query

    def perform_create(self, serializer: ContractSerializer) -> None:  # type: ignore[override]
        created = run(services.save_contract, actor(self.request), serializer.validated_data)
        serializer.instance = _contracts().get(pk=created.pk)


class ContractDetailView(HrView, generics.RetrieveUpdateDestroyAPIView[Contract]):
    serializer_class = ContractSerializer
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[Contract]:
        return _contracts()

    def perform_update(self, serializer: ContractSerializer) -> None:  # type: ignore[override]
        contract = cast(Contract, serializer.instance)
        run(services.save_contract, actor(self.request), serializer.validated_data, contract)
        serializer.instance = _contracts().get(pk=contract.pk)

    def perform_destroy(self, instance: Contract) -> None:
        run(services.delete_contract, actor(self.request), instance)
