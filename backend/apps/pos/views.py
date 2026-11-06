from typing import Any, cast

from django.db.models import QuerySet
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounting.models import TaxRate
from apps.accounting.serializers import TaxRateSerializer
from apps.accounting.services import AccountingError
from apps.accounts.models import User
from apps.inventory.models import Warehouse
from apps.inventory.services import InventoryError
from apps.sales import documents
from apps.sales.services import SalesError
from apps.sales.views import LANGUAGE, PDF, pdf_response
from apps.tenancy.permissions import HasModulePermission

from . import services
from .models import PosSale, PosSession
from .serializers import (
    CloseTillSerializer,
    FoundProductSerializer,
    OpenTillSerializer,
    PosWarehouseSerializer,
    SaleRequestSerializer,
    SaleResultSerializer,
    TillSerializer,
)


def actor(request: Request) -> User:
    return cast(User, request.user)


def run(call: Any, *args: Any) -> Any:
    try:
        return call(*args)
    except (services.PosError, SalesError, InventoryError, AccountingError) as exc:
        raise ValidationError({"detail": type(exc).message}) from exc


class PosView(APIView):
    permission_classes = [HasModulePermission]
    module = "pos"
    throttle_scope = "tenancy"


def session_data(session: PosSession) -> Any:
    for key, value in services.takings(session).items():
        setattr(session, key, value)
    return TillSerializer(session).data


class SessionListView(PosView, generics.GenericAPIView[PosSession]):
    pagination_class = None

    def get_queryset(self) -> QuerySet[PosSession]:
        return PosSession.objects.select_related("warehouse", "opened_by")

    @extend_schema(
        parameters=[OpenApiParameter("status", str)], responses=TillSerializer(many=True)
    )
    def get(self, request: Request) -> Response:
        query = self.get_queryset()
        if status := request.query_params.get("status", "")[:10]:
            query = query.filter(status=status)
        return Response([session_data(session) for session in query[:50]])

    @extend_schema(request=OpenTillSerializer, responses={201: TillSerializer})
    def post(self, request: Request) -> Response:
        body = OpenTillSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        session = run(
            services.open_till,
            actor(request),
            body.validated_data["warehouse"],
            body.validated_data["opening_float"],
        )
        return Response(session_data(self.get_queryset().get(pk=session.pk)), 201)


class SessionDetailView(PosView, generics.GenericAPIView[PosSession]):
    def get_queryset(self) -> QuerySet[PosSession]:
        return PosSession.objects.select_related("warehouse", "opened_by")

    @extend_schema(responses=TillSerializer)
    def get(self, request: Request, pk: int) -> Response:
        return Response(session_data(self.get_object()))


class SaleView(PosView, generics.GenericAPIView[PosSession]):
    required_action = "create"

    def get_queryset(self) -> QuerySet[PosSession]:
        return PosSession.objects.all()

    @extend_schema(request=SaleRequestSerializer, responses={201: SaleResultSerializer})
    def post(self, request: Request, pk: int) -> Response:
        session = self.get_object()
        body = SaleRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        sale = run(
            services.sell,
            actor(request),
            session,
            [
                services.CartLine(line["product"], line["unit"], line["quantity"])
                for line in data["lines"]
            ],
            data["method"],
            data.get("tendered"),
            data.get("tax_rate"),
        )
        return Response(SaleResultSerializer(sale).data, 201)


class CloseTillView(PosView, generics.GenericAPIView[PosSession]):
    required_action = "post"

    def get_queryset(self) -> QuerySet[PosSession]:
        return PosSession.objects.select_related("warehouse", "opened_by")

    @extend_schema(request=CloseTillSerializer, responses=TillSerializer)
    def post(self, request: Request, pk: int) -> Response:
        session = self.get_object()
        body = CloseTillSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        closed = run(
            services.close_till, actor(request), session, body.validated_data["counted_cash"]
        )
        return Response(session_data(self.get_queryset().get(pk=closed.pk)))


class ProductSearchView(PosView):
    @extend_schema(
        parameters=[OpenApiParameter("q", str)], responses=FoundProductSerializer(many=True)
    )
    def get(self, request: Request) -> Response:
        term = request.query_params.get("q", "").strip()[:80]
        found = services.find_products(term) if term else []
        return Response(FoundProductSerializer(found, many=True).data)


class PosWarehouseListView(PosView, generics.ListAPIView[Warehouse]):
    serializer_class = PosWarehouseSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[Warehouse]:
        return Warehouse.objects.all()


class PosTaxRateListView(PosView, generics.ListAPIView[TaxRate]):
    serializer_class = TaxRateSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[TaxRate]:
        return TaxRate.objects.all()


class SaleReceiptView(PosView, generics.GenericAPIView[PosSale]):
    def get_queryset(self) -> QuerySet[PosSale]:
        return PosSale.objects.select_related("invoice__customer")

    @extend_schema(parameters=[LANGUAGE], responses=PDF)
    def get(self, request: Request, pk: int) -> HttpResponse:
        return pdf_response(request, documents.invoice_html, self.get_object().invoice)
