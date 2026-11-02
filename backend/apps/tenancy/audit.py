from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser
from django.db import models

from apps.platform.context import request_id_var

from .models import AuditEvent


def record(
    action: AuditEvent.Action,
    instance: models.Model,
    user: AbstractBaseUser | AnonymousUser | None,
    changes: dict[str, Any] | None = None,
) -> AuditEvent:
    """Write one audit row. Call it inside the same transaction as the change it describes."""
    event: AuditEvent = AuditEvent.objects.create(
        user=user if user is not None and user.is_authenticated else None,
        action=action,
        model=instance._meta.label,
        object_id=str(instance.pk),
        changes=changes or {},
        request_id=request_id_var.get(),
    )
    return event
