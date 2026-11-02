from typing import Any

from django.conf import settings
from django.db import models, transaction

from apps.accounting.models import Account, JournalEntry, PostedEntryError
from apps.tenancy.models import TenantOwnedModel


def quantity_field(**kwargs: Any) -> "models.DecimalField[Any, Any]":
    return models.DecimalField(max_digits=18, decimal_places=4, **kwargs)


def money_field(**kwargs: Any) -> "models.DecimalField[Any, Any]":
    return models.DecimalField(max_digits=18, decimal_places=2, **kwargs)


class Unit(TenantOwnedModel):
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=50)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["code"]
        constraints = [models.UniqueConstraint(fields=["tenant", "code"], name="uniq_unit_code")]

    def __str__(self) -> str:
        return self.code


class Category(TenantOwnedModel):
    name = models.CharField(max_length=80)
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="children"
    )

    class Meta(TenantOwnedModel.Meta):
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uniq_category_name")
        ]

    def __str__(self) -> str:
        return self.name


class Product(TenantOwnedModel):
    sku = models.CharField(max_length=40)
    name = models.CharField(max_length=150)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, null=True, blank=True)
    # Stock is always counted in the base unit; packs convert into it.
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    variant_of = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="variants"
    )
    attributes = models.JSONField(default=dict, blank=True)
    track_batches = models.BooleanField(default=False)
    reorder_level = quantity_field(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["tenant", "sku"], name="uniq_product_sku")]

    def __str__(self) -> str:
        return f"{self.sku} {self.name}"


class ProductUnit(TenantOwnedModel):
    """A pack a product is bought or sold in, with its size in base units and its barcode."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="packs")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    factor = quantity_field()
    # NULL, not "", for packs without a barcode: MySQL lets many NULLs share a unique index.
    barcode = models.CharField(max_length=64, null=True, blank=True)  # noqa: DJ001

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "product", "unit"], name="uniq_product_pack"
            ),
            models.UniqueConstraint(fields=["tenant", "barcode"], name="uniq_barcode"),
            models.CheckConstraint(condition=models.Q(factor__gt=0), name="pack_factor_positive"),
        ]

    def __str__(self) -> str:
        return f"{self.product_id} x{self.factor}"


class Warehouse(TenantOwnedModel):
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="uniq_warehouse_code")
        ]

    def __str__(self) -> str:
        return self.code


class Batch(TenantOwnedModel):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="batches")
    number = models.CharField(max_length=40)
    expiry_date = models.DateField(null=True, blank=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["expiry_date", "number"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "product", "number"], name="uniq_batch")
        ]

    def __str__(self) -> str:
        return self.number


class StockLevel(TenantOwnedModel):
    """What one warehouse holds of one product. Only changed under select_for_update()."""

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="levels")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="levels")
    quantity = quantity_field(default=0)
    value = money_field(default=0)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "product", "warehouse"], name="uniq_stock_level"
            ),
            models.CheckConstraint(condition=models.Q(quantity__gte=0), name="stock_not_negative"),
        ]

    def __str__(self) -> str:
        return f"{self.product_id}@{self.warehouse_id}: {self.quantity}"


class BatchLevel(TenantOwnedModel):
    """Quantity of one batch in one warehouse. Changed only while its StockLevel is locked."""

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="levels")
    quantity = quantity_field(default=0)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "warehouse", "batch"], name="uniq_batch_level"
            ),
            models.CheckConstraint(condition=models.Q(quantity__gte=0), name="batch_not_negative"),
        ]

    def __str__(self) -> str:
        return f"{self.batch_id}@{self.warehouse_id}: {self.quantity}"


class CostLayer(TenantOwnedModel):
    """A FIFO layer. Read and changed only while its StockLevel row is locked."""

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="+")
    quantity_left = quantity_field()
    unit_cost = quantity_field()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["id"]
        indexes = [models.Index(fields=["tenant", "product", "warehouse", "quantity_left"])]

    def __str__(self) -> str:
        return f"{self.quantity_left} @ {self.unit_cost}"


class StockEntry(TenantOwnedModel):
    class Kind(models.TextChoices):
        RECEIPT = "receipt"
        ISSUE = "issue"
        TRANSFER = "transfer"
        ADJUSTMENT = "adjustment"

    class Status(models.TextChoices):
        DRAFT = "draft"
        POSTED = "posted"

    kind = models.CharField(max_length=12, choices=Kind.choices)
    number = models.CharField(max_length=30, null=True, blank=True)  # noqa: DJ001
    date = models.DateField()
    memo = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="+")
    to_warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    # The other side of the journal entry for receipts, issues and adjustments.
    contra_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    journal_entry = models.OneToOneField(
        JournalEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-date", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="uniq_stock_entry_number")
        ]

    def __str__(self) -> str:
        return self.number or f"Draft {self.pk}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None:
            stored = StockEntry.all_tenants.filter(pk=self.pk).values_list("status", flat=True)
            if stored.first() == self.Status.POSTED:
                raise PostedEntryError("Posted stock entries can't be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        with transaction.atomic():
            stored = (
                StockEntry.all_tenants.select_for_update()
                .filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )
            if self.Status.POSTED in (self.status, stored):
                raise PostedEntryError("Posted stock entries can't be deleted.")
            return super().delete(*args, **kwargs)


class StockEntryLine(TenantOwnedModel):
    entry = models.ForeignKey(StockEntry, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    # For adjustments this is the counted quantity; for everything else, the quantity moved.
    quantity = quantity_field()
    unit_cost = quantity_field(null=True, blank=True)
    batch_number = models.CharField(max_length=40, blank=True)
    expiry_date = models.DateField(null=True, blank=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=0), name="entry_qty_not_negative"
            )
        ]

    def __str__(self) -> str:
        return f"{self.product_id} {self.quantity}"


class StockMove(TenantOwnedModel):
    """One change to one stock level. Positive quantities and values come in, negative go out."""

    entry = models.ForeignKey(
        StockEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="moves"
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="moves")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="moves")
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, null=True, blank=True)
    date = models.DateField()
    quantity = quantity_field()
    value = money_field()
    source_type = models.CharField(max_length=40, blank=True)
    source_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["id"]
        indexes = [models.Index(fields=["tenant", "product", "warehouse", "date"])]

    def __str__(self) -> str:
        return f"{self.product_id}@{self.warehouse_id} {self.quantity}"
