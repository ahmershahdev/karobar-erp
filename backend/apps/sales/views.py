from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from django.db.models import Prefetch, Q, QuerySet
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
from apps.purchasing.serializers import DateSerializer
from apps.tenancy.permissions import HasModulePermission

from . import services
from .models import (
    CreditNote,
    CreditNoteLine,
    Customer,
    CustomerReceipt,
    Invoice,
    InvoiceLine,
    ReceiptAllocation,
    SalesOrder,
    SalesOrderLine,
)
from .serializers import (
    CreditNoteSerializer,
    CustomerReceiptSerializer,
    CustomerSerializer,
    InvoiceSerializer,
    SalesOrderSerializer,
)


def actor(request: Request) -> User:
    return cast(User, request.user)


def run(call: Any, *args: Any) -> Any:
    try:
        return call(*args)
    except (services.SalesError, InventoryError, AccountingError) as exc:
        raise ValidationError({"detail": type(exc).message}) from exc


class SalesView(APIView):
    permission_classes = [HasModulePermission]
    module = "sales"
    throttle_scope = "tenancy"


@extend_schema(parameters=[OpenApiParameter("q", str)])
class CustomerListView(SalesView, generics.ListCreateAPIView[Customer]):
    serializer_class = CustomerSerializer

    def get_queryset(self) -> QuerySet[Customer]:
        query = services.customers()
        if term := self.request.query_params.get("q", "").strip()[:80]:
            query = query.filter(
                Q(name__icontains=term) | Q(code__icontains=term) | Q(phone__icontains=term)
            )
        return query

    def perform_create(self, serializer: CustomerSerializer) -> None:  # type: ignore[override]
        created = run(
            services.save_customer, actor(self.request), Customer(), serializer.validated_data
        )
        serializer.instance = services.customers().get(pk=created.pk)


class CustomerDetailView(SalesView, generics.RetrieveUpdateDestroyAPIView[Customer]):
    serializer_class = CustomerSerializer
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[Customer]:
        return services.customers()

    def perform_update(self, serializer: CustomerSerializer) -> None:  # type: ignore[override]
        customer = cast(Customer, serializer.instance)
        run(services.save_customer, actor(self.request), customer, serializer.validated_data)
        serializer.instance = services.customers().get(pk=customer.pk)

    def perform_destroy(self, instance: Customer) -> None:
        run(services.delete_customer, actor(self.request), instance)


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
    post: Callable[[User, Any], Any]


def _queryset(model: Any, lines: str, line_model: Any, *related: str) -> Callable[[], Any]:
    def build() -> QuerySet[Any]:
        return cast(
            QuerySet[Any],
            model.objects.select_related("customer", "created_by").prefetch_related(
                Prefetch(lines, queryset=line_model.objects.select_related(*related))
            ),
        )

    return build


ZERO = Decimal(0)
ORDER = Kind(
    SalesOrder,
    SalesOrderSerializer,
    _queryset(SalesOrder, "lines", SalesOrderLine, "product", "unit"),
    services.save_order,
    ("customer", "date", "valid_until", "warehouse", "memo"),
    "lines",
    lambda d: services.OrderLineInput(
        d["product"], d["unit"], d["quantity"], d["unit_price"], d.get("tax_amount", ZERO)
    ),
    services.confirm_order,
)
INVOICE = Kind(
    Invoice,
    InvoiceSerializer,
    _queryset(Invoice, "lines", InvoiceLine, "product", "unit"),
    services.save_invoice,
    ("customer", "order", "date", "due_date", "warehouse", "memo"),
    "lines",
    lambda d: services.InvoiceLineInput(
        d["product"],
        d["unit"],
        d["quantity"],
        d["unit_price"],
        d.get("tax_amount", ZERO),
        d.get("order_line"),
        d.get("batch_number", ""),
    ),
    services.post_invoice,
)
RECEIPT = Kind(
    CustomerReceipt,
    CustomerReceiptSerializer,
    _queryset(CustomerReceipt, "allocations", ReceiptAllocation, "invoice"),
    services.save_receipt,
    ("customer", "date", "amount", "received_into", "reference", "memo"),
    "allocations",
    lambda d: services.AllocationInput(d["invoice"], d["amount"]),
    services.post_receipt,
)
CREDIT = Kind(
    CreditNote,
    CreditNoteSerializer,
    _queryset(CreditNote, "lines", CreditNoteLine, "invoice_line__product"),
    services.save_credit_note,
    ("invoice", "date", "memo"),
    "lines",
    lambda d: services.CreditLineInput(d["invoice_line"], d["quantity"]),
    services.post_credit_note,
)


