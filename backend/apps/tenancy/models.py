import uuid
from typing import Any, ClassVar

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from django.utils.text import slugify

from .context import get_current_tenant
from .managers import TenantScopedManager


class Tenant(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=150)
    # For readable app URLs only. The API still identifies a tenant by public_id, and the app
    # resolves a slug against the signed-in user's own memberships, so knowing one grants nothing.
    slug = models.SlugField(max_length=60, unique=True, editable=False)
    base_currency = models.CharField(max_length=3, default="PKR")
    locale = models.CharField(max_length=5, default="en")
    # July for Pakistan's July to June fiscal year; 1 for a calendar year.
    fiscal_year_start_month = models.PositiveSmallIntegerField(default=7)
    # "average" or "fifo". Fixed once stock has moved: changing it would revalue history.
    valuation_method = models.CharField(max_length=10, default="average")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.slug:
            super().save(*args, **kwargs)
            return
        # Urdu and Arabic names slugify to nothing, so those businesses get a generic stem.
        stem = slugify(self.name)[:50].strip("-") or "business"
        fallback = f"{stem}-{self.public_id.hex[:6]}"
        self.slug = fallback if Tenant.objects.filter(slug=stem).exists() else stem
        try:
            with transaction.atomic():
                super().save(*args, **kwargs)
        except IntegrityError:
            # Two businesses with the same name created at the same moment.
            self.slug = fallback
            super().save(*args, **kwargs)


class TenantOwnedModel(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+")

    objects: ClassVar[TenantScopedManager[Any]] = TenantScopedManager()
    all_tenants: ClassVar[models.Manager[Any]] = models.Manager()

    class Meta:
        abstract = True
        base_manager_name = "all_tenants"

    def save(self, *args: Any, **kwargs: Any) -> None:
        current = get_current_tenant()
        if self.tenant_id is None:
            self.tenant = current
        elif self.tenant_id != current.pk:
            raise PermissionDenied("row belongs to another tenant")
        super().save(*args, **kwargs)


class Role(TenantOwnedModel):
    name = models.CharField(max_length=80)
    # {"sales": ["view", "create", "post"], ...}; checked by apps.tenancy.permissions.
    permissions = models.JSONField(default=dict)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "name"], name="uniq_role_name")]

    def __str__(self) -> str:
        return self.name


class Membership(TenantOwnedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.ForeignKey(Role, on_delete=models.PROTECT, null=True, blank=True)
    is_owner = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "user"], name="uniq_membership")]

    def __str__(self) -> str:
        return f"{self.user_id} in {self.tenant_id}"


class Invitation(TenantOwnedModel):
    email = models.EmailField()
    role = models.ForeignKey(Role, on_delete=models.PROTECT, null=True, blank=True)
    # Only a SHA-256 of the emailed token is stored, so a database leak can't be used to join.
    token_hash = models.CharField(max_length=64, unique=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantOwnedModel.Meta):
        indexes = [models.Index(fields=["tenant", "email"])]

    def __str__(self) -> str:
        return f"{self.email} to {self.tenant_id}"

    @property
    def is_pending(self) -> bool:
        return (
            self.accepted_at is None
            and self.revoked_at is None
            and self.expires_at > timezone.now()
        )


class AuditEvent(TenantOwnedModel):
    class Action(models.TextChoices):
        CREATE = "create"
        UPDATE = "update"
        DELETE = "delete"
        POST = "post"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    action = models.CharField(max_length=10, choices=Action.choices)
    model = models.CharField(max_length=100)
    object_id = models.CharField(max_length=64)
    # DjangoJSONEncoder keeps Decimal amounts, dates and UUIDs readable in the audit trail.
    changes = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    request_id = models.CharField(max_length=64, blank=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta(TenantOwnedModel.Meta):
        indexes = [models.Index(fields=["tenant", "model", "object_id"])]

    def __str__(self) -> str:
        return f"{self.action} {self.model}#{self.object_id}"
