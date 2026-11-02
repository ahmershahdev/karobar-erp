from typing import Any

from django.core.management.base import BaseCommand

from apps.accounting import services
from apps.accounting.models import Account
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant


class Command(BaseCommand):
    help = "Install the standard chart and a current fiscal year for businesses that have none."

    def handle(self, *args: Any, **options: Any) -> None:
        done = 0
        for tenant in Tenant.objects.order_by("pk"):
            with tenant_context(tenant):
                if Account.objects.exists():
                    continue
                services.install_chart(tenant, None)
                services.create_current_fiscal_year(None, tenant.fiscal_year_start_month)
                done += 1
        self.stdout.write(f"Set up books for {done} business(es).")
