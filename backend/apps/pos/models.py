from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.accounting.models import JournalEntry
from apps.inventory.models import Warehouse, money_field
from apps.sales.models import CustomerReceipt, Invoice
from apps.tenancy.models import TenantOwnedModel


class PosSession(TenantOwnedModel):
    """One till from opening to the end-of-day count."""

    class Status(models.TextChoices):
        OPEN = "open"
        CLOSED = "closed"

    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    # Holds the warehouse id while open and is empty once closed. MySQL has no partial unique
    # index, and this is what lets the database itself refuse a second open till.
    open_key = models.CharField(max_length=20, null=True, blank=True)  # noqa: DJ001
    opening_float = money_field(default=0)
    expected_cash = money_field(null=True, blank=True)
    counted_cash = money_field(null=True, blank=True)
    difference = money_field(null=True, blank=True)
    journal_entry = models.OneToOneField(
        JournalEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "open_key"], name="one_open_till_per_store"),
            models.CheckConstraint(condition=Q(opening_float__gte=0), name="float_not_negative"),
        ]

    def __str__(self) -> str:
        return f"Till {self.pk} {self.status}"


class PosSale(TenantOwnedModel):
    class Method(models.TextChoices):
        CASH = "cash"
        CARD = "card"

    session = models.ForeignKey(PosSession, on_delete=models.PROTECT, related_name="sales")
    invoice = models.OneToOneField(Invoice, on_delete=models.PROTECT, related_name="+")
    # Empty only for a sale given away in full, which takes no money.
    receipt = models.OneToOneField(
        CustomerReceipt, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    method = models.CharField(max_length=10, choices=Method.choices)
    amount = money_field()
    tendered = money_field()
    change = money_field(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"{self.invoice_id} {self.amount}"
