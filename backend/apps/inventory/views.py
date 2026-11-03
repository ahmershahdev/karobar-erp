from typing import Any, cast

from django.db.models import Count, DecimalField, Exists, OuterRef, Prefetch, Q, QuerySet, Sum
from django.db.models.functions import Coalesce
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import generics, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounting.services import AccountingError
from apps.accounts.models import User
from apps.core.money import quantize_money
from apps.tenancy.permissions import HasModulePermission

from . import services
from .models import (
    Batch,
    Category,
    Product,
    ProductUnit,
    StockEntry,
    StockEntryLine,
    StockLevel,
    StockMove,
    Unit,
    Warehouse,
)
from .serializers import (
    AlertsSerializer,
    BatchSerializer,
    CategorySerializer,
    ProductSerializer,
    StockEntrySerializer,
    StockLevelSerializer,
    StockMoveSerializer,
    UnitSerializer,
    WarehouseSerializer,
)


def actor(request: Request) -> User:
    return cast(User, request.user)


def run(call: Any, *args: Any) -> Any:
    try:
        return call(*args)
    except (services.InventoryError, AccountingError) as exc:
        raise ValidationError({"detail": type(exc).message}) from exc


class InventoryView(APIView):
    permission_classes = [HasModulePermission]
    module = "inventory"
    throttle_scope = "tenancy"


def master_views(model: Any, serializer: Any) -> tuple[type[Any], type[Any]]:
    """List/create and detail views for a simple master table, audited through the service."""

    class ListView(InventoryView, generics.ListCreateAPIView[Any]):
        serializer_class = serializer
        pagination_class = None

        def get_queryset(self) -> QuerySet[Any]:
            return cast(QuerySet[Any], model.objects.all())

        def perform_create(self, ser: Any) -> None:
            ser.instance = run(
                services.save_master, actor(self.request), model(), ser.validated_data
            )

    class DetailView(InventoryView, generics.RetrieveUpdateDestroyAPIView[Any]):
        serializer_class = serializer
        http_method_names = ["get", "patch", "delete", "head", "options"]

        def get_queryset(self) -> QuerySet[Any]:
            return cast(QuerySet[Any], model.objects.all())

        def perform_update(self, ser: Any) -> None:
            run(services.save_master, actor(self.request), ser.instance, ser.validated_data)

        def perform_destroy(self, instance: Any) -> None:
            run(services.delete_master, actor(self.request), instance)

    ListView.__name__ = f"{model.__name__}ListView"
    DetailView.__name__ = f"{model.__name__}DetailView"
    return ListView, DetailView


UnitListView, UnitDetailView = master_views(Unit, UnitSerializer)
CategoryListView, CategoryDetailView = master_views(Category, CategorySerializer)
WarehouseListView, WarehouseDetailView = master_views(Warehouse, WarehouseSerializer)


def products() -> QuerySet[Product]:
    query: QuerySet[Product] = (
        Product.objects.select_related("unit")
        .prefetch_related(Prefetch("packs", queryset=ProductUnit.objects.select_related("unit")))
        .annotate(on_hand=Coalesce(Sum("levels__quantity"), 0, output_field=DecimalField()))
    )
    return query


def _has_barcode(code: str) -> Exists:
    return Exists(ProductUnit.objects.filter(product=OuterRef("pk"), barcode=code))


def _packs(data: list[dict[str, Any]] | None) -> list[services.PackInput] | None:
    if data is None:
        return None
    return [services.PackInput(p["unit"], p["factor"], p.get("barcode") or None) for p in data]


@extend_schema(parameters=[OpenApiParameter("q", str), OpenApiParameter("barcode", str)])
class ProductListView(InventoryView, generics.ListCreateAPIView[Product]):
    serializer_class = ProductSerializer

    def get_queryset(self) -> QuerySet[Product]:
        query = products()
        params = self.request.query_params
        # Barcodes are matched with Exists, not a join: joining packs would repeat each stock
        # level once per pack and multiply on_hand.
        if barcode := params.get("barcode", "").strip()[:64]:
            query = query.filter(_has_barcode(barcode))
        if term := params.get("q", "").strip()[:80]:
            # One box for names, SKUs and scanned barcodes: no guessing which one was typed.
            query = query.filter(
                Q(name__icontains=term) | Q(sku__icontains=term) | _has_barcode(term)
            )
        return query

    def perform_create(self, serializer: ProductSerializer) -> None:  # type: ignore[override]
        data = dict(serializer.validated_data)
        packs = _packs(data.pop("packs", None))
        product = run(services.save_product, actor(self.request), data, packs)
        serializer.instance = products().get(pk=product.pk)


class ProductDetailView(InventoryView, generics.RetrieveUpdateDestroyAPIView[Product]):
    serializer_class = ProductSerializer
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[Product]:
        return products()

    def perform_update(self, serializer: ProductSerializer) -> None:  # type: ignore[override]
        data = dict(serializer.validated_data)
        packs = _packs(data.pop("packs", None))
        run(services.save_product, actor(self.request), data, packs, serializer.instance)
        serializer.instance = products().get(pk=cast(Product, serializer.instance).pk)

    def perform_destroy(self, instance: Product) -> None:
        run(services.delete_master, actor(self.request), instance)


