from typing import Any, cast

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.emails import app_link
from apps.accounts.models import User
from apps.platform.tasks import send_email

from . import services
from .context import get_current_tenant
from .models import AuditEvent, Invitation, Membership, Role
from .permissions import HasModulePermission
from .serializers import (
    AcceptInvitationSerializer,
    AuditEventSerializer,
    InvitationSerializer,
    MemberSerializer,
    MembershipSerializer,
    RoleSerializer,
    TenantCreateSerializer,
)


def actor(request: Request) -> User:
    return cast(User, request.user)


def run(call: Any, *args: Any) -> Any:
    try:
        return call(*args)
    except services.TenancyError as exc:
        raise ValidationError({"detail": str(exc)}) from exc


class MyTenantsView(generics.ListAPIView[Membership]):
    serializer_class = MembershipSerializer
    throttle_scope = "tenancy"
    pagination_class = None

    def get_queryset(self) -> QuerySet[Membership]:
        # Not tenant-scoped on purpose: this is the list the tenant switcher picks from.
        return (
            Membership.all_tenants.select_related("tenant", "role")
            .filter(user=self.request.user)
            .order_by("tenant__name")
        )

    @extend_schema(request=TenantCreateSerializer, responses={201: MembershipSerializer})
    def post(self, request: Request) -> Response:
        data = TenantCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        membership = run(
            services.create_tenant,
            actor(request),
            data.validated_data["name"],
            data.validated_data["base_currency"],
            data.validated_data["locale"],
        )
        return Response(MembershipSerializer(membership).data, status=status.HTTP_201_CREATED)


class RoleListView(generics.ListCreateAPIView[Role]):
    serializer_class = RoleSerializer
    throttle_scope = "tenancy"
    permission_classes = [HasModulePermission]
    module = "roles"
    pagination_class = None

    def get_queryset(self) -> QuerySet[Role]:
        return Role.objects.order_by("name")

    def perform_create(self, serializer: RoleSerializer) -> None:  # type: ignore[override]
        data = serializer.validated_data
        serializer.instance = run(
            services.save_role, actor(self.request), data["name"], data["permissions"]
        )


class RoleDetailView(generics.RetrieveUpdateDestroyAPIView[Role]):
    serializer_class = RoleSerializer
    throttle_scope = "tenancy"
    permission_classes = [HasModulePermission]
    module = "roles"

    def get_queryset(self) -> QuerySet[Role]:
        return Role.objects.all()

    def perform_update(self, serializer: RoleSerializer) -> None:  # type: ignore[override]
        role = cast(Role, serializer.instance)
        data = serializer.validated_data
        run(
            services.save_role,
            actor(self.request),
            data.get("name", role.name),
            data.get("permissions", role.permissions),
            role,
        )

    def perform_destroy(self, instance: Role) -> None:
        run(services.delete_role, actor(self.request), instance)


class MemberListView(generics.ListAPIView[Membership]):
    serializer_class = MemberSerializer
    throttle_scope = "tenancy"
    permission_classes = [HasModulePermission]
    module = "members"

    def get_queryset(self) -> QuerySet[Membership]:
        return Membership.objects.select_related("user", "role")


class MemberDetailView(generics.RetrieveUpdateDestroyAPIView[Membership]):
    serializer_class = MemberSerializer
    throttle_scope = "tenancy"
    permission_classes = [HasModulePermission]
    module = "members"
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[Membership]:
        return Membership.objects.select_related("user", "role")

    def perform_update(self, serializer: MemberSerializer) -> None:  # type: ignore[override]
        membership = cast(Membership, serializer.instance)
        role = serializer.validated_data.get("role", membership.role)
        run(services.change_member_role, actor(self.request), membership, role)

    def perform_destroy(self, instance: Membership) -> None:
        run(services.remove_member, actor(self.request), instance)


class InvitationListView(generics.ListCreateAPIView[Invitation]):
    serializer_class = InvitationSerializer
    throttle_scope = "tenancy"
    permission_classes = [HasModulePermission]
    module = "members"

    def get_queryset(self) -> QuerySet[Invitation]:
        return Invitation.objects.select_related("role")

    def perform_create(self, serializer: InvitationSerializer) -> None:  # type: ignore[override]
        tenant = get_current_tenant()
        invitation, token = run(
            services.invite,
            actor(self.request),
            tenant,
            serializer.validated_data["email"],
            serializer.validated_data.get("role"),
        )
        serializer.instance = invitation
        send_email.delay(
            invitation.email,
            f"You're invited to {tenant.name} on Karobar ERP",
            f"{actor(self.request).email} invited you to join {tenant.name}.\n\n"
            f"Accept within 7 days:\n\n{app_link('accept-invite', token=token)}",
        )


class InvitationDetailView(generics.RetrieveDestroyAPIView[Invitation]):
    serializer_class = InvitationSerializer
    throttle_scope = "tenancy"
    permission_classes = [HasModulePermission]
    module = "members"

    def get_queryset(self) -> QuerySet[Invitation]:
        return Invitation.objects.select_related("role")

    def perform_destroy(self, instance: Invitation) -> None:
        run(services.revoke_invitation, actor(self.request), instance)


class AcceptInvitationView(APIView):
    throttle_scope = "auth"

    @extend_schema(request=AcceptInvitationSerializer, responses={200: MembershipSerializer})
    def post(self, request: Request) -> Response:
        data = AcceptInvitationSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        membership = run(services.accept_invitation, actor(request), data.validated_data["token"])
        return Response(MembershipSerializer(membership).data)


class AuditEventListView(generics.ListAPIView[AuditEvent]):
    serializer_class = AuditEventSerializer
    throttle_scope = "tenancy"
    permission_classes = [HasModulePermission]
    module = "audit"

    def get_queryset(self) -> QuerySet[AuditEvent]:
        return AuditEvent.objects.select_related("user")


class AuditEventDetailView(generics.RetrieveAPIView[AuditEvent]):
    serializer_class = AuditEventSerializer
    throttle_scope = "tenancy"
    permission_classes = [HasModulePermission]
    module = "audit"

    def get_queryset(self) -> QuerySet[AuditEvent]:
        return AuditEvent.objects.select_related("user")
