"""Every write to tenancy data goes through here, so each one is atomic and audited."""

import hashlib
import secrets
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db import IntegrityError, models, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.platform.locking import lock_rows

from . import audit
from .context import tenant_context
from .models import AuditEvent, Invitation, Membership, Role, Tenant
from .modules import FULL_ACCESS, READ_ONLY
from .signals import tenant_created

INVITATION_LIFETIME = timedelta(days=7)
Action = AuditEvent.Action


class TenancyError(Exception):
    """A request that is well formed but not allowed by the rules.

    Each rule is its own subclass with a fixed `message`. Views show that class attribute, never
    the exception's text, so nothing from a traceback or from user input can reach a response.
    """

    message = "That isn't allowed."


class UnverifiedCreatorError(TenancyError):
    message = "Confirm your email address before creating a business."


class DuplicateRoleError(TenancyError):
    message = "A role with this name already exists."


class RoleInUseError(TenancyError):
    message = "Move members and pending invitations off this role first."


class OwnerRoleFixedError(TenancyError):
    message = "The owner's access can't be changed."


class OwnerNotRemovableError(TenancyError):
    message = "The owner can't be removed."


class AlreadyMemberError(TenancyError):
    message = "This person is already a member."


class InvitationAcceptedError(TenancyError):
    message = "This invitation was already accepted."


class InvitationUnusableError(TenancyError):
    message = "This invitation is invalid, used or expired."


class InvitationForSomeoneElseError(TenancyError):
    message = "This invitation was sent to a different email address."


class UnverifiedInviteeError(TenancyError):
    message = "Confirm your email address before joining a business."


def _snapshot(instance: models.Model, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: getattr(instance, field) for field in fields}


def _diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[Any]]:
    return {key: [before[key], after[key]] for key in before if before[key] != after[key]}


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@transaction.atomic
def create_tenant(
    owner: User,
    name: str,
    base_currency: str,
    locale: str,
    fiscal_year_start_month: int = 7,
    valuation_method: str = "average",
) -> Membership:
    if owner.email_verified_at is None:
        raise UnverifiedCreatorError
    tenant = Tenant.objects.create(
        name=name,
        base_currency=base_currency,
        locale=locale,
        fiscal_year_start_month=fiscal_year_start_month,
        valuation_method=valuation_method,
    )
    with tenant_context(tenant):
        Role.objects.create(name="Manager", permissions=FULL_ACCESS)
        Role.objects.create(name="Viewer", permissions=READ_ONLY)
        membership: Membership = Membership.objects.create(user=owner, is_owner=True)
        audit.record(Action.CREATE, tenant, owner, {"name": [None, name]})
        tenant_created.send(sender=Tenant, tenant=tenant, owner=owner)
    return membership


@transaction.atomic
def save_role(
    actor: User,
    name: str,
    permissions: dict[str, list[str]],
    role: Role | None = None,
    max_discount_percent: Decimal | None = None,
) -> Role:
    """`max_discount_percent` left out keeps the role's limit; a new role starts at none."""
    fields = ("name", "permissions", "max_discount_percent")
    before = _snapshot(role, fields) if role else dict.fromkeys(fields)
    target = role or Role(name=name, permissions=permissions)
    target.name, target.permissions = name, permissions
    if max_discount_percent is not None:
        target.max_discount_percent = max_discount_percent
    try:
        with transaction.atomic():
            target.save()
    except IntegrityError as exc:
        raise DuplicateRoleError from exc
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
        raise RoleInUseError
    audit.record(Action.DELETE, role, actor, {"name": [role.name, None]})
    role.delete()


@transaction.atomic
def change_member_role(actor: User, membership: Membership, role: Role | None) -> Membership:
    if membership.is_owner:
        raise OwnerRoleFixedError
    before = membership.role.name if membership.role else None
    membership.role = role
    membership.save(update_fields=["role"])
    audit.record(Action.UPDATE, membership, actor, {"role": [before, role.name if role else None]})
    return membership