@extend_schema(parameters=[OpenApiParameter("product", int)])
class BatchListView(InventoryView, generics.ListAPIView[Batch]):
    serializer_class = BatchSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[Batch]:
        query = Batch.objects.all()
        product = self.request.query_params.get("product", "")
        return query.filter(product_id=product) if product.isdigit() else query


@extend_schema(parameters=[OpenApiParameter("warehouse", int), OpenApiParameter("product", int)])
class StockLevelListView(InventoryView, generics.ListAPIView[StockLevel]):
    serializer_class = StockLevelSerializer

    def get_queryset(self) -> QuerySet[StockLevel]:
        return _levels(self.request)


def _levels(request: Request) -> QuerySet[StockLevel]:
    query = StockLevel.objects.select_related("product", "product__unit", "warehouse").exclude(
        quantity=0
    )
    for field in ("warehouse", "product"):
        value = request.query_params.get(field, "")
        if value.isdigit():
            query = query.filter(**{f"{field}_id": value})
    return query


@extend_schema(parameters=[OpenApiParameter("warehouse", int)])
class StockValueView(InventoryView):
    @extend_schema(
        responses=inline_serializer(
            "StockValue",
            {
                "total_value": serializers.DecimalField(max_digits=18, decimal_places=2),
                "lines": serializers.IntegerField(),
            },
        )
    )
    def get(self, request: Request) -> Response:
        totals = _levels(request).aggregate(total=Sum("value"), lines=Count("id"))
        return Response(
            {"total_value": str(quantize_money(totals["total"] or 0)), "lines": totals["lines"]}
        )


class ProductMovesView(InventoryView, generics.ListAPIView[StockMove]):
    serializer_class = StockMoveSerializer

    def get_queryset(self) -> QuerySet[StockMove]:
        product = generics.get_object_or_404(Product.objects.all(), pk=self.kwargs["pk"])
        return StockMove.objects.filter(product=product).select_related(
            "entry", "warehouse", "batch"
        )


def entries() -> QuerySet[StockEntry]:
    return StockEntry.objects.select_related("journal_entry", "created_by").prefetch_related(
        Prefetch("lines", queryset=StockEntryLine.objects.select_related("product", "unit"))
    )


def _lines(data: list[dict[str, Any]]) -> list[services.LineInput]:
    return [
        services.LineInput(
            line["product"],
            line["unit"],
            line["quantity"],
            line.get("unit_cost"),
            line.get("batch_number", ""),
            line.get("expiry_date"),
        )
        for line in data
    ]


def _header(data: dict[str, Any]) -> dict[str, Any]:
    return {
        k: data[k]
        for k in ("kind", "date", "memo", "warehouse", "to_warehouse", "contra_account")
        if k in data
    }


@extend_schema(parameters=[OpenApiParameter("kind", str), OpenApiParameter("status", str)])
class StockEntryListView(InventoryView, generics.ListCreateAPIView[StockEntry]):
    serializer_class = StockEntrySerializer

    def get_queryset(self) -> QuerySet[StockEntry]:
        query = entries()
        params = self.request.query_params
        if params.get("kind") in StockEntry.Kind.values:
            query = query.filter(kind=params["kind"])
        if params.get("status") in StockEntry.Status.values:
            query = query.filter(status=params["status"])
        return query

    def perform_create(self, serializer: StockEntrySerializer) -> None:  # type: ignore[override]
        data = serializer.validated_data
        entry = run(services.save_draft, actor(self.request), _header(data), _lines(data["lines"]))
        serializer.instance = entries().get(pk=entry.pk)


class StockEntryDetailView(InventoryView, generics.RetrieveUpdateDestroyAPIView[StockEntry]):
    serializer_class = StockEntrySerializer
    http_method_names = ["get", "put", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[StockEntry]:
        return entries()

    def perform_update(self, serializer: StockEntrySerializer) -> None:  # type: ignore[override]
        data = serializer.validated_data
        entry = run(
            services.save_draft,
            actor(self.request),
            _header(data),
            _lines(data["lines"]),
            serializer.instance,
        )
        serializer.instance = entries().get(pk=entry.pk)

    def perform_destroy(self, instance: StockEntry) -> None:
        run(services.delete_draft, actor(self.request), instance)


class StockEntryPostView(InventoryView, generics.GenericAPIView[StockEntry]):
    required_action = "post"

    def get_queryset(self) -> QuerySet[StockEntry]:
        return StockEntry.objects.all()

    @extend_schema(request=None, responses=StockEntrySerializer)
    def post(self, request: Request, pk: int) -> Response:
        entry = run(services.post_entry, actor(request), self.get_object())
        return Response(StockEntrySerializer(entries().get(pk=entry.pk)).data)


class AlertsView(InventoryView):
    @extend_schema(responses=AlertsSerializer)
    def get(self, request: Request) -> Response:
        return Response(
            {
                "low_stock": [
                    {
                        "product": row.product.pk,
                        "sku": row.product.sku,
                        "name": row.product.name,
                        "on_hand": str(row.on_hand),
                        "reorder_level": str(row.product.reorder_level),
                    }
                    for row in services.low_stock()
                ],
                "expiring": [
                    {
                        "batch": row.batch.pk,
                        "product": row.batch.product.name,
                        "number": row.batch.number,
                        "warehouse": row.warehouse.code,
                        "quantity": str(row.quantity),
                        "expiry_date": str(row.batch.expiry_date),
                    }
                    for row in services.expiring(30)
                ],
            }
        )
