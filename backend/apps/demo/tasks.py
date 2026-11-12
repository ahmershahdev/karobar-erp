import logging

from celery import shared_task
from django.conf import settings

from . import reset

logger = logging.getLogger(__name__)


# A year of documents per business takes a while, far past the default limit for a task.
@shared_task(time_limit=4 * 3600, soft_time_limit=4 * 3600 - 300)  # type: ignore[untyped-decorator]
def reset_demo() -> list[str]:
    """Each night, put the demo businesses back as they were. Does nothing outside demo mode."""
    if not settings.DEMO_MODE:
        return []
    lines = reset.reset(settings.DEMO_DAYS)
    for line in lines:
        logger.info("Demo reset: %s", line)
    return lines
