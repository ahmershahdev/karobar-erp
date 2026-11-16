import threading
import time

import pytest
from django.db import connection, transaction
from rest_framework.test import APIClient

from apps.accounts.models import User
from tests.factories import TEST_PASSWORD, create_user


def sign_in(email: str) -> int:
    client = APIClient()
    response = client.post(
        "/api/accounts/login/", {"email": email, "password": TEST_PASSWORD}, format="json"
    )
    return response.status_code


@pytest.mark.django_db
def test_sign_in_records_last_login(user: User) -> None:
    assert user.last_login is None
    assert sign_in(user.email) == 200
    user.refresh_from_db()
    assert user.last_login is not None


@pytest.mark.django_db(transaction=True)
def test_sign_in_does_not_wait_while_another_transaction_locks_the_user() -> None:
    # The demo reset holds the owner's row like this for the whole of a long seed.
    user = create_user()
    locked = threading.Event()
    release = threading.Event()

    def hold_lock() -> None:
        try:
            with transaction.atomic():
                list(User.objects.select_for_update().filter(pk=user.pk))
                locked.set()
                release.wait(30)
        finally:
            connection.close()

    holder = threading.Thread(target=hold_lock)
    holder.start()
    try:
        assert locked.wait(10)
        began = time.monotonic()
        assert sign_in(user.email) == 200
        assert time.monotonic() - began < 3
    finally:
        release.set()
        holder.join()
    user.refresh_from_db()
    assert user.last_login is None
