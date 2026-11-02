from typing import Any

from rest_framework import serializers

from .models import AuditEvent, Invitation, Membership, Role
from .modules import clean_permissions, permission_problems


class TenantRoleField(serializers.PrimaryKeyRelatedField[Role]):
    # Resolved per request, after the tenant is active, so only this tenant's roles match.
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(queryset=Role.all_tenants.none(), **kwargs)

    def get_queryset(self) -> Any:
        return Role.objects.all()


class MembershipSerializer(serializers.ModelSerializer[Membership]):
    tenant_id = serializers.UUIDField(source="tenant.public_id", read_only=True)
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    role = serializers.CharField(source="role.name", read_only=True, default=None, allow_null=True)
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = ("tenant_id", "tenant_name", "role", "is_owner", "permissions")
        read_only_fields = fields

    def get_permissions(self, membership: Membership) -> dict[str, list[str]]:
        return membership.role.permissions if membership.role else {}


class TenantCreateSerializer(serializers.Serializer[None]):
    name = serializers.CharField(max_length=150)
    base_currency = serializers.RegexField(r"^[A-Z]{3}$", default="PKR")
    locale = serializers.ChoiceField(choices=["en", "ur", "ar"], default="en")
    fiscal_year_start_month = serializers.IntegerField(min_value=1, max_value=12, default=7)
    valuation_method = serializers.ChoiceField(choices=["average", "fifo"], default="average")


class RoleSerializer(serializers.ModelSerializer[Role]):
    permissions = serializers.JSONField()

    class Meta:
        model = Role
        fields = ("id", "name", "permissions")
        read_only_fields = ("id",)
        extra_kwargs = {"name": {"max_length": 80}}

    def validate_permissions(self, value: Any) -> dict[str, list[str]]:
        problems = permission_problems(value)
        if problems:
            raise serializers.ValidationError(problems)
        return clean_permissions(value)


class MemberSerializer(serializers.ModelSerializer[Membership]):
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    role = TenantRoleField(allow_null=True, required=False)
    role_name = serializers.CharField(
        source="role.name", read_only=True, default=None, allow_null=True
    )

    class Meta:
        model = Membership
        fields = ("id", "email", "full_name", "role", "role_name", "is_owner", "created_at")
        read_only_fields = ("id", "email", "full_name", "role_name", "is_owner", "created_at")


class InvitationSerializer(serializers.ModelSerializer[Invitation]):
    role = TenantRoleField(allow_null=True, required=False)
    role_name = serializers.CharField(
        source="role.name", read_only=True, default=None, allow_null=True
    )
    status = serializers.SerializerMethodField()

    class Meta:
        model = Invitation
        fields = ("id", "email", "role", "role_name", "status", "created_at", "expires_at")
        read_only_fields = ("id", "role_name", "status", "created_at", "expires_at")
        extra_kwargs = {"email": {"max_length": 254}}

    def get_status(self, invitation: Invitation) -> str:
        if invitation.accepted_at:
            return "accepted"
        if invitation.revoked_at:
            return "revoked"
        return "pending" if invitation.is_pending else "expired"


class AcceptInvitationSerializer(serializers.Serializer[None]):
    token = serializers.CharField(max_length=128)


class AuditEventSerializer(serializers.ModelSerializer[AuditEvent]):
    user = serializers.EmailField(
        source="user.email", read_only=True, default=None, allow_null=True
    )

    class Meta:
        model = AuditEvent
        fields = ("id", "action", "model", "object_id", "changes", "user", "at")
        read_only_fields = fields
