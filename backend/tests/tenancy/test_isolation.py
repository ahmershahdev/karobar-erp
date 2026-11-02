"""Every endpoint is either public, user-level, or tenant-owned and proven isolated here.

A new URL that isn't listed below fails test_every_endpoint_is_classified, which is the point:
nobody can add an endpoint without deciding how tenants are kept apart on it.
"""

from collections.abc import Callable, Iterator

import pytest
from django.urls import URLPattern, URLResolver, get_resolver

from apps.tenancy import audit
from apps.tenancy.models import AuditEvent, Role, Tenant
from tests.conftest import Member

PUBLIC = {"api/health/", "api/accounts/csrf/", "api/accounts/login/"}
USER_LEVEL = {"api/accounts/logout/", "api/accounts/me/", "api/tenants/", "api/schema/"}

# Each entry builds a row in the given tenant and returns the URL that reads it.
TENANT_OWNED: dict[str, Callable[[Member], str]] = {}


def tenant_endpoint(route: str) -> Callable[[Callable[[Member], str]], Callable[[Member], str]]:
    def register(make_url: Callable[[Member], str]) -> Callable[[Member], str]:
        TENANT_OWNED[route] = make_url
        return make_url

    return register


@tenant_endpoint("api/audit/")
def _audit_list(member: Member) -> str:
    return "/api/audit/"


@tenant_endpoint("api/audit/<int:pk>/")
def _audit_detail(member: Member) -> str:
    role = Role.objects.create(name="Owner role")
    return f"/api/audit/{audit.record(AuditEvent.Action.CREATE, role, member.user).pk}/"


def _routes(resolver: URLResolver, prefix: str = "") -> Iterator[str]:
    for entry in resolver.url_patterns:
        route = prefix + str(entry.pattern)
        if isinstance(entry, URLResolver):
            yield from _routes(entry, route)
        elif isinstance(entry, URLPattern):
            yield route


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
    url = TENANT_OWNED[route](owner)

    mine = owner.client().get(url)
    assert mine.status_code == 200

    theirs = outsider.client().get(url)
    if "<" in route:
        assert theirs.status_code == 404
    else:
        assert theirs.status_code == 200
        assert theirs.json().get("results", theirs.json()) in ([], {})
