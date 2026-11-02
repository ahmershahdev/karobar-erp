from rest_framework import serializers

from .models import AuditEvent, Membership


class MembershipSerializer(serializers.ModelSerializer[Membership]):
    tenant_id = serializers.UUIDField(source="tenant.public_id", read_only=True)
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    role = serializers.CharField(source="role.name", read_only=True, default=None)

    class Meta:
        model = Membership
        fields = ("tenant_id", "tenant_name", "role", "is_owner")
        read_only_fields = fields


class AuditEventSerializer(serializers.ModelSerializer[AuditEvent]):
    user = serializers.EmailField(source="user.email", read_only=True, default=None)

    class Meta:
        model = AuditEvent
        fields = ("id", "action", "model", "object_id", "changes", "user", "at")
        read_only_fields = fields
