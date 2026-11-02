from typing import Any

import pytest
from django.db import OperationalError, transaction
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.platform.locking import lock_rows, retry_on_deadlock

pytestmark = pytest.mark.django_db


def test_health_is_public_and_checks_the_database() -> None:
    response = APIClient().get("/api/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_reports_a_broken_database(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*args: Any, **kwargs: Any) -> None:
        raise ConnectionError

    monkeypatch.setattr("apps.platform.views.connection.cursor", broken)
    assert APIClient().get("/api/health/").status_code == 503


def test_security_headers_are_set() -> None:
    response = APIClient().get("/api/health/")
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["X-Frame-Options"] == "DENY"
    assert response["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response["Cross-Origin-Opener-Policy"] == "same-origin"
    assert response["Cache-Control"] == "no-store"
    assert "camera=()" in response["Permissions-Policy"]
    csp = response["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in csp
    assert "unsafe-inline" not in csp


def test_request_id_is_echoed_only_when_well_formed() -> None:
    client = APIClient()
    good = client.get("/api/health/", HTTP_X_REQUEST_ID="abcdef12-3456")
    assert good["X-Request-ID"] == "abcdef12-3456"
    bad = client.get("/api/health/", HTTP_X_REQUEST_ID="evil log line!")
    assert bad["X-Request-ID"] != "evil log line!"
    assert len(bad["X-Request-ID"]) == 32


def test_unhandled_errors_hide_details(monkeypatch: pytest.MonkeyPatch, user: User) -> None:
    def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("SELECT secret FROM other_tenant")

    monkeypatch.setattr("apps.accounts.views.MeSerializer", boom)
    client = APIClient(raise_request_exception=False)
    client.force_login(user)
    response = client.get("/api/accounts/me/")
    assert response.status_code == 500
    assert "secret" not in response.content.decode()
    assert "request_id" in response.json()


@pytest.mark.django_db(transaction=True)
def test_lock_rows_refuses_to_run_outside_a_transaction(user: User) -> None:
    with pytest.raises(RuntimeError, match="atomic"):
        lock_rows(User.objects.all())


def test_lock_rows_returns_rows_in_primary_key_order(user: User) -> None:
    second = User.objects.create_user("second@example.test", "another long password")
    with transaction.atomic():
        assert lock_rows(User.objects.order_by("-pk")) == [user, second]


def _flaky(failures: list[int]) -> Any:
    calls = {"n": 0}

    def call() -> str:
        calls["n"] += 1
        if failures:
            raise OperationalError(failures.pop(0), "lock trouble")
        return f"done after {calls['n']}"

    return call


@pytest.mark.django_db(transaction=True)
def test_retry_on_deadlock_starts_over() -> None:
    assert retry_on_deadlock(_flaky([1213, 1205]))() == "done after 3"
    with pytest.raises(OperationalError):
        retry_on_deadlock(_flaky([1213, 1213, 1213]))()
    with pytest.raises(OperationalError):
        retry_on_deadlock(_flaky([2006]))()


def test_retry_on_deadlock_leaves_outer_transactions_alone() -> None:
    with pytest.raises(OperationalError), transaction.atomic():
        retry_on_deadlock(_flaky([1213]))()
