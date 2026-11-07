import logging
from typing import Any, cast

from django.db import transaction
from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from kombu.exceptions import OperationalError  # type: ignore[import-untyped, unused-ignore]
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.emails import app_link
from apps.accounts.models import User
from apps.platform.mail import send_message

from . import audit, services
from .context import get_current_tenant
from .models import AuditEvent, Invitation, Membership, Role
from .permissions import HasModulePermission, IsTenantMember
from .serializers import (
    AcceptInvitationSerializer,
    AuditEventSerializer,
    AutomationSerializer,
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
        raise ValidationError({"detail": type(exc).message}) from exc


class AutomationView(APIView):
    permission_classes = [HasModulePermission]
    module = "members"
    throttle_scope = "tenancy"

    @extend_schema(responses=AutomationSerializer)
    def get(self, request: Request) -> Response:
        return Response(AutomationSerializer(get_current_tenant()).data)

    @extend_schema(request=AutomationSerializer, responses=AutomationSerializer)
    def patch(self, request: Request) -> Response:
        tenant = get_current_tenant()
        body = AutomationSerializer(tenant, data=request.data)
        body.is_valid(raise_exception=True)
        with transaction.atomic():
            before = tenant.daily_summary
            tenant.daily_summary = body.validated_data["daily_summary"]
            tenant.save(update_fields=["daily_summary"])
            audit.record(
                AuditEvent.Action.UPDATE,
                tenant,
                actor(request),
                {"daily_summary": [before, tenant.daily_summary]},
            )
        return Response(AutomationSerializer(tenant).data)


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
            data.validated_data["fiscal_year_start_month"],
            data.validated_data["valuation_method"],
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
            services.save_role,
            actor(self.request),
            data["name"],
            data["permissions"],
            None,
            data.get("max_discount_percent"),
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
            data.get("max_discount_percent"),
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
        send_message(
            invitation.email,
            f"You're invited to {tenant.name} on Karobar ERP",
            f"Join {tenant.name}",
            [f"{actor(self.request).email} invited you to join {tenant.name} on Karobar ERP."],
            ("Accept the invitation", app_link("accept-invite", token=token)),
            "This invitation works for 7 days.",
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


logger = logging.getLogger(__name__)


class MemberOwnerView(APIView):
    """Hand the business to another member. Only the owner can, which the service checks."""

    permission_classes = [IsTenantMember]
    throttle_scope = "tenancy"

    @extend_schema(request=None, responses=MemberSerializer)
    def post(self, request: Request, pk: int) -> Response:
        target = get_object_or_404(Membership.objects.select_related("user", "role"), pk=pk)
        membership = run(services.transfer_ownership, actor(request), target)
        tenant = get_current_tenant()
        try:
            send_message(
                membership.user.email,
                f"You now own {tenant.name} on Karobar ERP",
                f"{tenant.name} is yours",
                [
                    f"{actor(request).email} handed {tenant.name} to you. "
                    "You now have full control."
                ],
                ("Open the business", app_link(f"app/{tenant.slug}")),
                "",
            )
        except OperationalError:
            logger.exception("Could not queue an ownership notice")
        return Response(MemberSerializer(membership).data)
