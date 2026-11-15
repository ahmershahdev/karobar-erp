"""People and businesses the end-to-end tests sign in as. Run by seed.mjs through
`manage.py shell`, after the demo businesses are made. Safe to run again."""

import os

from django.utils import timezone

from apps.accounts.models import User
from apps.tenancy import services
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Membership, Role, Tenant

PASSWORD = os.environ["E2E_PASSWORD"]


def person(email: str, name: str) -> User:
    user, _ = User.objects.get_or_create(email=email, defaults={"full_name": name})
    user.email_verified_at = user.email_verified_at or timezone.now()
    user.set_password(PASSWORD)
    user.save()
    return user


def business(owner: User, name: str, currency: str = "PKR") -> Tenant:
    tenant = Tenant.objects.filter(name=name).first()
    if tenant is None:
        tenant = services.create_tenant(owner, name, currency, "en").tenant
    return tenant


def member(tenant: Tenant, user: User, role: str, permissions: dict[str, list[str]]) -> None:
    with tenant_context(tenant):
        found, _ = Role.objects.get_or_create(name=role, defaults={"permissions": permissions})
        Membership.objects.get_or_create(user=user, defaults={"role": found})


# No business yet: the journey test makes one through the screens.
person("fresh@e2e.test", "Fresh Owner")

shop = business(person("boss@e2e.test", "Seeded Boss"), "Seeded Shop")
member(
    shop,
    person("cashier@e2e.test", "Seeded Cashier"),
    "Counter only",
    {"pos": ["view", "create", "post"]},
)
# Another business entirely, for checking that one business never sees another.
business(person("rival@e2e.test", "Rival Owner"), "Rival Shop")


# Fifty staff of the demo store for the load tests (loadtest/): many people working in one
# business is what puts its stock, numbering and books under contention.
store = Tenant.objects.get(name__startswith="Noor Kiryana")
with tenant_context(store):
    manager = Role.objects.get(name="Manager")
    for number in range(1, 51):
        staff = person(f"load{number}@e2e.test", f"Load Staff {number}")
        Membership.objects.get_or_create(user=staff, defaults={"role": manager})
print("load test staff are ready")
print("e2e people are ready")
