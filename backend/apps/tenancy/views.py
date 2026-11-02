from django.db.models import QuerySet
from rest_framework import generics

from .models import AuditEvent, Membership
from .permissions import HasModulePermission
from .serializers import AuditEventSerializer, MembershipSerializer


class MyTenantsView(generics.ListAPIView[Membership]):
    serializer_class = MembershipSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[Membership]:
        # Not tenant-scoped on purpose: this is the list the tenant switcher picks from.
        return (
            Membership.all_tenants.select_related("tenant", "role")
            .filter(user=self.request.user)
            .order_by("tenant__name")
        )


class AuditEventListView(generics.ListAPIView[AuditEvent]):
    serializer_class = AuditEventSerializer
    permission_classes = [HasModulePermission]
    module = "audit"

    def get_queryset(self) -> QuerySet[AuditEvent]:
        return AuditEvent.objects.select_related("user")


class AuditEventDetailView(generics.RetrieveAPIView[AuditEvent]):
    serializer_class = AuditEventSerializer
    permission_classes = [HasModulePermission]
    module = "audit"

    def get_queryset(self) -> QuerySet[AuditEvent]:
        return AuditEvent.objects.select_related("user")
