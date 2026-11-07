import logging
from datetime import date, timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.platform.mail import send_message
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Membership, Tenant

from . import services

logger = logging.getLogger(__name__)


def _summarise(tenant: Tenant, today: date, yesterday: date) -> int:
    with tenant_context(tenant):
        sales = services.sales_on(yesterday)
        attention = services.home(today)["attention"]
        owners = list(
            Membership.objects.filter(is_owner=True, user__is_active=True).values_list(
                "user__email", flat=True
            )
        )
    if not sales and not any(attention.values()):
        return 0
    paragraphs = [f"Sales yesterday: {tenant.base_currency} {sales:,.2f}"]
    if attention["overdue"]:
        paragraphs.append(f"Overdue bills: {attention['overdue']}")
    if attention["low_stock"]:
        paragraphs.append(f"Products running low: {attention['low_stock']}")
    if attention["open_tills"]:
        paragraphs.append(f"Tills still open: {attention['open_tills']}")
    link = f"{settings.SITE_URL.rstrip('/')}/app/{tenant.slug}"
    for email in owners:
        send_message(
            email,
            f"Your day at {tenant.name}",
            f"How {tenant.name} is doing",
            paragraphs,
            ("Open my business", link),
            "You can turn this email off on your business home page.",
        )
    return len(owners)


@shared_task  # type: ignore[untyped-decorator]
def send_daily_summaries() -> int:
    """Email each owner how yesterday went and what needs attention. A quiet day sends nothing."""
    sent = 0
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    for tenant in Tenant.objects.filter(daily_summary=True).order_by("pk"):
        # One business failing must not cost every later business its email.
        try:
            sent += _summarise(tenant, today, yesterday)
        except Exception:
            logger.exception("Daily summary failed for tenant %s", tenant.pk)
    return sent
