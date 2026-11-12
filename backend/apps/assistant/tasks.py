"""Chat answers, worked out off the web request (see ChatJob)."""

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.accounts.models import User
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Membership, Tenant

from . import services
from .models import ChatJob, ChatMessage

logger = logging.getLogger(__name__)


@shared_task  # type: ignore[untyped-decorator]
def clear_old_chats() -> int:
    """Remove chat messages older than CHAT_KEEP_DAYS, for every business and person."""
    cutoff = timezone.now() - timedelta(days=settings.CHAT_KEEP_DAYS)
    removed = 0
    for tenant in Tenant.objects.order_by("pk"):
        # One business failing must not stop the others.
        try:
            with tenant_context(tenant):
                users = (
                    ChatMessage.objects.filter(created_at__lt=cutoff)
                    .values_list("user", flat=True)
                    .distinct()
                )
                for user in User.objects.filter(pk__in=list(users)).order_by("pk"):
                    removed += services.clear_before(user, cutoff)
        except Exception:
            logger.exception("Clearing old chat failed for tenant %s", tenant.pk)
    return removed


@shared_task  # type: ignore[untyped-decorator]
def answer_question(job_id: int) -> str:
    job = ChatJob.all_tenants.select_related("tenant", "user", "question").get(pk=job_id)
    if job.status != ChatJob.Status.WAITING:
        return str(job.status)
    with tenant_context(job.tenant):
        # The person's rights as they are now, not when they asked: a role may have changed.
        membership = Membership.objects.filter(user=job.user, user__is_active=True).first()
        try:
            if membership is None:
                raise services.AssistantError
            job.answer = services.answer(job.user, membership, job.question, job.language)
            job.status = ChatJob.Status.DONE
        except services.AssistantError as exc:
            job.status = ChatJob.Status.FAILED
            job.error = type(exc).message
        except Exception:
            # Anything else is a bug; the person still gets a plain answer instead of waiting.
            logger.exception("Chat answer %s failed", job.pk)
            job.status = ChatJob.Status.FAILED
            job.error = services.AssistantError.message
        job.finished_at = timezone.now()
        job.save(update_fields=["answer", "status", "error", "finished_at"])
    return str(job.status)
