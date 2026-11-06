from datetime import date

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenancy.permissions import HasModulePermission

from . import services
from .serializers import (
    BalanceSheetSerializer,
    CashFlowSerializer,
    DashboardSerializer,
    HomeSerializer,
    PeriodSerializer,
    ProfitLossSerializer,
    SalesTaxSerializer,
)


class ReportView(APIView):
    permission_classes = [HasModulePermission]
    module = "reports"
    throttle_scope = "tenancy"


def period(request: Request) -> tuple[date, date]:
    """The dates asked for; without them, this month so far."""
    query = PeriodSerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    end = query.validated_data.get("end") or timezone.localdate()
    return query.validated_data.get("start") or end.replace(day=1), end


class ProfitLossView(ReportView):
    @extend_schema(parameters=[PeriodSerializer], responses=ProfitLossSerializer)
    def get(self, request: Request) -> Response:
        return Response(ProfitLossSerializer(services.profit_loss(*period(request))).data)


class BalanceSheetView(ReportView):
    @extend_schema(parameters=[PeriodSerializer], responses=BalanceSheetSerializer)
    def get(self, request: Request) -> Response:
        _, end = period(request)
        return Response(BalanceSheetSerializer(services.position(end)).data)


class CashFlowView(ReportView):
    @extend_schema(parameters=[PeriodSerializer], responses=CashFlowSerializer)
    def get(self, request: Request) -> Response:
        return Response(CashFlowSerializer(services.cash_flow(*period(request))).data)


class SalesTaxView(ReportView):
    @extend_schema(parameters=[PeriodSerializer], responses=SalesTaxSerializer)
    def get(self, request: Request) -> Response:
        return Response(SalesTaxSerializer(services.sales_tax(*period(request))).data)


class HomeView(ReportView):
    @extend_schema(responses=HomeSerializer)
    def get(self, request: Request) -> Response:
        return Response(HomeSerializer(services.home(timezone.localdate())).data)


class DashboardView(ReportView):
    @extend_schema(responses=DashboardSerializer)
    def get(self, request: Request) -> Response:
        return Response(DashboardSerializer(services.dashboard(timezone.localdate())).data)
