import time
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.demo import data, seed, wipe


class Command(BaseCommand):
    help = (
        "Replace the demo businesses with fresh ones holding a year of invented documents. "
        "Runs only when DEMO_MODE is on."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--days", type=int, default=365, help="Days of history to make.")
        parser.add_argument(
            "--only", choices=sorted(data.PLANS), help="Make just one of the businesses."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEMO_MODE:
            raise CommandError("DEMO_MODE is off. Set DEMO_MODE=true to make demo data.")
        if not settings.DEMO_PASSWORD:
            raise CommandError("Set DEMO_PASSWORD for the demo owner's account.")
        days: int = options["days"]
        if not 7 <= days <= 400:
            raise CommandError("--days must be between 7 and 400.")
        kinds = [options["only"]] if options["only"] else list(data.PLANS)
        owner = demo_owner()
        removed = wipe.wipe_all()
        self.stdout.write(f"Removed {removed} old demo business(es).")
        today = timezone.localdate()
        for kind in kinds:
            began = time.monotonic()
            with transaction.atomic():
                tenant, counts = seed.seed(owner, kind, today, days)
            made = ", ".join(f"{value} {key}" for key, value in sorted(counts.items()))
            took = time.monotonic() - began
            self.stdout.write(f"{tenant.name}: {made} in {took:.0f}s.")
        self.stdout.write(f"Sign in as {owner.email}.")


def demo_owner() -> User:
    """The shared demo account. Its password is set from DEMO_PASSWORD on every run."""
    owner = User.objects.filter(email=settings.DEMO_EMAIL).first()
    if owner is None:
        owner = User.objects.create_user(settings.DEMO_EMAIL, settings.DEMO_PASSWORD)
    else:
        owner.set_password(settings.DEMO_PASSWORD)
    owner.full_name = "Demo owner"
    owner.is_active = True
    owner.email_verified_at = owner.email_verified_at or timezone.now()
    owner.save()
    return owner
