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
        RESET = "reset"
        # A card the chat proposed, and the row that records it was confirmed. Both hold JSON.
        DRAFT = "draft"
        DONE = "done"

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


class ChatJob(TenantOwnedModel):
    """One answer being worked out by a Celery worker. The question is saved first and the
    screen polls this row, so a slow reply from the model holds a worker, never a web request."""

    class Status(models.TextChoices):
        WAITING = "waiting"
        DONE = "done"
        FAILED = "failed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    question = models.OneToOneField(ChatMessage, on_delete=models.CASCADE, related_name="job")
    language = models.CharField(max_length=5, default="en")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.WAITING)
    answer = models.OneToOneField(
        ChatMessage, on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    error = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"{self.status} {self.pk}"
