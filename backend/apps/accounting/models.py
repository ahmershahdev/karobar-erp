from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction

from apps.core.balances import AccountType
from apps.tenancy.models import TenantOwnedModel


class Account(TenantOwnedModel):
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=150)
    type = models.CharField(
        max_length=10, choices=[(t.value, t.name.title()) for t in AccountType]
    )
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="children"
    )
    # Group accounts only total their children; entries can't be posted to them.
    is_group = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    # The posting-rule role this account plays ("receivables", "sales"); one account per role.
    # NULL, not "", for accounts without a role: MySQL lets many NULLs share a unique index.
    role = models.CharField(max_length=40, null=True, blank=True)  # noqa: DJ001

    class Meta(TenantOwnedModel.Meta):
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="uniq_account_code"),
            models.UniqueConstraint(fields=["tenant", "role"], name="uniq_account_role"),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class FiscalYear(TenantOwnedModel):
    name = models.CharField(max_length=40)
    start = models.DateField()
    end = models.DateField()

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-start"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "start"], name="uniq_fiscal_year_start")
        ]

    def __str__(self) -> str:
        return self.name


class FiscalPeriod(TenantOwnedModel):
    fiscal_year = models.ForeignKey(FiscalYear, on_delete=models.CASCADE, related_name="periods")
    number = models.PositiveSmallIntegerField()
    start = models.DateField()
    end = models.DateField()
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["start"]
        indexes = [models.Index(fields=["tenant", "start", "end"])]

    def __str__(self) -> str:
        return f"{self.fiscal_year.name} P{self.number}"


class NumberSeries(TenantOwnedModel):
    """A gapless counter. Only ever read and advanced under select_for_update()."""

    key = models.CharField(max_length=20)
    prefix = models.CharField(max_length=10)
    next_number = models.PositiveIntegerField(default=1)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "key"], name="uniq_series_key")]

    def __str__(self) -> str:
        return f"{self.prefix}{self.next_number}"


class PostedEntryError(ValidationError):
    pass


class JournalEntry(TenantOwnedModel):
    class Status(models.TextChoices):
        DRAFT = "draft"
        POSTED = "posted"

    # Drafts have no number yet; NULLs don't collide in the unique (tenant, number) index.
    number = models.CharField(max_length=30, null=True, blank=True)  # noqa: DJ001
    date = models.DateField()
    memo = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    # One reversal per entry, enforced by the unique constraint.
    reversal_of = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_by"
    )
    source_type = models.CharField(max_length=40, blank=True)
    source_id = models.CharField(max_length=64, blank=True)
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
            models.UniqueConstraint(fields=["tenant", "number"], name="uniq_entry_number")
        ]
        indexes = [models.Index(fields=["tenant", "status", "date"])]

    def __str__(self) -> str:
        return self.number or f"Draft {self.pk}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        # A posted entry is a permanent record. The only write allowed after posting is the one
        # that posts it, which the posting service does with update_fields.
        if self.pk is not None:
            stored = JournalEntry.all_tenants.filter(pk=self.pk).values_list("status", flat=True)
            if stored.first() == self.Status.POSTED:
                raise PostedEntryError("Posted entries can't be changed; post a reversal instead.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        # Ask the database, not this copy, and hold the row until the delete is done, so nothing
        # can post the entry between the check and the delete.
        with transaction.atomic():
            stored = (
                JournalEntry.all_tenants.select_for_update()
                .filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )
            if self.Status.POSTED in (self.status, stored):
                raise PostedEntryError("Posted entries can't be deleted; post a reversal instead.")
            return super().delete(*args, **kwargs)


class JournalLine(TenantOwnedModel):
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="lines")
    debit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    description = models.CharField(max_length=255, blank=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["id"]
        indexes = [models.Index(fields=["tenant", "account", "entry"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(debit__gte=0, credit__gte=0), name="line_amounts_not_negative"
            )
        ]

    def __str__(self) -> str:
        return f"{self.account_id} {self.debit}/{self.credit}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.entry.status == JournalEntry.Status.POSTED:
            raise PostedEntryError("Lines of a posted entry can't be changed.")
        super().save(*args, **kwargs)
