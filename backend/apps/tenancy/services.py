"""Every write to tenancy data goes through here, so each one is atomic and audited."""

import hashlib
import secrets
from datetime import timedelta
from typing import Any

from django.db import IntegrityError, models, transaction
from django.utils import timezone

from apps.accounts.models import User

from . import audit
from .context import tenant_context
from .models import AuditEvent, Invitation, Membership, Role, Tenant
from .modules import FULL_ACCESS, READ_ONLY

INVITATION_LIFETIME = timedelta(days=7)
Action = AuditEvent.Action


class TenancyError(Exception):
    """A request that is well formed but not allowed by the rules; shown to the user as is."""


def _snapshot(instance: models.Model, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: getattr(instance, field) for field in fields}


def _diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[Any]]:
    return {key: [before[key], after[key]] for key in before if before[key] != after[key]}


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@transaction.atomic
def create_tenant(owner: User, name: str, base_currency: str, locale: str) -> Membership:
    if owner.email_verified_at is None:
        raise TenancyError("Confirm your email address before creating a business.")
    tenant = Tenant.objects.create(name=name, base_currency=base_currency, locale=locale)
    with tenant_context(tenant):
        Role.objects.create(name="Manager", permissions=FULL_ACCESS)
        Role.objects.create(name="Viewer", permissions=READ_ONLY)
        membership: Membership = Membership.objects.create(user=owner, is_owner=True)
        audit.record(Action.CREATE, tenant, owner, {"name": [None, name]})
    return membership


@transaction.atomic
def save_role(
    actor: User, name: str, permissions: dict[str, list[str]], role: Role | None = None
) -> Role:
    fields = ("name", "permissions")
    before = _snapshot(role, fields) if role else dict.fromkeys(fields)
    target = role or Role(name=name, permissions=permissions)
    target.name, target.permissions = name, permissions
    try:
        with transaction.atomic():
            target.save()
    except IntegrityError as exc:
        raise TenancyError("A role with this name already exists.") from exc
    changes = _diff(before, _snapshot(target, fields))
    audit.record(Action.UPDATE if role else Action.CREATE, target, actor, changes)
    return target


@transaction.atomic
def delete_role(actor: User, role: Role) -> None:
    if (
        Membership.objects.filter(role=role).exists()
        or Invitation.objects.filter(
            role=role, accepted_at__isnull=True, revoked_at__isnull=True
        ).exists()
    ):
        raise TenancyError("Move members and pending invitations off this role first.")
    audit.record(Action.DELETE, role, actor, {"name": [role.name, None]})
    role.delete()


@transaction.atomic
def change_member_role(actor: User, membership: Membership, role: Role | None) -> Membership:
    if membership.is_owner:
        raise TenancyError("The owner's access can't be changed.")
    before = membership.role.name if membership.role else None
    membership.role = role
    membership.save(update_fields=["role"])
    audit.record(Action.UPDATE, membership, actor, {"role": [before, role.name if role else None]})
    return membership


@transaction.atomic
def remove_member(actor: User, membership: Membership) -> None:
    if membership.is_owner:
        raise TenancyError("The owner can't be removed.")
    audit.record(Action.DELETE, membership, actor, {"user": [membership.user.email, None]})
    membership.delete()


@transaction.atomic
def invite(actor: User, tenant: Tenant, email: str, role: Role | None) -> tuple[Invitation, str]:
    email = email.lower()
    # Locking the tenant row serialises invitations per business, so two admins inviting the
    # same address at once can't leave two live links behind.
    Tenant.objects.select_for_update().get(pk=tenant.pk)
    if Membership.objects.filter(user__email=email).exists():
        raise TenancyError("This person is already a member.")
    now = timezone.now()
    Invitation.objects.filter(
        email=email, accepted_at__isnull=True, revoked_at__isnull=True
    ).update(revoked_at=now)
    token = secrets.token_urlsafe(32)
    invitation: Invitation = Invitation.objects.create(
        email=email,
        role=role,
        token_hash=hash_token(token),
        invited_by=actor,
        expires_at=now + INVITATION_LIFETIME,
    )
    audit.record(Action.CREATE, invitation, actor, {"email": [None, email]})
    return invitation, token


@transaction.atomic
def revoke_invitation(actor: User, invitation: Invitation) -> None:
    if invitation.accepted_at is not None:
        raise TenancyError("This invitation was already accepted.")
    invitation.revoked_at = invitation.revoked_at or timezone.now()
    invitation.save(update_fields=["revoked_at"])
    audit.record(Action.DELETE, invitation, actor, {"email": [invitation.email, None]})


@transaction.atomic
def accept_invitation(user: User, token: str) -> Membership:
    invitation = (
        Invitation.all_tenants.select_for_update()
        .select_related("tenant", "role")
        .filter(token_hash=hash_token(token))
        .first()
    )
    if invitation is None or not invitation.is_pending:
        raise TenancyError("This invitation is invalid, used or expired.")
    if invitation.email != user.email.lower():
        raise TenancyError("This invitation was sent to a different email address.")
    if user.email_verified_at is None:
        raise TenancyError("Confirm your email address before joining a business.")
    with tenant_context(invitation.tenant):
        membership: Membership
        membership, created = Membership.objects.get_or_create(
            user=user, defaults={"role": invitation.role}
        )
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=["accepted_at"])
        if created:
            audit.record(Action.CREATE, membership, user, {"user": [None, user.email]})
    return membership
