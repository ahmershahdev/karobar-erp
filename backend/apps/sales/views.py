from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from django.db.models import Prefetch, Q, QuerySet
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounting.models import TaxRate
from apps.accounting.serializers import TaxRateSerializer
from apps.accounting.services import AccountingError
from apps.accounts.models import User
from apps.inventory.services import InventoryError
from apps.purchasing.serializers import (
    DateSerializer,
    StatementQuerySerializer,
    StatementSerializer,
)
from apps.tenancy.context import tenant_context
from apps.tenancy.permissions import HasModulePermission

from . import billing, documents, links, reports, services
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
    BillImageSerializer,
    BillSettingsSerializer,
    BillShareSerializer,
    CreditNoteSerializer,
    CustomerReceiptSerializer,
    CustomerSerializer,
    InvoiceSerializer,
    ReceivableRowSerializer,
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
DISCOUNT = ("discount_percent", "bill_discount")
ORDER = Kind(
    SalesOrder,
    SalesOrderSerializer,
    _queryset(SalesOrder, "lines", SalesOrderLine, "product", "unit"),
    services.save_order,
    ("customer", "date", "valid_until", "warehouse", "memo", *DISCOUNT),
    "lines",
    lambda d: services.OrderLineInput(
        d["product"],
        d["unit"],
        d["quantity"],
        d["unit_price"],
        d.get("tax_amount", ZERO),
        d.get("tax_rate"),
        d.get("discount_percent"),
        d.get("discount", ZERO),
    ),
    services.confirm_order,
)
INVOICE = Kind(
    Invoice,
    InvoiceSerializer,
    _queryset(Invoice, "lines", InvoiceLine, "product", "unit"),
    services.save_invoice,
    ("customer", "order", "date", "due_date", "warehouse", "memo", *DISCOUNT),
    "lines",
    lambda d: services.InvoiceLineInput(
        d["product"],
        d["unit"],
        d["quantity"],
        d["unit_price"],
        d.get("tax_amount", ZERO),
        d.get("order_line"),
        d.get("batch_number", ""),
        d.get("tax_rate"),
        d.get("discount_percent"),
        d.get("discount", ZERO),
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


class SalesTaxRateListView(SalesView, generics.ListAPIView[TaxRate]):
    """The rates to choose from on a sale. Setting them up stays with accounting."""

    serializer_class = TaxRateSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[TaxRate]:
        return TaxRate.objects.all()


class CustomerStatementView(SalesView, generics.GenericAPIView[Customer]):
    def get_queryset(self) -> QuerySet[Customer]:
        return Customer.objects.all()

    @extend_schema(parameters=[StatementQuerySerializer], responses=StatementSerializer)
    def get(self, request: Request, pk: int) -> Response:
        query = StatementQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        statement = reports.statement(
            self.get_object(),
            query.validated_data.get("start"),
            query.validated_data.get("end") or timezone.localdate(),
        )
        return Response(StatementSerializer(statement).data)


class ReceivablesAgeingView(SalesView, generics.GenericAPIView[Customer]):
    pagination_class = None

    @extend_schema(responses=ReceivableRowSerializer(many=True))
    def get(self, request: Request) -> Response:
        rows = reports.ageing(timezone.localdate())
        customers = Customer.objects.in_bulk([row["id"] for row in rows])
        for row in rows:
            row["whatsapp"] = links.reminder_message(customers[row["id"]], row["total"])
        return Response(ReceivableRowSerializer(rows, many=True).data)


class PrintingUnavailable(APIException):
    status_code = 503
    default_detail = documents.PdfUnavailableError.message
    default_code = "pdf_unavailable"


def pdf_response(
    request: Request, render: Callable[[Any, str], str], document: Any
) -> HttpResponse:
    if document.status != "posted":
        raise ValidationError({"detail": "Only posted documents can be printed."})
    language = request.query_params.get("lang", "")
    if language not in documents.LANGUAGES:
        language = "en"
    try:
        pdf = documents.to_pdf(render(document, language))
    except documents.PdfUnavailableError as exc:
        raise PrintingUnavailable from exc
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{document.number}.pdf"'
    return response


LANGUAGE = OpenApiParameter("lang", str)
PDF = {(200, "application/pdf"): bytes}


class InvoicePdfView(SalesView, generics.GenericAPIView[Invoice]):
    def get_queryset(self) -> QuerySet[Invoice]:
        return Invoice.objects.select_related("customer")

    @extend_schema(parameters=[LANGUAGE], responses=PDF)
    def get(self, request: Request, pk: int) -> HttpResponse:
        return pdf_response(request, documents.invoice_html, self.get_object())


class InvoiceShareView(SalesView, generics.GenericAPIView[Invoice]):
    def get_queryset(self) -> QuerySet[Invoice]:
        return Invoice.objects.select_related("customer")

    @extend_schema(responses=BillShareSerializer)
    def get(self, request: Request, pk: int) -> Response:
        invoice = self.get_object()
        if invoice.status != Invoice.Status.POSTED:
            raise ValidationError({"detail": "Only posted bills can be shared."})
        data = {"link": links.bill_url(invoice), "whatsapp": links.bill_message(invoice)}
        return Response(BillShareSerializer(data).data)


class PublicBillView(APIView):
    """One bill for whoever holds its signed link. A bad, old or draft link all look the same."""

    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]
    throttle_scope = "anon"

    @extend_schema(parameters=[LANGUAGE], responses=PDF)
    def get(self, request: Request, token: str) -> HttpResponse:
        found = links.read_bill_token(token)
        if found is None:
            raise NotFound
        tenant, pk = found
        with tenant_context(tenant):
            invoice = (
                Invoice.objects.select_related("customer")
                .filter(pk=pk, status=Invoice.Status.POSTED)
                .first()
            )
            if invoice is None:
                raise NotFound
            response = pdf_response(request, documents.invoice_html, invoice)
        # The link is the key to the bill, so it must not reach caches, search engines or
        # other sites through the Referer header.
        response["Cache-Control"] = "private, no-store"
        response["X-Robots-Tag"] = "noindex"
        response["Referrer-Policy"] = "no-referrer"
        return response


class ReceiptPdfView(SalesView, generics.GenericAPIView[CustomerReceipt]):
    def get_queryset(self) -> QuerySet[CustomerReceipt]:
        return CustomerReceipt.objects.select_related("customer")

    @extend_schema(parameters=[LANGUAGE], responses=PDF)
    def get(self, request: Request, pk: int) -> HttpResponse:
        return pdf_response(request, documents.receipt_html, self.get_object())


def _billing(call: Any, *args: Any) -> Any:
    try:
        return call(*args)
    except billing.BillingError as exc:
        raise ValidationError({"detail": type(exc).message}) from exc


class BillSettingsView(APIView):
    """Business-wide, like the daily summary, so it sits with the people who run the business."""

    permission_classes = [HasModulePermission]
    module = "members"
    throttle_scope = "tenancy"

    @extend_schema(responses=BillSettingsSerializer)
    def get(self, request: Request) -> Response:
        return Response(BillSettingsSerializer(billing.current()).data)

    @extend_schema(request=BillSettingsSerializer, responses=BillSettingsSerializer)
    def patch(self, request: Request) -> Response:
        body = BillSettingsSerializer(billing.current(), data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        saved = _billing(billing.save, actor(request), body.validated_data)
        return Response(BillSettingsSerializer(saved).data)


class BillImageView(APIView):
    """The logo or the signature picture, named by `kind` in the URL configuration."""

    permission_classes = [HasModulePermission]
    module = "members"
    throttle_scope = "tenancy"
    parser_classes = [MultiPartParser]
    kind = "logo"

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        # Taking a picture off changes the bill like putting one up, so both need update
        # rights; delete rights alone don't remove it.
        self.required_action = "update" if request.method == "DELETE" else None
        super().initial(request, *args, **kwargs)

    @extend_schema(responses={(200, "image/png"): OpenApiTypes.BINARY})
    def get(self, request: Request) -> HttpResponse:
        picture = getattr(billing.current(), self.kind)
        if not picture:
            raise NotFound
        response = HttpResponse(bytes(picture), content_type="image/png")
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        request={"multipart/form-data": BillImageSerializer}, responses=BillSettingsSerializer
    )
    def put(self, request: Request) -> Response:
        # Django's upload limits don't count file data, so the size is checked here before
        # anything is read. nginx stops anything over 2 MB earlier still.
        if int(request.META.get("CONTENT_LENGTH") or 0) > billing.MAX_REQUEST_BYTES:
            raise ValidationError({"detail": billing.BadImageError.message})
        body = BillImageSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        upload = body.validated_data["image"]
        # One byte past the limit is enough to know it is too big, without reading the rest.
        data = upload.read(billing.MAX_IMAGE_BYTES + 1)
        saved = _billing(billing.set_image, actor(request), self.kind, data)
        return Response(BillSettingsSerializer(saved).data)

    @extend_schema(request=None, responses={200: BillSettingsSerializer})
    def delete(self, request: Request) -> Response:
        saved = billing.set_image(actor(request), self.kind, None)
        return Response(BillSettingsSerializer(saved).data)
