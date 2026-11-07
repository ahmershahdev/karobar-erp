import logging

from celery import shared_task
from django.utils import timezone

from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

from .retention import clear_former_employees

logger = logging.getLogger(__name__)


@shared_task  # type: ignore[untyped-decorator]
def clear_former_employee_details() -> int:
    """Nightly: clear bank accounts and national IDs that former employees' records no longer
    need. One business failing doesn't stop the others."""
    today = timezone.localdate()
    changed = 0
    for tenant in Tenant.objects.all():
        try:
            with tenant_context(tenant):
                changed += clear_former_employees(today)
        except Exception:
            logger.exception("clearing former employees failed for tenant %s", tenant.pk)
    return changed
