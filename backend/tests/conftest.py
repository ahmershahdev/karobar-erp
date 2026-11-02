from collections.abc import Callable, Iterator
from contextvars import Token
from dataclasses import dataclass

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.tenancy.context import current_tenant_var
from apps.tenancy.models import Membership, Tenant

from .factories import create_membership, create_role, create_tenant, create_user


@dataclass
class Member:
    user: User
    tenant: Tenant
    membership: Membership

    def client(self) -> APIClient:
        client = APIClient()
        client.force_login(self.user)
        client.credentials(HTTP_X_TENANT=str(self.tenant.public_id))
        return client


def make_member(permissions: dict[str, list[str]] | None = None, owner: bool = False) -> Member:
    tenant = create_tenant()
    token = current_tenant_var.set(tenant)
    try:
        role = None if owner else create_role(permissions=permissions or {})
        membership = create_membership(role=role, is_owner=owner)
    finally:
        current_tenant_var.reset(token)
    return Member(user=membership.user, tenant=tenant, membership=membership)


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    # Throttle counters live in the cache; without this, tests would throttle each other.
    cache.clear()


@pytest.fixture
def owner(db: None) -> Member:
    return make_member(owner=True)


@pytest.fixture
def outsider(db: None) -> Member:
    return make_member(owner=True)


@pytest.fixture
def in_tenant() -> Iterator[Callable[[Tenant], None]]:
    tokens: list[Token[Tenant | None]] = []

    def activate(tenant: Tenant) -> None:
        tokens.append(current_tenant_var.set(tenant))

    yield activate
    for token in reversed(tokens):
        current_tenant_var.reset(token)


@pytest.fixture
def user(db: None) -> User:
    return create_user()
