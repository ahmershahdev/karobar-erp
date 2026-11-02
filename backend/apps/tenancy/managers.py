from typing import TYPE_CHECKING, Any, TypeVar

from django.db import models

from .context import get_current_tenant

if TYPE_CHECKING:
    from .models import TenantOwnedModel

M = TypeVar("M", bound="TenantOwnedModel")


class TenantScopedManager(models.Manager[M]):
    """The default manager of every tenant-owned model.

    It fails closed: with no active tenant it raises instead of returning every tenant's rows.
    Code that really needs all tenants (migrations, platform reports) uses `all_tenants`.
    """

    def get_queryset(self) -> models.QuerySet[M]:
        return super().get_queryset().filter(tenant=get_current_tenant())

    def create(self, **kwargs: Any) -> M:
        kwargs.setdefault("tenant", get_current_tenant())
        return super().create(**kwargs)