def _save(kind: Kind, request: Request, data: dict[str, Any], instance: Any = None) -> Any:
    header = {key: data[key] for key in kind.header if key in data}
    lines = [kind.line(line) for line in data.get(kind.lines_key, [])]
    saved = run(kind.save, actor(request), header, lines, *([instance] if instance else []))
    return kind.queryset().get(pk=saved.pk)


def document_views(kind: Kind) -> tuple[type[Any], type[Any], type[Any]]:
    @extend_schema(parameters=[OpenApiParameter("status", str), OpenApiParameter("customer", int)])
    class ListView(SalesView, generics.ListCreateAPIView[Any]):
        serializer_class = kind.serializer

        def get_queryset(self) -> QuerySet[Any]:
            query = kind.queryset()
            params = self.request.query_params
            if status := params.get("status", "")[:12]:
                query = query.filter(status=status)
            if params.get("customer", "").isdigit():
                query = query.filter(customer_id=params["customer"])
            return query

        def perform_create(self, serializer: Any) -> None:
            serializer.instance = _save(kind, self.request, serializer.validated_data)

    class DetailView(SalesView, generics.RetrieveUpdateDestroyAPIView[Any]):
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

    class PostView(SalesView, generics.GenericAPIView[Any]):
        required_action = "post"

        def get_queryset(self) -> QuerySet[Any]:
            return cast(QuerySet[Any], kind.model.objects.all())

        @extend_schema(request=None, responses=kind.serializer)
        def post(self, request: Request, pk: int) -> Response:
            document = run(kind.post, actor(request), self.get_object())
            return Response(kind.serializer(kind.queryset().get(pk=document.pk)).data)

    name = f"Sales{kind.model.__name__}"
    for view, suffix in ((ListView, "List"), (DetailView, "Detail"), (PostView, "Post")):
        view.__name__ = view.__qualname__ = f"{name}{suffix}View"
    return ListView, DetailView, PostView


OrderListView, OrderDetailView, OrderConfirmView = document_views(ORDER)
InvoiceListView, InvoiceDetailView, InvoicePostView = document_views(INVOICE)
ReceiptListView, ReceiptDetailView, ReceiptPostView = document_views(RECEIPT)
CreditListView, CreditDetailView, CreditPostView = document_views(CREDIT)


def _on(request: Request) -> Any:
    body = DateSerializer(data=request.data)
    body.is_valid(raise_exception=True)
    return body.validated_data.get("date") or timezone.localdate()


class OrderQuoteView(SalesView, generics.GenericAPIView[SalesOrder]):
    required_action = "update"

    def get_queryset(self) -> QuerySet[SalesOrder]:
        return SalesOrder.objects.all()

    @extend_schema(request=None, responses=SalesOrderSerializer)
    def post(self, request: Request, pk: int) -> Response:
        order = run(services.quote_order, actor(request), self.get_object())
        return Response(SalesOrderSerializer(ORDER.queryset().get(pk=order.pk)).data)


class OrderCloseView(SalesView, generics.GenericAPIView[SalesOrder]):
    required_action = "update"

    def get_queryset(self) -> QuerySet[SalesOrder]:
        return SalesOrder.objects.all()

    @extend_schema(request=None, responses=SalesOrderSerializer)
    def post(self, request: Request, pk: int) -> Response:
        order = run(services.close_order, actor(request), self.get_object())
        return Response(SalesOrderSerializer(ORDER.queryset().get(pk=order.pk)).data)


class OrderInvoiceView(SalesView, generics.GenericAPIView[SalesOrder]):
    """Start an invoice for everything still outstanding on the order."""

    required_action = "create"

    def get_queryset(self) -> QuerySet[SalesOrder]:
        return SalesOrder.objects.all()

    @extend_schema(request=DateSerializer, responses={201: InvoiceSerializer})
    def post(self, request: Request, pk: int) -> Response:
        invoice = run(services.invoice_order, actor(request), self.get_object(), _on(request))
        return Response(InvoiceSerializer(INVOICE.queryset().get(pk=invoice.pk)).data, 201)


class InvoiceCreditView(SalesView, generics.GenericAPIView[Invoice]):
    """Start a credit note for everything on the invoice not yet returned."""

    required_action = "create"

    def get_queryset(self) -> QuerySet[Invoice]:
        return Invoice.objects.all()

    @extend_schema(request=DateSerializer, responses={201: CreditNoteSerializer})
    def post(self, request: Request, pk: int) -> Response:
        note = run(services.credit_invoice, actor(request), self.get_object(), _on(request))
        return Response(CreditNoteSerializer(CREDIT.queryset().get(pk=note.pk)).data, 201)
