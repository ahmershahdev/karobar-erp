from typing import Any, ClassVar

from django.conf import settings
from django.db import models, transaction
from django.db.models import F, Q

from apps.accounting.models import Account, JournalEntry, PostedEntryError
from apps.inventory.models import Product, StockEntry, Unit, Warehouse, money_field, quantity_field
from apps.tenancy.models import TenantOwnedModel


class Supplier(TenantOwnedModel):
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=300, blank=True)
    tax_number = models.CharField(max_length=40, blank=True)
    payment_terms_days = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="uniq_supplier_code")
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class Document(TenantOwnedModel):
    """A purchase document that becomes a permanent record once it leaves draft.

    After that only the fields in MUTABLE_AFTER_POST may change (a bill's amount paid, an
    order's status), and only through save(update_fields=...). Corrections are new documents.
    """

    DRAFT = "draft"
    MUTABLE_AFTER_POST: ClassVar[frozenset[str]] = frozenset()

    # Drafts have no number yet; NULLs don't collide in the unique (tenant, number) index.
    number = models.CharField(max_length=30, null=True, blank=True)  # noqa: DJ001
    date = models.DateField()
    memo = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, default=DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwnedModel.Meta):
        abstract = True
        ordering = ["-date", "-id"]

    def __str__(self) -> str:
        return self.number or f"Draft {self.pk}"

    def _stored_status(self, lock: bool = False) -> str | None:
        query = type(self).all_tenants.filter(pk=self.pk)
        if lock:
            query = query.select_for_update()
        status: str | None = query.values_list("status", flat=True).first()
        return status

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None and self._stored_status() not in (None, self.DRAFT):
            fields = kwargs.get("update_fields")
            if fields is None or not set(fields) <= self.MUTABLE_AFTER_POST:
                raise PostedEntryError("Posted documents can't be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        with transaction.atomic():
            if self._stored_status(lock=True) not in (None, self.DRAFT):
                raise PostedEntryError("Posted documents can't be deleted.")
            return super().delete(*args, **kwargs)


class PurchaseOrder(Document):
    class Status(models.TextChoices):
        DRAFT = "draft"
        CONFIRMED = "confirmed"
        CLOSED = "closed"

    MUTABLE_AFTER_POST = frozenset({"status"})

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="orders")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="+")
    expected_date = models.DateField(null=True, blank=True)
    total = money_field(default=0)

    class Meta(Document.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "number"], name="uniq_po_number")]


class PurchaseOrderLine(TenantOwnedModel):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    quantity = quantity_field()
    unit_price = quantity_field()
    received_quantity = quantity_field(default=0)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0, unit_price__gte=0, received_quantity__gte=0)
                & Q(received_quantity__lte=F("quantity")),
                name="po_line_quantities",
            )
        ]

    def __str__(self) -> str:
        return f"{self.product_id} {self.quantity}"


class PostedStatus(models.TextChoices):
    DRAFT = "draft"
    POSTED = "posted"


class GoodsReceipt(Document):
    Status = PostedStatus

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="receipts")
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, null=True, blank=True, related_name="receipts"
    )
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="+")
    # The stock receipt that moved the goods; its GRN number is this receipt's number too.
    stock_entry = models.OneToOneField(
        StockEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta(Document.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="uniq_receipt_number")
        ]


class GoodsReceiptLine(TenantOwnedModel):
    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name="lines")
    order_line = models.ForeignKey(
        PurchaseOrderLine, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    quantity = quantity_field()
    unit_cost = quantity_field()
    batch_number = models.CharField(max_length=40, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    # What the stock receipt booked for this line, and how much of it bills have taken.
    value = money_field(default=0)
    billed_quantity = quantity_field(default=0)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0, unit_cost__gte=0, billed_quantity__gte=0)
                & Q(billed_quantity__lte=F("quantity")),
                name="receipt_line_quantities",
            )
        ]

    def __str__(self) -> str:
        return f"{self.product_id} {self.quantity}"


class Bill(Document):
    Status = PostedStatus
    MUTABLE_AFTER_POST = frozenset({"amount_paid"})

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="bills")
    # The supplier's own invoice number, as printed on their paper.
    supplier_reference = models.CharField(max_length=40, blank=True)
    due_date = models.DateField(null=True, blank=True)
    net = money_field(default=0)
    tax = money_field(default=0)
    total = money_field(default=0)
    amount_paid = money_field(default=0)
    journal_entry = models.OneToOneField(
        JournalEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta(Document.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="uniq_bill_number"),
            models.CheckConstraint(
                condition=Q(amount_paid__gte=0) & Q(amount_paid__lte=F("total")),
                name="bill_paid_within_total",
            ),
        ]
        indexes = [models.Index(fields=["tenant", "supplier", "status"])]


class BillLine(TenantOwnedModel):
    """Either goods from a receipt line, or a service or expense booked to `account`."""

    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name="lines")
    receipt_line = models.ForeignKey(
        GoodsReceiptLine, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    description = models.CharField(max_length=255, blank=True)
    quantity = quantity_field()
    unit_price = quantity_field()
    amount = money_field()
    tax_amount = money_field(default=0)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0, unit_price__gte=0, tax_amount__gte=0)
                & (
                    Q(receipt_line__isnull=False, account__isnull=True)
                    | Q(receipt_line__isnull=True, account__isnull=False)
                ),
                name="bill_line_goods_or_account",
            )
        ]

    def __str__(self) -> str:
        return f"{self.bill_id} {self.amount}"


class SupplierPayment(Document):
    Status = PostedStatus

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="payments")
    amount = money_field()
    # The cash or bank account the money left from.
    paid_from = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="+")
    reference = models.CharField(max_length=60, blank=True)
    journal_entry = models.OneToOneField(
        JournalEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta(Document.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="uniq_payment_number"),
            models.CheckConstraint(condition=Q(amount__gte=0), name="payment_not_negative"),
        ]


class PaymentAllocation(TenantOwnedModel):
    payment = models.ForeignKey(
        SupplierPayment, on_delete=models.CASCADE, related_name="allocations"
    )
    bill = models.ForeignKey(Bill, on_delete=models.PROTECT, related_name="allocations")
    amount = money_field()

    class Meta(TenantOwnedModel.Meta):
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="allocation_positive")
        ]

    def __str__(self) -> str:
        return f"{self.bill_id} {self.amount}"