@transaction.atomic
def remove_member(actor: User, membership: Membership) -> None:
    if membership.is_owner:
        raise OwnerNotRemovableError
    audit.record(Action.DELETE, membership, actor, {"user": [membership.user.email, None]})
    membership.delete()


@transaction.atomic
def invite(actor: User, tenant: Tenant, email: str, role: Role | None) -> tuple[Invitation, str]:
    email = email.lower()
    # Locking the tenant row serialises invitations per business, so two admins inviting the
    # same address at once can't leave two live links behind.
    Tenant.objects.select_for_update().get(pk=tenant.pk)
    if Membership.objects.filter(user__email=email).exists():
        raise AlreadyMemberError
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
        raise InvitationAcceptedError
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
        raise InvitationUnusableError
    if invitation.email != user.email.lower():
        raise InvitationForSomeoneElseError
    if user.email_verified_at is None:
        raise UnverifiedInviteeError
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


class NotTheOwnerError(TenancyError):
    message = "Only the owner can hand the business to someone else."


class AlreadyOwnerError(TenancyError):
    message = "This person already owns the business."


class InactiveMemberError(TenancyError):
    message = "This person can no longer sign in, so they can't own the business."


@transaction.atomic
def transfer_ownership(actor: User, target: Membership) -> Membership:
    """Make `target` the owner. The old owner stays a member with no role until given one."""
    current = Membership.objects.filter(user=actor, is_owner=True).first()
    rows = {
        row.pk: row
        for row in lock_rows(
            Membership.objects.filter(pk__in=[target.pk, *([current.pk] if current else [])])
        )
    }
    # Checked again under the lock: two hand-overs at once must not leave two owners.
    if current is None or not rows[current.pk].is_owner:
        raise NotTheOwnerError
    current, target = rows[current.pk], rows[target.pk]
    if target.is_owner:
        raise AlreadyOwnerError
    if not target.user.is_active:
        raise InactiveMemberError
    before = current.role.name if current.role else None
    current.is_owner = False
    current.role = None
    current.save(update_fields=["is_owner", "role"])
    target.is_owner = True
    target.save(update_fields=["is_owner"])
    audit.record(
        Action.UPDATE, current, actor, {"is_owner": [True, False], "role": [before, None]}
    )
    audit.record(Action.UPDATE, target, actor, {"is_owner": [False, True]})
    return target


class OwnsBusinessError(Exception):
    def __init__(self, names: list[str]) -> None:
        super().__init__()
        self.names = names


def former_user_email(user: User) -> str:
    # .invalid can never receive mail, and the address reads as a former user wherever records
    # show who made them.
    return f"former-user-{user.public_id.hex[:12]}@karobar.invalid"


@transaction.atomic
def delete_account(user: User) -> None:
    """Anonymise the person and leave every business.

    The row stays, because posted documents, journal entries and the signed chat must keep
    pointing at whoever made them. Name, email, password and linked sign-ins go, so nothing
    left identifies them and the email can be used for a new account.
    """
    user = lock_rows(User.objects.filter(pk=user.pk))[0]
    memberships = lock_rows(Membership.all_tenants.filter(user=user))
    owned = [row.tenant_id for row in memberships if row.is_owner]
    if owned:
        raise OwnsBusinessError(
            sorted(Tenant.objects.filter(pk__in=owned).values_list("name", flat=True))
        )
    for row in memberships:
        with tenant_context(row.tenant):
            audit.record(Action.DELETE, row, user, {"user": ["a former member", None]})
            row.delete()
    user.social_accounts.all().delete()
    user.email = former_user_email(user)
    user.full_name = ""
    user.email_verified_at = None
    user.is_active = False
    user.set_unusable_password()
    user.save(update_fields=["email", "full_name", "email_verified_at", "is_active", "password"])
