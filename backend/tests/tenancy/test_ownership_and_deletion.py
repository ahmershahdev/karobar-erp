from collections.abc import Iterator

import pytest
from django.core import mail
from rest_framework.test import APIClient

from apps.accounts.models import SocialAccount, User
from apps.tenancy import services
from apps.tenancy.context import tenant_context
from apps.tenancy.models import AuditEvent, Membership
from tests.accounts.test_flows import post
from tests.conftest import Member, make_member
from tests.factories import TEST_PASSWORD, create_membership, create_role, create_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner() -> Iterator[Member]:
    member = make_member(owner=True)
    with tenant_context(member.tenant):
        yield member


def staff(of: Member) -> Member:
    with tenant_context(of.tenant):
        membership = create_membership(role=create_role(permissions={"sales": ["view"]}))
    return Member(user=membership.user, tenant=of.tenant, membership=membership)


def delete(user: User, **body: str) -> tuple[int, dict[str, object]]:
    client = APIClient()
    client.force_login(user)
    payload = {"current_password": TEST_PASSWORD, "email": user.email, **body}
    answer = client.post("/api/accounts/delete/", payload, format="json")
    return answer.status_code, (answer.json() if answer.content else {})


def test_the_owner_can_hand_the_business_to_a_member(owner: Member) -> None:
    clerk = staff(owner)
    mail.outbox.clear()
    answer = owner.client().post(f"/api/members/{clerk.membership.pk}/make-owner/")
    assert answer.status_code == 200
    assert answer.json()["is_owner"] is True
    old, new = (
        Membership.objects.get(pk=owner.membership.pk),
        Membership.objects.get(pk=clerk.membership.pk),
    )
    assert (old.is_owner, old.role) == (False, None)
    assert new.is_owner is True
    assert AuditEvent.objects.filter(model="tenancy.Membership", action="update").count() == 2
    assert mail.outbox[0].to == [clerk.user.email]


def test_only_the_owner_can_hand_over(owner: Member) -> None:
    clerk, other = staff(owner), staff(owner)
    answer = clerk.client().post(f"/api/members/{other.membership.pk}/make-owner/")
    assert answer.status_code == 400
    assert Membership.objects.get(pk=owner.membership.pk).is_owner is True
    assert Membership.objects.get(pk=other.membership.pk).is_owner is False


def test_the_owner_cannot_hand_over_to_themselves(owner: Member) -> None:
    answer = owner.client().post(f"/api/members/{owner.membership.pk}/make-owner/")
    assert answer.status_code == 400
    assert Membership.objects.get(pk=owner.membership.pk).is_owner is True


def test_a_member_who_cannot_sign_in_cannot_become_owner(owner: Member) -> None:
    clerk = staff(owner)
    User.objects.filter(pk=clerk.user.pk).update(is_active=False)
    answer = owner.client().post(f"/api/members/{clerk.membership.pk}/make-owner/")
    assert answer.status_code == 400
    assert Membership.objects.get(pk=owner.membership.pk).is_owner is True


def test_after_handing_over_the_old_owner_can_be_removed(owner: Member) -> None:
    clerk = staff(owner)
    owner.client().post(f"/api/members/{clerk.membership.pk}/make-owner/")
    answer = clerk.client().delete(f"/api/members/{owner.membership.pk}/")
    assert answer.status_code == 204


def test_deleting_an_account_removes_the_person_and_keeps_the_records(owner: Member) -> None:
    clerk = staff(owner)
    user = clerk.user
    with tenant_context(owner.tenant):
        role = create_role(name="Made by clerk")
        event = AuditEvent.objects.create(user=user, action="create", model="x", object_id="1")
    SocialAccount.objects.create(user=user, provider="google", uid="g-1")
    old_email = user.email
    mail.outbox.clear()

    code, _ = delete(user)

    assert code == 204
    user.refresh_from_db()
    assert user.email.startswith("former-user-")
    assert user.email.endswith("@karobar.invalid")
    assert user.full_name == ""
    assert user.is_active is False
    assert not user.has_usable_password()
    assert not SocialAccount.objects.filter(user=user).exists()
    assert not Membership.all_tenants.filter(user=user).exists()
    assert AuditEvent.all_tenants.filter(pk=event.pk, user=user).exists()
    assert role.pk is not None
    assert mail.outbox[0].to == [old_email]
    assert "a former member" in str(
        AuditEvent.all_tenants.filter(model="tenancy.Membership", action="delete").last().changes  # type: ignore[union-attr]
    )


def test_a_deleted_account_is_signed_out_everywhere(owner: Member) -> None:
    clerk = staff(owner)
    elsewhere = APIClient()
    elsewhere.force_login(clerk.user)
    assert delete(clerk.user)[0] == 204
    assert elsewhere.get("/api/accounts/me/").status_code == 403


def test_the_email_can_be_used_again_after_deleting(owner: Member) -> None:
    clerk = staff(owner)
    email = clerk.user.email
    assert delete(clerk.user)[0] == 204
    body = {"email": email, "password": "another long new passphrase", "full_name": "New"}
    assert post("/api/accounts/signup/", body) == 202
    assert User.objects.filter(email=email, is_active=True).exists()


def test_an_owner_must_hand_over_first(owner: Member) -> None:
    code, body = delete(owner.user)
    assert code == 400
    assert owner.tenant.name in str(body["detail"])
    owner.user.refresh_from_db()
    assert owner.user.is_active is True
    assert Membership.all_tenants.filter(user=owner.user).exists()


def test_deleting_needs_the_password_and_the_typed_email() -> None:
    user = create_user()
    assert delete(user, current_password="wrong")[0] == 400
    assert delete(user, email="someone@else.test")[0] == 400
    user.refresh_from_db()
    assert user.is_active is True


def test_the_typed_email_ignores_case_and_spaces() -> None:
    user = create_user()
    assert delete(user, email=f"  {user.email.upper()} ")[0] == 204


def test_a_google_only_account_sets_a_password_first() -> None:
    user = create_user()
    user.set_unusable_password()
    user.save()
    code, body = delete(user, current_password="")
    assert code == 400
    assert "Forgot password" in str(body["current_password"])


def test_a_person_in_no_business_can_delete() -> None:
    user = create_user()
    assert delete(user)[0] == 204
    user.refresh_from_db()
    assert user.email == services.former_user_email(user)
