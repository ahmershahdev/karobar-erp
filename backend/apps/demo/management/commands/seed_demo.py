from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.demo import data, reset


class Command(BaseCommand):
    help = (
        "Replace the demo businesses with fresh ones holding a year of invented documents. "
        "Runs only when DEMO_MODE is on."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--days", type=int, default=None, help="Days of history (default DEMO_DAYS)."
        )
        parser.add_argument(
            "--only", choices=sorted(data.PLANS), help="Make just one of the businesses."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        days: int = settings.DEMO_DAYS if options["days"] is None else options["days"]
        if not 7 <= days <= 400:
            raise CommandError("--days must be between 7 and 400.")
        kinds = [options["only"]] if options["only"] else None
        try:
            lines = reset.reset(days, kinds)
        except (reset.DemoOffError, reset.NoPasswordError) as exc:
            raise CommandError(exc.message) from exc
        for line in lines:
            self.stdout.write(line)
        self.stdout.write(f"Sign in as {settings.DEMO_EMAIL}.")
