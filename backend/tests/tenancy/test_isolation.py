"""Every endpoint is either public, user-level, or tenant-owned and proven isolated here.

A new URL that isn't listed below fails test_every_endpoint_is_classified, which is the point:
nobody can add an endpoint without deciding how tenants are kept apart on it.
"""

from collections.abc import Callable, Iterator

import pytest
from django.conf import settings
from django.urls import URLPattern, URLResolver, get_resolver

from apps.tenancy import audit, services
from apps.tenancy.models import AuditEvent, Membership, Role, Tenant
from tests.conftest import Member
from tests.factories import create_user

PUBLIC = {
    "api/health/",
    "api/accounts/csrf/",
    "api/accounts/login/",
    "api/accounts/signup/",
    "api/accounts/verify-email/",
    "api/accounts/password-reset/",
    "api/accounts/password-reset/confirm/",
}
USER_LEVEL = {
    "api/accounts/logout/",
    "api/accounts/me/",
    "api/accounts/verify-email/resend/",
    "api/tenants/",
    "api/invitations/accept/",
    "api/schema/",
}

# Each entry creates a row in the member's tenant and returns (url, id of that row). Detail
# urls must be 404 for an outsider; list urls must not contain the row.
TENANT_OWNED: dict[str, Callable[[Member], tuple[str, int]]] = {}


def tenant_endpoint(
    route: str,
) -> Callable[[Callable[[Member], tuple[str, int]]], Callable[[Member], tuple[str, int]]]:
    def register(make: Callable[[Member], tuple[str, int]]) -> Callable[[Member], tuple[str, int]]:
        TENANT_OWNED[route] = make
        return make

    return register


def _event(member: Member) -> int:
    role = Role.objects.create(name="Audited")
    event: AuditEvent = audit.record(AuditEvent.Action.CREATE, role, member.user)
    return event.pk


def _role(member: Member) -> int:
    role: Role = Role.objects.create(name="Private role")
    return role.pk


def _member(member: Member) -> int:
    membership: Membership = Membership.objects.create(user=create_user())
    return membership.pk


def _invitation(member: Member) -> int:
    invitation, _ = services.invite(member.user, member.tenant, "hidden@example.test", None)
    return invitation.pk


def _register(prefix: str, make_row: Callable[[Member], int]) -> None:
    def collection(member: Member) -> tuple[str, int]:
        return f"/api/{prefix}/", make_row(member)

    def detail(member: Member) -> tuple[str, int]:
        pk = make_row(member)
        return f"/api/{prefix}/{pk}/", pk

    tenant_endpoint(f"api/{prefix}/")(collection)
    tenant_endpoint(f"api/{prefix}/<int:pk>/")(detail)


_register("audit", _event)
_register("roles", _role)
_register("members", _member)
_register("invitations", _invitation)


def _routes(resolver: URLResolver, prefix: str = "") -> Iterator[str]:
    for entry in resolver.url_patterns:
        route = prefix + str(entry.pattern)
        if isinstance(entry, URLResolver):
            yield from _routes(entry, route)
        elif isinstance(entry, URLPattern):
            yield route


def _views(resolver: URLResolver, prefix: str = "") -> Iterator[tuple[str, object]]:
    for entry in resolver.url_patterns:
        route = prefix + str(entry.pattern)
        if isinstance(entry, URLResolver):
            yield from _views(entry, route)
        elif isinstance(entry, URLPattern):
            yield route, getattr(entry.callback, "cls", None)


def test_every_api_view_has_a_throttle_scope() -> None:
    rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    for route, view in _views(get_resolver()):
        if not route.startswith("api/") or route == "api/schema/":
            continue
        scope = getattr(view, "throttle_scope", None)
        assert scope in rates, f"{route} needs a throttle_scope with a rate in settings"


def test_every_endpoint_is_classified() -> None:
    api_routes = {r for r in _routes(get_resolver()) if r.startswith("api/")}
    classified = PUBLIC | USER_LEVEL | set(TENANT_OWNED)
    assert api_routes - classified == set(), "classify new endpoints in test_isolation.py"
    assert classified - api_routes == set(), "remove deleted endpoints from test_isolation.py"


@pytest.mark.django_db
@pytest.mark.parametrize("route", sorted(TENANT_OWNED))
def test_other_tenants_rows_are_invisible(
    route: str, owner: Member, outsider: Member, in_tenant: Callable[[Tenant], None]
) -> None:
    in_tenant(owner.tenant)
    url, row_id = TENANT_OWNED[route](owner)

    mine = owner.client().get(url)
    assert mine.status_code == 200

    theirs = outsider.client().get(url)
    if "<" in route:
        assert theirs.status_code == 404
        for method in ("patch", "delete"):
            assert getattr(outsider.client(), method)(url, {}, format="json").status_code in (
                404,
                405,
            )
    else:
        assert theirs.status_code == 200
        body = theirs.json()
        rows = body["results"] if isinstance(body, dict) else body
        assert row_id not in [row["id"] for row in rows]
