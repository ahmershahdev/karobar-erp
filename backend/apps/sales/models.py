from django.db import models
from django.db.models import F, Q

from apps.accounting.models import Account, JournalEntry, TaxRate
from apps.inventory.models import Product, StockEntry, Unit, Warehouse, money_field, quantity_field
from apps.purchasing.models import Document, PostedStatus
from apps.tenancy.models import TenantOwnedModel


class Customer(TenantOwnedModel):
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=300, blank=True)
    tax_number = models.CharField(max_length=40, blank=True)
    payment_terms_days = models.PositiveSmallIntegerField(default=0)
    # Empty means no limit; zero means cash only. See apps.core.credit.
    credit_limit = money_field(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="uniq_customer_code")
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class SalesOrder(Document):
    """A quotation and an order are one document at two stages, so nothing is typed twice.

    A draft can be sent as a quotation, which gives it a QUO number, or confirmed straight away.
    Confirming gives it an SO number and is when the credit limit is checked.
    """

    class Status(models.TextChoices):
        DRAFT = "draft"
        QUOTED = "quoted"
        CONFIRMED = "confirmed"
        CLOSED = "closed"

    MUTABLE_AFTER_POST = frozenset({"status", "number", "posted_by", "posted_at"})

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="+")
    quote_number = models.CharField(max_length=30, null=True, blank=True)  # noqa: DJ001
    valid_until = models.DateField(null=True, blank=True)
    total = money_field(default=0)

    class Meta(Document.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="uniq_so_number"),
            models.UniqueConstraint(fields=["tenant", "quote_number"], name="uniq_quote_number"),
        ]


class SalesOrderLine(TenantOwnedModel):
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    quantity = quantity_field()
    unit_price = quantity_field()
    tax_rate = models.ForeignKey(
        TaxRate, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    tax_amount = money_field(default=0)
    invoiced_quantity = quantity_field(default=0)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0, unit_price__gte=0, tax_amount__gte=0)
                & Q(invoiced_quantity__gte=0)
                & Q(invoiced_quantity__lte=F("quantity")),
                name="so_line_quantities",
            )
        ]

    def __str__(self) -> str:
        return f"{self.product_id} {self.quantity}"


class Invoice(Document):
    Status = PostedStatus
    MUTABLE_AFTER_POST = frozenset({"amount_paid", "amount_credited"})

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="invoices")
    order = models.ForeignKey(
        SalesOrder, on_delete=models.PROTECT, null=True, blank=True, related_name="invoices"
    )
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="+")
    due_date = models.DateField(null=True, blank=True)
    net = money_field(default=0)
    tax = money_field(default=0)
    total = money_field(default=0)
    # What the goods cost us, as the stock engine booked it.
    cost = money_field(default=0)
    amount_paid = money_field(default=0)
    amount_credited = money_field(default=0)
    journal_entry = models.OneToOneField(
        JournalEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    # The stock issue that moved the goods out, with its own entry for their cost.
    stock_entry = models.OneToOneField(
        StockEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta(Document.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="uniq_invoice_number"),
            models.CheckConstraint(
                condition=Q(amount_paid__gte=0, amount_credited__gte=0)
                & Q(total__gte=F("amount_paid") + F("amount_credited")),
                name="invoice_settled_within_total",
            ),
        ]
        indexes = [models.Index(fields=["tenant", "customer", "status"])]


class InvoiceLine(TenantOwnedModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    order_line = models.ForeignKey(
        SalesOrderLine, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    quantity = quantity_field()
    unit_price = quantity_field()
    amount = money_field()
    tax_rate = models.ForeignKey(
        TaxRate, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    tax_amount = money_field(default=0)
    batch_number = models.CharField(max_length=40, blank=True)
    cost = money_field(default=0)
    returned_quantity = quantity_field(default=0)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0, unit_price__gte=0, tax_amount__gte=0)
                & Q(returned_quantity__gte=0)
                & Q(returned_quantity__lte=F("quantity")),
                name="invoice_line_quantities",
            )
        ]

    def __str__(self) -> str:
        return f"{self.product_id} {self.quantity}"


class CustomerReceipt(Document):
    Status = PostedStatus

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="receipts")
    amount = money_field()
    # The cash or bank account the money went into.
    received_into = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="+")
    reference = models.CharField(max_length=60, blank=True)
    journal_entry = models.OneToOneField(
        JournalEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta(Document.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="uniq_customer_receipt"),
            models.CheckConstraint(condition=Q(amount__gte=0), name="receipt_not_negative"),
        ]


class ReceiptAllocation(TenantOwnedModel):
    receipt = models.ForeignKey(
        CustomerReceipt, on_delete=models.CASCADE, related_name="allocations"
    )
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="allocations")
    amount = money_field()

    class Meta(TenantOwnedModel.Meta):
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="receipt_allocation_positive")
        ]

    def __str__(self) -> str:
        return f"{self.invoice_id} {self.amount}"


class CreditNote(Document):
    """Goods coming back against one invoice: they return to stock and the customer owes less."""

    Status = PostedStatus

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="credit_notes")
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="credit_notes")
    net = money_field(default=0)
    tax = money_field(default=0)
    total = money_field(default=0)
    # How much came off the invoice. Any rest stays on the customer's account as credit.
    applied = money_field(default=0)
    journal_entry = models.OneToOneField(
        JournalEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    stock_entry = models.OneToOneField(
        StockEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta(Document.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="uniq_credit_note_number"),
        ]


class CreditNoteLine(TenantOwnedModel):
    note = models.ForeignKey(CreditNote, on_delete=models.CASCADE, related_name="lines")
    invoice_line = models.ForeignKey(InvoiceLine, on_delete=models.PROTECT, related_name="+")
    quantity = quantity_field()
    amount = money_field(default=0)
    tax_amount = money_field(default=0)
    cost = money_field(default=0)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="credit_line_quantity")
        ]

    def __str__(self) -> str:
        return f"{self.invoice_line_id} {self.quantity}"
