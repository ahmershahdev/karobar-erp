from dataclasses import asdict
from decimal import Decimal
from typing import Any, cast

from django.db.models import Prefetch, QuerySet
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.platform.csv_export import csv_response
from apps.tenancy.permissions import HasModulePermission

from . import services
from .models import Account, FiscalPeriod, FiscalYear, JournalEntry, JournalLine, TaxRate
from .reports import general_ledger, trial_balance
from .serializers import (
    AccountSerializer,
    FiscalPeriodSerializer,
    FiscalYearSerializer,
    JournalEntrySerializer,
    PeriodStateSerializer,
    ReportQuerySerializer,
    ReverseSerializer,
    TaxRateSerializer,
)


def actor(request: Request) -> User:
    return cast(User, request.user)


def run(call: Any, *args: Any) -> Any:
    try:
        return call(*args)
    except services.AccountingError as exc:
        raise ValidationError({"detail": type(exc).message}) from exc


class AccountingView(APIView):
    permission_classes = [HasModulePermission]
    module = "accounting"
    throttle_scope = "tenancy"


def entries() -> QuerySet[JournalEntry]:
    return JournalEntry.objects.select_related(
        "created_by", "posted_by", "reversed_by"
    ).prefetch_related(Prefetch("lines", queryset=JournalLine.objects.select_related("account")))


class AccountListView(AccountingView, generics.ListCreateAPIView[Account]):
    serializer_class = AccountSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[Account]:
        return Account.objects.order_by("code")

    def perform_create(self, serializer: AccountSerializer) -> None:  # type: ignore[override]
        serializer.instance = run(
            services.save_account, actor(self.request), serializer.validated_data
        )


class AccountDetailView(AccountingView, generics.RetrieveUpdateDestroyAPIView[Account]):
    serializer_class = AccountSerializer
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[Account]:
        return Account.objects.all()

    def perform_update(self, serializer: AccountSerializer) -> None:  # type: ignore[override]
        run(
            services.save_account,
            actor(self.request),
            serializer.validated_data,
            serializer.instance,
        )

    def perform_destroy(self, instance: Account) -> None:
        run(services.delete_account, actor(self.request), instance)


class FiscalYearListView(AccountingView, generics.ListCreateAPIView[FiscalYear]):
    serializer_class = FiscalYearSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[FiscalYear]:
        return FiscalYear.objects.prefetch_related("periods")

    def perform_create(self, serializer: FiscalYearSerializer) -> None:  # type: ignore[override]
        data = serializer.validated_data
        serializer.instance = run(
            services.create_fiscal_year,
            actor(self.request),
            data["start"],
            data["end"],
            data.get("name", ""),
        )


