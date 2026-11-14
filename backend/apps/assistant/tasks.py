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
    """Remove chat messages older than CHAT_KEEP_DAYS, for every business and person. One
    person or business failing doesn't stop the rest; the run then fails, so it is noticed."""
    cutoff = timezone.now() - timedelta(days=settings.CHAT_KEEP_DAYS)
    removed = 0
    failed: list[str] = []
    for tenant in Tenant.objects.order_by("pk"):
        try:
            with tenant_context(tenant):
                users = (
                    ChatMessage.objects.filter(created_at__lt=cutoff)
                    .values_list("user", flat=True)
                    .distinct()
                )
                for user in User.objects.filter(pk__in=list(users)).order_by("pk"):
                    try:
                        removed += services.clear_before(user, cutoff)
                    except Exception:
                        logger.exception(
                            "Clearing old chat failed for user %s in tenant %s", user.pk, tenant.pk
                        )
                        failed.append(f"user {user.pk} in tenant {tenant.pk}")
        except Exception:
            logger.exception("Clearing old chat failed for tenant %s", tenant.pk)
            failed.append(f"tenant {tenant.pk}")
    if failed:
        raise RuntimeError(f"Old chat not cleared for {', '.join(failed)}; {removed} removed")
    return removed


def _end_unanswered(job_id: int, why: str) -> str:
    ended = ChatJob.all_tenants.filter(pk=job_id, status=ChatJob.Status.WAITING).update(
        status=ChatJob.Status.FAILED,
        error=services.AssistantError.message,
        finished_at=timezone.now(),
    )
    if ended:
        logger.warning("Chat job %s was not answered: %s", job_id, why)
        return str(ChatJob.Status.FAILED)
    status = ChatJob.all_tenants.filter(pk=job_id).values_list("status", flat=True).first()
    return str(status or "gone")


@shared_task  # type: ignore[untyped-decorator]
def answer_question(job_id: int) -> str:
    now = timezone.now()
    # One update that only one delivery can win. A job nobody started on in time is left
    # unanswered too: the screen has stopped waiting, and a late answer would arrive out of
    # order and use the model's quota for nothing.
    claimed = ChatJob.all_tenants.filter(
        pk=job_id,
        status=ChatJob.Status.WAITING,
        started_at__isnull=True,
        created_at__gte=now - services.QUEUE_PATIENCE,
    ).update(started_at=now)
    if not claimed:
        # Still waiting means it is too old, or this is a second delivery after the first
        # worker died part-way (acks_late). Either way nobody is working on it.
        return _end_unanswered(job_id, "it waited too long or was delivered twice")
    job = ChatJob.all_tenants.select_related("tenant", "user", "question").get(pk=job_id)
    answer, status, error = None, ChatJob.Status.FAILED, services.AssistantError.message
    with tenant_context(job.tenant):
        # The person's rights as they are now, not when they asked: a role may have changed.
        membership = Membership.objects.filter(user=job.user, user__is_active=True).first()
        try:
            if membership is None:
                raise services.AssistantError
            answer = services.answer(job.user, membership, job.question, job.language)
            status, error = ChatJob.Status.DONE, ""
        except services.AssistantError as exc:
            error = type(exc).message
            logger.info("Chat job %s failed: %s", job.pk, type(exc).__name__)
        except Exception:
            # Anything else is a bug; the person still gets a plain answer instead of waiting.
            logger.exception("Chat answer %s failed", job.pk)
    ChatJob.all_tenants.filter(pk=job.pk, status=ChatJob.Status.WAITING).update(
        answer=answer, status=status, error=error, finished_at=timezone.now()
    )
    return str(status)
