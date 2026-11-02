from typing import Any

from django.dispatch import receiver

from apps.accounts.models import User
from apps.tenancy.models import Tenant
from apps.tenancy.signals import tenant_created

from . import services


@receiver(tenant_created)
def set_up_books(sender: object, tenant: Tenant, owner: User, **kwargs: Any) -> None:
    services.install_chart(tenant, owner)
    services.create_current_fiscal_year(owner, tenant.fiscal_year_start_month)
