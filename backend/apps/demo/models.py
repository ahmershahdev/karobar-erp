from django.db import models

from apps.tenancy.models import Tenant


class DemoBusiness(models.Model):
    """A business made by the seed command. Only these can be wiped, so a real business is
    never touched by a reset."""

    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=10)
    seeded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.kind}: {self.tenant_id}"
