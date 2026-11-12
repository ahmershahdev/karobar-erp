"""Remove a demo business and everything in it.

The app never deletes a business: posted entries, audit rows and chat messages refuse to be
deleted, and most links are PROTECT. A demo business has to go in one piece each night, so its
rows are deleted table by table with foreign key checks off, inside one transaction. Only
businesses listed in DemoBusiness can be wiped, so a real one can never be touched.
"""

from django.apps import apps
from django.db import connection, models, transaction

from apps.tenancy.models import Tenant

from .models import DemoBusiness


class NotDemoError(Exception):
    """Only a business made by the seed command can be wiped."""


def tenant_fields() -> list[tuple[type[models.Model], str]]:
    """Every model with a field pointing at a business, and that field."""
    found = []
    for model in apps.get_models(include_auto_created=True):
        for field in model._meta.concrete_fields:
            if isinstance(field, models.ForeignKey) and field.related_model is Tenant:
                found.append((model, field.name))
    return found


def wipe(tenant: Tenant) -> None:
    if not DemoBusiness.objects.filter(tenant=tenant).exists():
        raise NotDemoError
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        try:
            for model, name in tenant_fields():
                # The base manager sees every business's rows; the filter keeps this one's.
                # A raw delete skips the model's own delete(), which refuses for posted rows.
                rows = model._base_manager.filter(**{name: tenant})
                rows._raw_delete(connection.alias)
            Tenant.objects.filter(pk=tenant.pk)._raw_delete(connection.alias)
        finally:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")


def wipe_all() -> int:
    tenants = list(Tenant.objects.filter(pk__in=DemoBusiness.objects.values("tenant")))
    for tenant in tenants:
        wipe(tenant)
    return len(tenants)
