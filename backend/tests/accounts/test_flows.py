import re
from urllib.parse import parse_qs, urlparse

import pytest
from django.core import mail
from django.utils import timezone
from kombu.exceptions import OperationalError
from rest_framework.test import APIClient

from apps.accounts import emails
from apps.accounts.models import User
from apps.accounts.tokens import make_email_token
from tests.factories import TEST_PASSWORD, create_user

pytestmark = pytest.mark.django_db

NEW_PASSWORD = "a brand new long passphrase"


def link_params(message_body: str) -> dict[str, str]:
    match = re.search(r"https?://\S+", message_body)
    assert match, message_body
    return {key: values[0] for key, values in parse_qs(urlparse(match.group()).query).items()}


def form_client() -> tuple[APIClient, dict[str, str]]:
    client = APIClient(enforce_csrf_checks=True)
    token = client.get("/api/accounts/csrf/").cookies["kb_csrftoken"].value
    return client, {"HTTP_X_CSRFTOKEN": token}


def post(path: str, body: dict[str, str]) -> int:
    client, headers = form_client()
    return client.post(path, body, format="json", **headers).status_code  # type: ignore[arg-type]


def test_sign_up_sends_a_verification_link_that_works() -> None:
    body = {"email": "New@Example.test", "password": TEST_PASSWORD, "full_name": "Asha"}
    assert post("/api/accounts/signup/", body) == 202
    user = User.objects.get(email="new@example.test")
    assert user.email_verified_at is None
    assert len(mail.outbox) == 1

    token = link_params(str(mail.outbox[0].body))["token"]
    assert post("/api/accounts/verify-email/", {"token": token}) == 204
    user.refresh_from_db()
    assert user.email_verified_at is not None


def test_sign_up_with_a_taken_email_looks_the_same(user: User) -> None:
    body = {"email": user.email, "password": TEST_PASSWORD}
    assert post("/api/accounts/signup/", body) == 202
    assert User.objects.filter(email=user.email).count() == 1
    assert "already has a Karobar account" in str(mail.outbox[0].body)


def test_sign_up_rejects_weak_passwords() -> None:
    client, headers = form_client()
    response = client.post(
        "/api/accounts/signup/",
        {"email": "weak@example.test", "password": "12345678"},
        format="json",
        **headers,  # type: ignore[arg-type]
    )
    assert response.status_code == 400
    assert "password" in response.json()
    assert not User.objects.filter(email="weak@example.test").exists()


def test_sign_up_needs_csrf() -> None:
    client = APIClient(enforce_csrf_checks=True)
    body = {"email": "x@example.test", "password": TEST_PASSWORD}
    assert client.post("/api/accounts/signup/", body, format="json").status_code == 403


def test_verification_link_dies_when_the_email_changes(user: User) -> None:
    token = make_email_token(user)
    user.email = "changed@example.test"
    user.save()
    assert post("/api/accounts/verify-email/", {"token": token}) == 400
    assert post("/api/accounts/verify-email/", {"token": "garbage"}) == 400


def test_resend_verification_only_for_unverified(user: User) -> None:
    client = APIClient()
    client.force_login(user)
    assert client.post("/api/accounts/verify-email/resend/").status_code == 204
    user.email_verified_at = timezone.now()
    user.save()
    assert client.post("/api/accounts/verify-email/resend/").status_code == 204
    assert len(mail.outbox) == 1


def test_an_account_from_google_can_set_a_password_by_reset(user: User) -> None:
    user.set_unusable_password()
    user.save(update_fields=["password"])

    assert post("/api/accounts/password-reset/", {"email": user.email}) == 204
    confirm = {**link_params(str(mail.outbox[0].body)), "password": NEW_PASSWORD}
    assert post("/api/accounts/password-reset/confirm/", confirm) == 204

    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)


def test_password_reset_round_trip_signs_out_other_sessions(user: User) -> None:
    other_session = APIClient()
    other_session.force_login(user)

    assert post("/api/accounts/password-reset/", {"email": user.email}) == 204
    params = link_params(str(mail.outbox[0].body))
    confirm = {**params, "password": NEW_PASSWORD}
    assert post("/api/accounts/password-reset/confirm/", confirm) == 204

    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)
    assert user.email_verified_at is not None
    assert other_session.get("/api/accounts/me/").status_code == 403
    assert post("/api/accounts/password-reset/confirm/", confirm) == 400, "links work once"


def test_password_reset_says_nothing_when_the_queue_is_down(
    user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(_: User) -> None:
        raise OperationalError("broker down")

    monkeypatch.setattr(emails, "send_password_reset", fail)
    assert post("/api/accounts/password-reset/", {"email": user.email}) == 204


def test_password_reset_for_unknown_email_says_nothing() -> None:
    assert post("/api/accounts/password-reset/", {"email": "ghost@example.test"}) == 204
    assert mail.outbox == []


@pytest.mark.parametrize(
    ("uid", "token"), [("bad", "bad"), ("", "x"), ("MTIz", "1-abc"), ("!!!", "x")]
)
def test_password_reset_confirm_rejects_bad_links(uid: str, token: str) -> None:
    body = {"uid": uid, "token": token, "password": NEW_PASSWORD}
    assert post("/api/accounts/password-reset/confirm/", body) == 400


def test_password_reset_confirm_checks_strength(user: User) -> None:
    assert post("/api/accounts/password-reset/", {"email": user.email}) == 204
    params = link_params(str(mail.outbox[0].body))
    assert post("/api/accounts/password-reset/confirm/", {**params, "password": "short"}) == 400


def test_me_reports_verification(user: User) -> None:
    client = APIClient()
    client.force_login(create_user(email_verified_at=timezone.now()))
    assert client.get("/api/accounts/me/").json()["email_verified"] is True
