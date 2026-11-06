from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from django.db.models import DecimalField, F, OuterRef, Prefetch, Q, QuerySet, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounting.services import AccountingError
from apps.accounts.models import User
from apps.inventory.services import InventoryError
from apps.tenancy.permissions import HasModulePermission

from . import services
from .models import (
    Bill,
    BillLine,
    GoodsReceipt,
    GoodsReceiptLine,
    PaymentAllocation,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierPayment,
)
from .serializers import (
    BillSerializer,
    DateSerializer,
    GoodsReceiptSerializer,
    PurchaseOrderSerializer,
    SupplierPaymentSerializer,
    SupplierSerializer,
)


def actor(request: Request) -> User:
    return cast(User, request.user)


def run(call: Any, *args: Any) -> Any:
    try:
        return call(*args)
    except (services.PurchasingError, InventoryError, AccountingError) as exc:
        raise ValidationError({"detail": type(exc).message}) from exc


class PurchasingView(APIView):
    permission_classes = [HasModulePermission]
    module = "purchasing"
    throttle_scope = "tenancy"


# Suppliers


def suppliers() -> QuerySet[Supplier]:
    owed = (
        Bill.objects.filter(supplier=OuterRef("pk"), status=Bill.Status.POSTED)
        .values("supplier")
        .annotate(total=Sum(F("total") - F("amount_paid")))
        .values("total")
    )
    # Money paid beyond the bills it was allocated to stays with the supplier as an advance,
    # and comes off what we owe them, so a balance can go below zero.
    paid = (
        SupplierPayment.objects.filter(
            supplier=OuterRef("pk"), status=SupplierPayment.Status.POSTED
        )
        .values("supplier")
        .annotate(total=Sum("amount"))
        .values("total")
    )
    allocated = (
        PaymentAllocation.objects.filter(
            payment__supplier=OuterRef("pk"), payment__status=SupplierPayment.Status.POSTED
        )
        .values("payment__supplier")
        .annotate(total=Sum("amount"))
        .values("total")
    )
    money: DecimalField[Decimal, Decimal] = DecimalField()
    query: QuerySet[Supplier] = Supplier.objects.annotate(
        balance=Coalesce(Subquery(owed), Decimal(0), output_field=money)
        - Coalesce(Subquery(paid), Decimal(0), output_field=money)
        + Coalesce(Subquery(allocated), Decimal(0), output_field=money)
    )
    return query


@extend_schema(parameters=[OpenApiParameter("q", str)])
class SupplierListView(PurchasingView, generics.ListCreateAPIView[Supplier]):
    serializer_class = SupplierSerializer

    def get_queryset(self) -> QuerySet[Supplier]:
        query = suppliers()
        if term := self.request.query_params.get("q", "").strip()[:80]:
            query = query.filter(Q(name__icontains=term) | Q(code__icontains=term))
        return query

    def perform_create(self, serializer: SupplierSerializer) -> None:  # type: ignore[override]
        created = run(
            services.save_supplier, actor(self.request), Supplier(), serializer.validated_data
        )
        serializer.instance = suppliers().get(pk=created.pk)


class SupplierDetailView(PurchasingView, generics.RetrieveUpdateDestroyAPIView[Supplier]):
    serializer_class = SupplierSerializer
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[Supplier]:
        return suppliers()

    def perform_update(self, serializer: SupplierSerializer) -> None:  # type: ignore[override]
        supplier = cast(Supplier, serializer.instance)
        run(services.save_supplier, actor(self.request), supplier, serializer.validated_data)
        serializer.instance = suppliers().get(pk=supplier.pk)

    def perform_destroy(self, instance: Supplier) -> None:
        run(services.delete_supplier, actor(self.request), instance)


# Documents


@dataclass(frozen=True)
class Kind:
    """How the generic document views load, save and post one kind of document."""

    model: Any
    serializer: Any
    queryset: Callable[[], QuerySet[Any]]
    save: Callable[..., Any]
    header: tuple[str, ...]
    lines_key: str
    line: Callable[[dict[str, Any]], Any]
    post: Callable[[User, Any], Any] | None = None


def _queryset(model: Any, lines: str, line_model: Any, *related: str) -> Callable[[], Any]:
    def build() -> QuerySet[Any]:
        return cast(
            QuerySet[Any],
            model.objects.select_related("supplier", "created_by").prefetch_related(
                Prefetch(lines, queryset=line_model.objects.select_related(*related))
            ),
        )

    return build


ORDER = Kind(
    PurchaseOrder,
    PurchaseOrderSerializer,
    _queryset(PurchaseOrder, "lines", PurchaseOrderLine, "product", "unit"),
    services.save_order,
    ("supplier", "date", "expected_date", "warehouse", "memo"),
    "lines",
    lambda d: services.OrderLineInput(d["product"], d["unit"], d["quantity"], d["unit_price"]),
    services.confirm_order,
)
RECEIPT = Kind(
    GoodsReceipt,
    GoodsReceiptSerializer,
    _queryset(GoodsReceipt, "lines", GoodsReceiptLine, "product", "unit"),
    services.save_receipt,
    ("supplier", "purchase_order", "date", "warehouse", "memo"),
    "lines",
    lambda d: services.ReceiptLineInput(
        d["product"],
        d["unit"],
        d["quantity"],
        d["unit_cost"],
        d.get("order_line"),
        d.get("batch_number", ""),
        d.get("expiry_date"),
    ),
    services.post_receipt,
)
BILL = Kind(
    Bill,
    BillSerializer,
    _queryset(Bill, "lines", BillLine, "account"),
    services.save_bill,
    ("supplier", "supplier_reference", "date", "due_date", "memo"),
    "lines",
    lambda d: services.BillLineInput(
        d["quantity"],
        d["unit_price"],
        d.get("receipt_line"),
        d.get("account"),
        d.get("description", ""),
        d.get("tax_amount", Decimal(0)),
    ),
    services.post_bill,
)
PAYMENT = Kind(
    SupplierPayment,
    SupplierPaymentSerializer,
    _queryset(SupplierPayment, "allocations", PaymentAllocation, "bill"),
    services.save_payment,
    ("supplier", "date", "amount", "paid_from", "reference", "memo"),
    "allocations",
    lambda d: services.AllocationInput(d["bill"], d["amount"]),
    services.post_payment,
)


