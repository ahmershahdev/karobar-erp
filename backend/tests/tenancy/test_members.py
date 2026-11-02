import re
from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.tenancy import services
from apps.tenancy.context import tenant_context
from apps.tenancy.models import AuditEvent, Invitation, Membership, Role
from apps.tenancy.modules import clean_permissions, permission_problems
from tests.conftest import Member, make_member
from tests.factories import create_user

pytestmark = pytest.mark.django_db


def verified(email: str = "") -> User:
    return create_user(email_verified_at=timezone.now(), **({"email": email} if email else {}))


def signed_in(user: User) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def audit_actions(member: Member) -> list[str]:
    with tenant_context(member.tenant):
        return list(AuditEvent.objects.order_by("id").values_list("action", flat=True))


def test_creating_a_business_needs_a_verified_email() -> None:
    unverified = create_user()
    response = signed_in(unverified).post("/api/tenants/", {"name": "Shop"}, format="json")
    assert response.status_code == 400

    owner = verified()
    response = signed_in(owner).post(
        "/api/tenants/", {"name": "Invented Bazaar", "base_currency": "AED"}, format="json"
    )
    assert response.status_code == 201
    assert response.json()["is_owner"] is True
    membership = Membership.all_tenants.get(user=owner)
    assert membership.tenant.base_currency == "AED"
    assert set(
        Role.all_tenants.filter(tenant=membership.tenant).values_list("name", flat=True)
    ) == {
        "Manager",
        "Viewer",
    }


def test_roles_crud_is_audited_and_validated(owner: Member) -> None:
    client = owner.client()
    bad = client.post(
        "/api/roles/", {"name": "X", "permissions": {"nope": ["view"]}}, format="json"
    )
    assert bad.status_code == 400

    created = client.post(
        "/api/roles/", {"name": "Cashier", "permissions": {"pos": ["post", "view"]}}, format="json"
    )
    assert created.status_code == 201
    assert created.json()["permissions"] == {"pos": ["view", "post"]}
    role_id = created.json()["id"]

    duplicate = client.post("/api/roles/", {"name": "Cashier", "permissions": {}}, format="json")
    assert duplicate.status_code == 400

    renamed = client.patch(f"/api/roles/{role_id}/", {"name": "Till"}, format="json")
    assert renamed.json()["name"] == "Till"
    assert client.delete(f"/api/roles/{role_id}/").status_code == 204
    assert audit_actions(owner) == ["create", "update", "delete"]


def test_a_role_in_use_cannot_be_deleted(owner: Member) -> None:
    with tenant_context(owner.tenant):
        role = Role.objects.create(name="Clerk")
        Membership.objects.create(user=create_user(), role=role)
    assert owner.client().delete(f"/api/roles/{role.pk}/").status_code == 400


def test_invite_accept_flow(owner: Member) -> None:
    client = owner.client()
    with tenant_context(owner.tenant):
        role = Role.objects.create(name="Clerk", permissions={"sales": ["view"]})
    response = client.post(
        "/api/invitations/", {"email": "Guest@Example.test", "role": role.pk}, format="json"
    )
    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    token = re.search(r"token=([\w-]+)", str(mail.outbox[-1].body)).group(1)  # type: ignore[union-attr]

    guest = verified("guest@example.test")
    accepted = signed_in(guest).post("/api/invitations/accept/", {"token": token}, format="json")
    assert accepted.status_code == 200
    assert accepted.json()["role"] == "Clerk"
    assert accepted.json()["permissions"] == {"sales": ["view"]}

    again = signed_in(guest).post("/api/invitations/accept/", {"token": token}, format="json")
    assert again.status_code == 400
    members = client.get("/api/members/").json()["results"]
    assert {m["email"] for m in members} == {owner.user.email, "guest@example.test"}


