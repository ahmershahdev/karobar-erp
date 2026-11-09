from collections.abc import Callable
from datetime import date
from typing import Any, cast

from django.db.models import Count, QuerySet
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounting.services import AccountingError
from apps.accounts.models import User
from apps.core.salary_tax import Slab
from apps.platform.csv_export import csv_response
from apps.sales import documents as printing
from apps.tenancy.permissions import HasModulePermission, membership_of

from . import contributions, documents, openings, payments, runs, services
from .models import ContributionRate, MinimumWage, OpeningPay, PayrollRun, Payslip, TaxTable
from .serializers import (
    ContributionRateSerializer,
    MinimumWageSerializer,
    OpeningPaySerializer,
    PayrollReverseSerializer,
    PayrollRunDetailSerializer,
    PayrollRunSerializer,
    PostedSerializer,
    SalaryPaymentSerializer,
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
        "tax_table", "entry", "reversal", "payment__paid_from", "payment__entry"
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


class OpeningPayListView(PayrollView, generics.ListCreateAPIView[OpeningPay]):
    serializer_class = OpeningPaySerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[OpeningPay]:
        found = OpeningPay.objects.select_related("employee")
        month = self.request.query_params.get("month", "")
        if month:
            try:
                found = found.filter(year_starts=openings.year_starting(date.fromisoformat(month)))
            except ValueError:
                raise ValidationError({"month": "Give a date such as 2026-11-01."}) from None
            except services.PayrollError:
                return found.none()
        return found

    @extend_schema(parameters=[OpenApiParameter("month", str)])
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().get(request, *args, **kwargs)

    def perform_create(self, serializer: OpeningPaySerializer) -> None:  # type: ignore[override]
        saved = run(openings.save, actor(self.request), serializer.validated_data)
        serializer.instance = OpeningPay.objects.select_related("employee").get(pk=saved.pk)


class OpeningPayDetailView(PayrollView, generics.RetrieveDestroyAPIView[OpeningPay]):
    serializer_class = OpeningPaySerializer

    def get_queryset(self) -> QuerySet[OpeningPay]:
        return OpeningPay.objects.select_related("employee")

    def perform_destroy(self, instance: OpeningPay) -> None:
        run(openings.delete, actor(self.request), instance)


class PayrollRunPayView(PayrollView, generics.GenericAPIView[PayrollRun]):
    """Pay a posted month's salaries from a cash or bank account."""

    required_action = "post"

    def get_queryset(self) -> QuerySet[PayrollRun]:
        return PayrollRun.objects.all()

    @extend_schema(request=SalaryPaymentSerializer, responses=PayrollRunDetailSerializer)
    def post(self, request: Request, pk: int) -> Response:
        # The run first: another business's run is 404 whatever the body says.
        target = self.get_object()
        body = SalaryPaymentSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        run(payments.pay, actor(request), target, body.validated_data)
        return Response(PayrollRunDetailSerializer(_detail(pk)).data)


class TransferListView(PayrollView, generics.GenericAPIView[PayrollRun]):
    """The bank transfer list as CSV. It shows bank account numbers, which only people with HR
    rights may see, so it needs HR view rights as well as payroll ones."""

    def get_queryset(self) -> QuerySet[PayrollRun]:
        return PayrollRun.objects.all()

    @extend_schema(responses={(200, "text/csv"): str})
    def get(self, request: Request, pk: int) -> HttpResponse:
        found: PayrollRun = self.get_object()
        membership = membership_of(request)
        role = membership.role
        if not membership.is_owner and (
            role is None or "view" not in role.permissions.get("hr", [])
        ):
            raise PermissionDenied
        if found.status != PayrollRun.Status.POSTED:
            raise ValidationError(
                {"detail": "The transfer list is ready once the payroll is posted."}
            )
        return csv_response(
            f"salaries-{found.month:%Y-%m}.csv",
            payments.TRANSFER_HEADER,
            payments.transfer_rows(found),
        )


class PayrollRunReverseView(PayrollView, generics.GenericAPIView[PayrollRun]):
    """Undo a posted month that isn't paid yet."""

    required_action = "post"

    def get_queryset(self) -> QuerySet[PayrollRun]:
        return PayrollRun.objects.all()

    @extend_schema(request=PayrollReverseSerializer, responses=PayrollRunDetailSerializer)
    def post(self, request: Request, pk: int) -> Response:
        target = self.get_object()
        body = PayrollReverseSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        run(runs.reverse, actor(request), target, body.validated_data.get("reason", ""))
        return Response(PayrollRunDetailSerializer(_detail(pk)).data)


# EOBI and social security


class MinimumWageListView(PayrollView, generics.ListCreateAPIView[MinimumWage]):
    serializer_class = MinimumWageSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[MinimumWage]:
        return MinimumWage.objects.all()

    def perform_create(self, serializer: MinimumWageSerializer) -> None:  # type: ignore[override]
        serializer.instance = run(
            contributions.save, actor(self.request), MinimumWage(), serializer.validated_data
        )


class MinimumWageDetailView(PayrollView, generics.RetrieveUpdateDestroyAPIView[MinimumWage]):
    serializer_class = MinimumWageSerializer
    # Whole rows only, like the screen sends them.
    http_method_names = ["get", "put", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[MinimumWage]:
        return MinimumWage.objects.all()

    def perform_update(self, serializer: MinimumWageSerializer) -> None:  # type: ignore[override]
        row = cast(MinimumWage, serializer.instance)
        serializer.instance = run(
            contributions.save, actor(self.request), row, serializer.validated_data
        )

    def perform_destroy(self, instance: MinimumWage) -> None:
        run(contributions.delete, actor(self.request), instance)


class ContributionRateListView(PayrollView, generics.ListCreateAPIView[ContributionRate]):
    serializer_class = ContributionRateSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[ContributionRate]:
        return ContributionRate.objects.all()

    def perform_create(  # type: ignore[override]
        self, serializer: ContributionRateSerializer
    ) -> None:
        serializer.instance = run(
            contributions.save, actor(self.request), ContributionRate(), serializer.validated_data
        )


class ContributionRateDetailView(
    PayrollView, generics.RetrieveUpdateDestroyAPIView[ContributionRate]
):
    serializer_class = ContributionRateSerializer
    # Whole rows only: an update without a ceiling or province clears it, which a partial
    # update would do by accident.
    http_method_names = ["get", "put", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[ContributionRate]:
        return ContributionRate.objects.all()

    def perform_update(  # type: ignore[override]
        self, serializer: ContributionRateSerializer
    ) -> None:
        row = cast(ContributionRate, serializer.instance)
        values = {"wage_cap": None, "province": "", **serializer.validated_data}
        serializer.instance = run(contributions.save, actor(self.request), row, values)

    def perform_destroy(self, instance: ContributionRate) -> None:
        run(contributions.delete, actor(self.request), instance)


class ContributionsFillView(PayrollView):
    required_action = "create"

    @extend_schema(request=None, responses=TablesFilledSerializer)
    def post(self, request: Request) -> Response:
        added = run(contributions.fill_official, actor(request))
        return Response(TablesFilledSerializer({"added": added}).data)
