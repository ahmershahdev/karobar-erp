from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Tenant

current_tenant_var: ContextVar["Tenant | None"] = ContextVar("current_tenant", default=None)


class TenantNotSetError(RuntimeError):
    pass


def get_current_tenant() -> "Tenant":
    tenant = current_tenant_var.get()
    if tenant is None:
        raise TenantNotSetError("no tenant is active for this request or task")
    return tenant
