"""Signal receivers for the accounts app."""

from typing import Any

from django.db import transaction
from django.utils import timezone

from .models import User


def record_last_login(sender: Any, user: User, **kwargs: Any) -> None:
    """Stamp last_login without ever making a sign-in wait for it.

    Django's own receiver saves the user row, and that waits whenever another transaction holds
    a lock on the row. The nightly demo reset seeds each business in one long transaction, and
    every seeded row that points at the demo owner keeps that owner's row locked until it
    commits, so demo sign-ins hung until MySQL's lock wait ran out. A locked row is skipped
    here instead: the timestamp is a nicety, the sign-in is not.
    """
    with transaction.atomic():
        free = (
            User.objects.select_for_update(skip_locked=True)
            .filter(pk=user.pk)
            .values_list("pk", flat=True)
        )
        if not free:
            return
        now = timezone.now()
        User.objects.filter(pk=user.pk).update(last_login=now)
    user.last_login = now
