from celery import shared_task
from django.conf import settings

from apps.platform.tasks import send_email
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Membership, Tenant

from . import services


@shared_task  # type: ignore[untyped-decorator]
def send_stock_alerts() -> int:
    """Email each business's owners a digest of low stock and batches expiring within 30 days."""
    sent = 0
    for tenant in Tenant.objects.order_by("pk"):
        with tenant_context(tenant):
            low = services.low_stock()
            soon = services.expiring(30)
            if not low and not soon:
                continue
            owners = list(
                Membership.objects.filter(is_owner=True, user__is_active=True).values_list(
                    "user__email", flat=True
                )
            )
        lines = [f"Stock alerts for {tenant.name}", ""]
        if low:
            lines.append("Below reorder level:")
            lines += [f"- {row.product.sku} {row.product.name}: {row.on_hand}" for row in low]
            lines.append("")
        if soon:
            lines.append("Expiring within 30 days:")
            lines += [
                f"- {row.batch.product.name} batch {row.batch.number} "
                f"({row.warehouse.code}): {row.quantity}, expires {row.batch.expiry_date}"
                for row in soon
            ]
        link = f"{settings.SITE_URL.rstrip('/')}/app/{tenant.slug}/inventory/alerts"
        lines += ["", link]
        for email in owners:
            send_email.delay(email, f"Stock alerts: {tenant.name}", "\n".join(lines))
            sent += 1
    return sent