def _save(kind: Kind, request: Request, data: dict[str, Any], instance: Any = None) -> Any:
    header = {key: data[key] for key in kind.header if key in data}
    lines = [kind.line(line) for line in data.get(kind.lines_key, [])]
    saved = run(kind.save, actor(request), header, lines, *([instance] if instance else []))
    return kind.queryset().get(pk=saved.pk)


def document_views(kind: Kind) -> tuple[type[Any], type[Any], type[Any]]:
    @extend_schema(parameters=[OpenApiParameter("status", str), OpenApiParameter("supplier", int)])
    class ListView(PurchasingView, generics.ListCreateAPIView[Any]):
        serializer_class = kind.serializer

        def get_queryset(self) -> QuerySet[Any]:
            query = kind.queryset()
            params = self.request.query_params
            if status := params.get("status", "")[:12]:
                query = query.filter(status=status)
            if params.get("supplier", "").isdigit():
                query = query.filter(supplier_id=params["supplier"])
            return query

        def perform_create(self, serializer: Any) -> None:
            serializer.instance = _save(kind, self.request, serializer.validated_data)

    class DetailView(PurchasingView, generics.RetrieveUpdateDestroyAPIView[Any]):
        serializer_class = kind.serializer
        http_method_names = ["get", "put", "delete", "head", "options"]

        def get_queryset(self) -> QuerySet[Any]:
            return kind.queryset()

        def perform_update(self, serializer: Any) -> None:
            serializer.instance = _save(
                kind, self.request, serializer.validated_data, serializer.instance
            )

        def perform_destroy(self, instance: Any) -> None:
            run(services.delete_draft, actor(self.request), instance)

    class PostView(PurchasingView, generics.GenericAPIView[Any]):
        required_action = "post"

        def get_queryset(self) -> QuerySet[Any]:
            return cast(QuerySet[Any], kind.model.objects.all())

        @extend_schema(request=None, responses=kind.serializer)
        def post(self, request: Request, pk: int) -> Response:
            document = run(kind.post, actor(request), self.get_object())
            return Response(kind.serializer(kind.queryset().get(pk=document.pk)).data)

    name = kind.model.__name__
    for view, suffix in ((ListView, "List"), (DetailView, "Detail"), (PostView, "Post")):
        view.__name__ = view.__qualname__ = f"{name}{suffix}View"
    return ListView, DetailView, PostView


OrderListView, OrderDetailView, OrderConfirmView = document_views(ORDER)
ReceiptListView, ReceiptDetailView, ReceiptPostView = document_views(RECEIPT)
BillListView, BillDetailView, BillPostView = document_views(BILL)
PaymentListView, PaymentDetailView, PaymentPostView = document_views(PAYMENT)


class OrderCloseView(PurchasingView, generics.GenericAPIView[PurchaseOrder]):
    required_action = "update"

    def get_queryset(self) -> QuerySet[PurchaseOrder]:
        return PurchaseOrder.objects.all()

    @extend_schema(request=None, responses=PurchaseOrderSerializer)
    def post(self, request: Request, pk: int) -> Response:
        order = run(services.close_order, actor(request), self.get_object())
        return Response(PurchaseOrderSerializer(ORDER.queryset().get(pk=order.pk)).data)


def _on(request: Request) -> Any:
    body = DateSerializer(data=request.data)
    body.is_valid(raise_exception=True)
    return body.validated_data.get("date") or timezone.localdate()


class OrderReceiveView(PurchasingView, generics.GenericAPIView[PurchaseOrder]):
    """Start a goods receipt for everything still outstanding on the order."""

    required_action = "create"

    def get_queryset(self) -> QuerySet[PurchaseOrder]:
        return PurchaseOrder.objects.select_related("supplier", "warehouse")

    @extend_schema(request=DateSerializer, responses={201: GoodsReceiptSerializer})
    def post(self, request: Request, pk: int) -> Response:
        receipt = run(services.receive_order, actor(request), self.get_object(), _on(request))
        return Response(GoodsReceiptSerializer(RECEIPT.queryset().get(pk=receipt.pk)).data, 201)


class ReceiptBillView(PurchasingView, generics.GenericAPIView[GoodsReceipt]):
    """Start a supplier bill for whatever of the receipt isn't billed yet."""

    required_action = "create"

    def get_queryset(self) -> QuerySet[GoodsReceipt]:
        return GoodsReceipt.objects.select_related("supplier")

    @extend_schema(request=DateSerializer, responses={201: BillSerializer})
    def post(self, request: Request, pk: int) -> Response:
        bill = run(services.bill_receipt, actor(request), self.get_object(), _on(request))
        return Response(BillSerializer(BILL.queryset().get(pk=bill.pk)).data, 201)
