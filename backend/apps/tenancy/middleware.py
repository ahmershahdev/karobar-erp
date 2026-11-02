import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse, JsonResponse

from .context import current_tenant_var
from .models import Membership

TENANT_HEADER = "X-Tenant"


class TenantMiddleware:
    """Activate the tenant named in the X-Tenant header, if the signed-in user belongs to it.

    A tenant the user isn't a member of gets the same 404 as one that doesn't exist, so the
    header can't be used to probe which businesses are on the platform.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        raw = request.headers.get(TENANT_HEADER)
        if not raw:
            return self.get_response(request)
        try:
            public_id = uuid.UUID(raw)
        except ValueError:
            return JsonResponse({"detail": "Not found."}, status=404)
        membership = None
        if request.user.is_authenticated:
            membership = (
                Membership.all_tenants.select_related("tenant", "role")
                .filter(user=request.user, tenant__public_id=public_id)
                .first()
            )
        if membership is None:
            return JsonResponse({"detail": "Not found."}, status=404)
        request.membership = membership  # type: ignore[attr-defined]
        token = current_tenant_var.set(membership.tenant)
        try:
            return self.get_response(request)
        finally:
            current_tenant_var.reset(token)