def test_invitation_rules(owner: Member) -> None:
    with tenant_context(owner.tenant):
        _, token = services.invite(owner.user, owner.tenant, "someone@example.test", None)
    wrong_person = signed_in(verified())
    assert (
        wrong_person.post("/api/invitations/accept/", {"token": token}, format="json").status_code
        == 400
    )

    unverified = create_user(email="someone@example.test")
    assert (
        signed_in(unverified)
        .post("/api/invitations/accept/", {"token": token}, format="json")
        .status_code
        == 400
    )

    with tenant_context(owner.tenant):
        _, token = services.invite(owner.user, owner.tenant, "late@example.test", None)
        Invitation.objects.filter(email="late@example.test").update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
    late = signed_in(verified("late@example.test"))
    assert (
        late.post("/api/invitations/accept/", {"token": token}, format="json").status_code == 400
    )

    duplicate = owner.client().post(
        "/api/invitations/", {"email": owner.user.email}, format="json"
    )
    assert duplicate.status_code == 400


def test_reinviting_revokes_the_old_link_and_revoke_endpoint(owner: Member) -> None:
    with tenant_context(owner.tenant):
        first, _ = services.invite(owner.user, owner.tenant, "twice@example.test", None)
        second, _ = services.invite(owner.user, owner.tenant, "twice@example.test", None)
        first.refresh_from_db()
    assert first.revoked_at is not None
    client = owner.client()
    assert client.delete(f"/api/invitations/{second.pk}/").status_code == 204
    statuses = {
        row["id"]: row["status"] for row in client.get("/api/invitations/").json()["results"]
    }
    assert statuses == {first.pk: "revoked", second.pk: "revoked"}


def test_revoking_an_accepted_invitation_fails(owner: Member) -> None:
    with tenant_context(owner.tenant):
        invitation, token = services.invite(owner.user, owner.tenant, "in@example.test", None)
    services.accept_invitation(verified("in@example.test"), token)
    assert owner.client().delete(f"/api/invitations/{invitation.pk}/").status_code == 400


def test_member_role_change_and_removal(owner: Member) -> None:
    with tenant_context(owner.tenant):
        role = Role.objects.create(name="Clerk")
        member = Membership.objects.create(user=create_user())
    client = owner.client()
    assert (
        client.patch(f"/api/members/{member.pk}/", {"role": role.pk}, format="json").json()[
            "role_name"
        ]
        == "Clerk"
    )
    assert (
        client.patch(f"/api/members/{member.pk}/", {"role": None}, format="json").status_code
        == 200
    )
    owner_row = owner.membership.pk
    assert (
        client.patch(f"/api/members/{owner_row}/", {"role": role.pk}, format="json").status_code
        == 400
    )
    assert client.delete(f"/api/members/{owner_row}/").status_code == 400
    assert client.delete(f"/api/members/{member.pk}/").status_code == 204


def test_roles_from_another_tenant_cannot_be_assigned(owner: Member, outsider: Member) -> None:
    with tenant_context(outsider.tenant):
        foreign = Role.objects.create(name="Foreign")
    response = owner.client().post(
        "/api/invitations/", {"email": "x@example.test", "role": foreign.pk}, format="json"
    )
    assert response.status_code == 400


def test_members_need_permission() -> None:
    viewer = make_member(permissions={"members": ["view"]})
    assert viewer.client().get("/api/members/").status_code == 200
    assert (
        viewer.client()
        .post("/api/invitations/", {"email": "a@example.test"}, format="json")
        .status_code
        == 403
    )


@pytest.mark.parametrize(
    "raw",
    ["not a dict", {"sales": "view"}, {"sales": ["fly"]}, {"sales": [1]}],
)
def test_permission_problems_reports_bad_input(raw: object) -> None:
    assert permission_problems(raw)


def test_clean_permissions_drops_empty_modules() -> None:
    raw = {"sales": [], "audit": ["view"]}
    assert permission_problems(raw) == []
    assert clean_permissions(raw) == {"audit": ["view"]}