class PeriodDetailView(AccountingView, generics.RetrieveUpdateAPIView[FiscalPeriod]):
    serializer_class = FiscalPeriodSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self) -> QuerySet[FiscalPeriod]:
        return FiscalPeriod.objects.all()

    @extend_schema(request=PeriodStateSerializer, responses=FiscalPeriodSerializer)
    def patch(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        period = self.get_object()
        data = PeriodStateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        period = services.set_period_closed(actor(request), period, data.validated_data["closed"])
        return Response(FiscalPeriodSerializer(period).data)


def _line_inputs(data: list[dict[str, Any]]) -> list[services.LineInput]:
    return [
        services.LineInput(
            line["account"],
            Decimal(line.get("debit") or 0),
            Decimal(line.get("credit") or 0),
            line.get("description", ""),
        )
        for line in data
    ]


@extend_schema(
    parameters=[
        OpenApiParameter("status", str, enum=["draft", "posted"]),
        OpenApiParameter("start", str),
        OpenApiParameter("end", str),
    ]
)
class EntryListView(AccountingView, generics.ListCreateAPIView[JournalEntry]):
    serializer_class = JournalEntrySerializer

    def get_queryset(self) -> QuerySet[JournalEntry]:
        query = entries()
        params = self.request.query_params
        if params.get("status") in JournalEntry.Status.values:
            query = query.filter(status=params["status"])
        filters = ReportQuerySerializer(
            data={k: params[k] for k in ("start", "end") if k in params}
        )
        filters.is_valid(raise_exception=True)
        if "start" in filters.validated_data:
            query = query.filter(date__gte=filters.validated_data["start"])
        if "end" in filters.validated_data:
            query = query.filter(date__lte=filters.validated_data["end"])
        return query

    def perform_create(self, serializer: JournalEntrySerializer) -> None:  # type: ignore[override]
        data = serializer.validated_data
        entry = run(
            services.save_draft,
            actor(self.request),
            data["date"],
            data.get("memo", ""),
            _line_inputs(data["lines"]),
        )
        serializer.instance = entries().get(pk=entry.pk)


class EntryDetailView(AccountingView, generics.RetrieveUpdateDestroyAPIView[JournalEntry]):
    serializer_class = JournalEntrySerializer
    http_method_names = ["get", "put", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[JournalEntry]:
        return entries()

    def perform_update(self, serializer: JournalEntrySerializer) -> None:  # type: ignore[override]
        data = serializer.validated_data
        entry = run(
            services.save_draft,
            actor(self.request),
            data["date"],
            data.get("memo", ""),
            _line_inputs(data["lines"]),
            serializer.instance,
        )
        serializer.instance = entries().get(pk=entry.pk)

    def perform_destroy(self, instance: JournalEntry) -> None:
        run(services.delete_draft, actor(self.request), instance)


class EntryPostView(AccountingView, generics.GenericAPIView[JournalEntry]):
    required_action = "post"

    def get_queryset(self) -> QuerySet[JournalEntry]:
        return JournalEntry.objects.all()

    @extend_schema(request=None, responses=JournalEntrySerializer)
    def post(self, request: Request, pk: int) -> Response:
        entry = run(services.post_entry, actor(request), self.get_object())
        return Response(JournalEntrySerializer(entries().get(pk=entry.pk)).data)


class EntryReverseView(AccountingView, generics.GenericAPIView[JournalEntry]):
    required_action = "post"

    def get_queryset(self) -> QuerySet[JournalEntry]:
        return JournalEntry.objects.all()

    @extend_schema(request=ReverseSerializer, responses={201: JournalEntrySerializer})
    def post(self, request: Request, pk: int) -> Response:
        entry = self.get_object()
        data = ReverseSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        reversal = run(
            services.reverse_entry,
            actor(request),
            entry,
            data.validated_data["date"],
            data.validated_data.get("memo", ""),
        )
        return Response(
            JournalEntrySerializer(entries().get(pk=reversal.pk)).data,
            status=status.HTTP_201_CREATED,
        )


REPORT_PARAMS = [
    OpenApiParameter("start", str),
    OpenApiParameter("end", str),
    OpenApiParameter("export", str, enum=["csv"]),
]


def _report_query(request: Request) -> dict[str, Any]:
    query = ReportQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    return dict(query.validated_data)


class TrialBalanceView(AccountingView):
    @extend_schema(
        parameters=REPORT_PARAMS,
        responses=inline_serializer(
            "TrialBalance",
            {
                "start": serializers.DateField(allow_null=True),
                "end": serializers.DateField(),
                "rows": inline_serializer(
                    "TrialBalanceRow",
                    {
                        "id": serializers.IntegerField(),
                        "code": serializers.CharField(),
                        "name": serializers.CharField(),
                        "type": serializers.CharField(),
                        "debit": serializers.DecimalField(max_digits=18, decimal_places=2),
                        "credit": serializers.DecimalField(max_digits=18, decimal_places=2),
                    },
                    many=True,
                ),
                "total_debit": serializers.DecimalField(max_digits=18, decimal_places=2),
                "total_credit": serializers.DecimalField(max_digits=18, decimal_places=2),
            },
        ),
    )
    def get(self, request: Request) -> Response | HttpResponse:
        query = _report_query(request)
        report = trial_balance(query.get("end", timezone.localdate()), query.get("start"))
        if query.get("export") == "csv":
            rows = [(r.code, r.name, r.type, r.debit, r.credit) for r in report.rows]
            rows.append(("", "Total", "", report.total_debit, report.total_credit))
            return csv_response(
                f"trial-balance-{report.end}.csv",
                ["Code", "Account", "Type", "Debit", "Credit"],
                rows,
            )
        return Response(
            {
                "start": report.start,
                "end": report.end,
                "rows": [
                    {k: str(v) if k in ("debit", "credit") else v for k, v in asdict(r).items()}
                    for r in report.rows
                ],
                "total_debit": str(report.total_debit),
                "total_credit": str(report.total_credit),
            }
        )


class LedgerView(AccountingView, generics.GenericAPIView[Account]):
    def get_queryset(self) -> QuerySet[Account]:
        return Account.objects.all()

    @extend_schema(
        parameters=REPORT_PARAMS,
        responses=inline_serializer(
            "Ledger",
            {
                "account": AccountSerializer(),
                "opening": serializers.DecimalField(max_digits=18, decimal_places=2),
                "closing": serializers.DecimalField(max_digits=18, decimal_places=2),
                "lines": inline_serializer(
                    "LedgerLine",
                    {
                        "entry_id": serializers.IntegerField(),
                        "number": serializers.CharField(),
                        "date": serializers.DateField(),
                        "memo": serializers.CharField(),
                        "description": serializers.CharField(),
                        "debit": serializers.DecimalField(max_digits=18, decimal_places=2),
                        "credit": serializers.DecimalField(max_digits=18, decimal_places=2),
                        "balance": serializers.DecimalField(max_digits=18, decimal_places=2),
                    },
                    many=True,
                ),
            },
        ),
    )
    def get(self, request: Request, pk: int) -> Response | HttpResponse:
        query = _report_query(request)
        ledger = general_ledger(self.get_object(), query.get("start"), query.get("end"))
        if query.get("export") == "csv":
            rows: list[tuple[object, ...]] = [
                ("", "", "Opening balance", "", "", "", ledger.opening)
            ]
            rows += [
                (
                    line.date,
                    line.number,
                    line.memo,
                    line.description,
                    line.debit,
                    line.credit,
                    line.balance,
                )
                for line in ledger.lines
            ]
            return csv_response(
                f"ledger-{ledger.account.code}.csv",
                ["Date", "Number", "Memo", "Description", "Debit", "Credit", "Balance"],
                rows,
            )
        money = ("debit", "credit", "balance")
        return Response(
            {
                "account": AccountSerializer(ledger.account).data,
                "opening": str(ledger.opening),
                "closing": str(ledger.closing),
                "lines": [
                    {k: str(v) if k in money else v for k, v in asdict(ln).items()}
                    for ln in ledger.lines
                ],
            }
        )


class TaxRateListView(AccountingView, generics.ListCreateAPIView[TaxRate]):
    serializer_class = TaxRateSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[TaxRate]:
        return TaxRate.objects.all()

    def perform_create(self, serializer: TaxRateSerializer) -> None:  # type: ignore[override]
        serializer.instance = services.save_tax_rate(
            actor(self.request), TaxRate(), serializer.validated_data
        )


class TaxRateDetailView(AccountingView, generics.RetrieveUpdateDestroyAPIView[TaxRate]):
    serializer_class = TaxRateSerializer
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[TaxRate]:
        return TaxRate.objects.all()

    def perform_update(self, serializer: TaxRateSerializer) -> None:  # type: ignore[override]
        serializer.instance = services.save_tax_rate(
            actor(self.request), cast(TaxRate, serializer.instance), serializer.validated_data
        )

    def perform_destroy(self, instance: TaxRate) -> None:
        run(services.delete_tax_rate, actor(self.request), instance)
