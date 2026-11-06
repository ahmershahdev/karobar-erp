from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.tenancy.models import TenantOwnedModel


class ChatMessage(TenantOwnedModel):
    """One message in a person's chat. Written once: its signature covers the words, the person,
    the business and the time, so the row is never changed or deleted."""

    class Role(models.TextChoices):
        USER = "user"
        ASSISTANT = "assistant"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    signature = models.CharField(max_length=64)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["id"]
        indexes = [models.Index(fields=["tenant", "user", "id"])]

    def __str__(self) -> str:
        return f"{self.role} {self.pk}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None:
            raise ValueError("chat messages are never changed")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValueError("chat messages are never deleted")
