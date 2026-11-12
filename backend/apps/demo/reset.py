"""Put the demo back: fresh businesses first, then the old ones go, so the demo is never empty."""

import time
from datetime import date

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.tenancy.models import Tenant

from . import data, seed, wipe
from .models import DemoBusiness


class DemoOffError(Exception):
    message = "DEMO_MODE is off. Set DEMO_MODE=true to make demo data."


class NoPasswordError(Exception):
    message = "Set DEMO_PASSWORD for the demo owner's account."


def demo_owner() -> User:
    """The shared demo account. Its password is set from DEMO_PASSWORD on every reset, so a
    visitor who somehow changed it can't keep others out for more than a day."""
    owner = User.objects.filter(email__iexact=settings.DEMO_EMAIL).first()
    if owner is None:
        owner = User.objects.create_user(settings.DEMO_EMAIL, settings.DEMO_PASSWORD)
    else:
        owner.set_password(settings.DEMO_PASSWORD)
    owner.full_name = "Demo owner"
    owner.is_active = True
    owner.email_verified_at = owner.email_verified_at or timezone.now()
    owner.save()
    return owner


def reset(days: int, kinds: list[str] | None = None, today: date | None = None) -> list[str]:
    """Make each demo business again and remove the old copies. Returns a line per business."""
    if not settings.DEMO_MODE:
        raise DemoOffError
    if not settings.DEMO_PASSWORD:
        raise NoPasswordError
    owner = demo_owner()
    old = list(Tenant.objects.filter(pk__in=DemoBusiness.objects.values("tenant")))
    lines = []
    for kind in kinds or list(data.PLANS):
        began = time.monotonic()
        with transaction.atomic():
            tenant, counts = seed.seed(owner, kind, today or timezone.localdate(), days)
        made = ", ".join(f"{value} {key}" for key, value in sorted(counts.items()))
        lines.append(f"{tenant.name}: {made} in {time.monotonic() - began:.0f}s.")
    for tenant in old:
        wipe.wipe(tenant)
    lines.append(f"Removed {len(old)} old demo business(es).")
    return lines
