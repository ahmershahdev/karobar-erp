"""Chat answers, worked out off the web request (see ChatJob)."""

import logging

from celery import shared_task
from django.utils import timezone

from apps.tenancy.context import tenant_context
from apps.tenancy.models import Membership

from . import services
from .models import ChatJob

logger = logging.getLogger(__name__)


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
