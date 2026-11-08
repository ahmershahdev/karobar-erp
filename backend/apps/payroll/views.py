from collections.abc import Callable
from typing import Any, cast

from django.db.models import Count, QuerySet
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounting.services import AccountingError
from apps.accounts.models import User
from apps.core.salary_tax import Slab
from apps.sales import documents as printing
from apps.tenancy.permissions import HasModulePermission

from . import documents, runs, services
from .models import PayrollRun, Payslip, TaxTable
from .serializers import (
    PayrollRunDetailSerializer,
    PayrollRunSerializer,
    PostedSerializer,
    TablesFilledSerializer,
    TaxTableSerializer,
    WorkOutSerializer,
)


def actor(request: Request) -> User:
    return cast(User, request.user)


def run(call: Callable[..., Any], *args: Any) -> Any:
    try:
        return call(*args)
    except services.PayrollError as exc:
        # Errors about particular people name them by employee code, never by anything private.
        detail = " ".join([type(exc).message, ", ".join(str(a) for a in exc.args)]).strip()
        raise ValidationError({"detail": detail}) from exc
    except AccountingError as exc:
        raise ValidationError({"detail": type(exc).message}) from exc


class PayrollView(APIView):
    permission_classes = [HasModulePermission]
    module = "payroll"
    throttle_scope = "tenancy"


def _slabs(data: dict[str, Any]) -> tuple[dict[str, Any], list[Slab]]:
    values = dict(data)
    slabs = [Slab(s["over"], s["fixed"], s["rate"]) for s in values.pop("slabs")]
    return values, slabs


class TaxTableListView(PayrollView, generics.ListCreateAPIView[TaxTable]):
    serializer_class = TaxTableSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[TaxTable]:
        return TaxTable.objects.prefetch_related("slabs")

    def perform_create(self, serializer: TaxTableSerializer) -> None:  # type: ignore[override]
        values, slabs = _slabs(serializer.validated_data)
        created = run(services.save_table, actor(self.request), values, slabs)
        serializer.instance = self.get_queryset().get(pk=created.pk)


class TaxTableDetailView(PayrollView, generics.RetrieveUpdateDestroyAPIView[TaxTable]):
    serializer_class = TaxTableSerializer

    def get_queryset(self) -> QuerySet[TaxTable]:
        return TaxTable.objects.prefetch_related("slabs")

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # Slabs are replaced as a whole, so a change always sends all of them.
        kwargs["partial"] = False
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer: TaxTableSerializer) -> None:  # type: ignore[override]
        values, slabs = _slabs(serializer.validated_data)
        run(services.save_table, actor(self.request), values, slabs, serializer.instance)
        serializer.instance = self.get_queryset().get(pk=cast(TaxTable, serializer.instance).pk)

    def perform_destroy(self, instance: TaxTable) -> None:
        run(services.delete_table, actor(self.request), instance)


class TaxTableFillView(PayrollView):
    required_action = "create"

    @extend_schema(request=None, responses=TablesFilledSerializer)
    def post(self, request: Request) -> Response:
        return Response({"added": run(services.fill_official, actor(request))})


def _runs() -> QuerySet[PayrollRun]:
    runs_with_people: QuerySet[PayrollRun] = PayrollRun.objects.select_related(
        "tax_table", "entry"
    ).annotate(people=Count("payslips"))
    return runs_with_people


class PayrollRunListView(PayrollView, generics.ListAPIView[PayrollRun]):
    serializer_class = PayrollRunSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[PayrollRun]:
        return _runs()

    @extend_schema(request=WorkOutSerializer, responses=PayrollRunDetailSerializer)
    def post(self, request: Request) -> Response:
        """Work out a month's payroll as a draft, or work out its draft again."""
        body = WorkOutSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        made = run(runs.work_out, actor(request), body.validated_data["month"])
        return Response(PayrollRunDetailSerializer(_detail(made.pk)).data)


def _detail(pk: int) -> PayrollRun:
    found: PayrollRun = _runs().prefetch_related("payslips__employee").get(pk=pk)
    return found


class PayrollRunDetailView(PayrollView, generics.RetrieveDestroyAPIView[PayrollRun]):
    serializer_class = PayrollRunDetailSerializer

    def get_queryset(self) -> QuerySet[PayrollRun]:
        return _runs().prefetch_related("payslips__employee")

    def perform_destroy(self, instance: PayrollRun) -> None:
        run(runs.delete, actor(self.request), instance)


class PayrollRunPostView(PayrollView, generics.GenericAPIView[PayrollRun]):
    required_action = "post"

    def get_queryset(self) -> QuerySet[PayrollRun]:
        return PayrollRun.objects.all()

    @extend_schema(request=None, responses=PostedSerializer)
    def post(self, request: Request, pk: int) -> Response:
        posted = run(runs.post, actor(request), self.get_object())
        data = PayrollRunDetailSerializer(_detail(pk)).data
        return Response({"posted": posted, "run": data})


class PrintingUnavailable(APIException):
    status_code = 503
    default_detail = printing.PdfUnavailableError.message
    default_code = "pdf_unavailable"


class PayslipPdfView(PayrollView, generics.GenericAPIView[Payslip]):
    def get_queryset(self) -> QuerySet[Payslip]:
        return Payslip.objects.select_related("run", "employee", "employee__department")

    @extend_schema(
        parameters=[OpenApiParameter("lang", str)],
        responses={(200, "application/pdf"): bytes},
    )
    def get(self, request: Request, pk: int) -> HttpResponse:
        payslip: Payslip = self.get_object()
        if payslip.run.status != PayrollRun.Status.POSTED:
            raise ValidationError(
                {"detail": "Payslips can be printed once the payroll is posted."}
            )
        language = request.query_params.get("lang", "")
        if language not in printing.LANGUAGES:
            language = "en"
        try:
            pdf = printing.to_pdf(documents.payslip_html(payslip, language))
        except printing.PdfUnavailableError as exc:
            raise PrintingUnavailable from exc
        response = HttpResponse(pdf, content_type="application/pdf")
        name = f"{payslip.run.number}-{payslip.employee.code}"
        response["Content-Disposition"] = f'inline; filename="{name}.pdf"'
        return response
