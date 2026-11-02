from collections.abc import Callable

import pytest
from django.core.exceptions import PermissionDenied
from rest_framework.test import APIClient

from apps.tenancy import audit
from apps.tenancy.context import TenantNotSetError
from apps.tenancy.models import AuditEvent, Role, Tenant
from tests.conftest import Member, make_member

pytestmark = pytest.mark.django_db


def test_scoped_manager_fails_closed_without_a_tenant(owner: Member) -> None:
    with pytest.raises(TenantNotSetError):
        list(Role.objects.all())


def test_scoped_manager_only_sees_the_active_tenant(
    owner: Member, outsider: Member, in_tenant: Callable[[Tenant], None]
) -> None:
    in_tenant(owner.tenant)
    Role.objects.create(name="Cashier")
    assert list(Role.objects.values_list("name", flat=True)) == ["Cashier"]
    assert Role.all_tenants.filter(tenant=outsider.tenant).count() == 0


def test_saving_another_tenants_row_is_refused(
    owner: Member, outsider: Member, in_tenant: Callable[[Tenant], None]
) -> None:
    in_tenant(outsider.tenant)
    role = Role.objects.create(name="Clerk")
    in_tenant(owner.tenant)
    role.name = "Hijacked"
    with pytest.raises(PermissionDenied):
        role.save()


def test_unknown_or_foreign_tenant_header_is_404(owner: Member, outsider: Member) -> None:
    client = owner.client()
    client.credentials(HTTP_X_TENANT=str(outsider.tenant.public_id))
    assert client.get("/api/audit/").status_code == 404
    client.credentials(HTTP_X_TENANT="not-a-uuid")
    assert client.get("/api/audit/").status_code == 404
    anonymous = APIClient()
    anonymous.credentials(HTTP_X_TENANT=str(owner.tenant.public_id))
    assert anonymous.get("/api/audit/").status_code == 404


def test_my_tenants_lists_only_my_memberships(owner: Member, outsider: Member) -> None:
    client = APIClient()
    client.force_login(owner.user)
    body = client.get("/api/tenants/").json()
    assert [row["tenant_id"] for row in body] == [str(owner.tenant.public_id)]
    assert body[0]["is_owner"] is True
    assert str(owner.tenant) == owner.tenant.name


def test_audit_record_and_listing(owner: Member, in_tenant: Callable[[Tenant], None]) -> None:
    in_tenant(owner.tenant)
    role = Role.objects.create(name="Storekeeper")
    event = audit.record(AuditEvent.Action.CREATE, role, owner.user, {"name": [None, "x"]})
    audit.record(AuditEvent.Action.UPDATE, role, None)
    client = owner.client()
    rows = client.get("/api/audit/").json()["results"]
    assert {row["action"] for row in rows} == {"create", "update"}
    detail = client.get(f"/api/audit/{event.pk}/").json()
    assert detail["user"] == owner.user.email
    assert detail["model"] == "tenancy.Role"


def test_module_permissions_follow_the_role(in_tenant: Callable[[Tenant], None]) -> None:
    viewer = make_member(permissions={"audit": ["view"]})
    nobody = make_member(permissions={"sales": ["view"]})
    assert viewer.client().get("/api/audit/").status_code == 200
    assert nobody.client().get("/api/audit/").status_code == 403
    no_header = APIClient()
    no_header.force_login(viewer.user)
    assert no_header.get("/api/audit/").status_code == 403
