import pytest
from django.core import mail, signing
from kombu.exceptions import OperationalError  # type: ignore[import-untyped, unused-ignore]
from rest_framework.test import APIClient

from apps.accounts import emails
from apps.accounts.models import User
from apps.accounts.tokens import CHANGE_EMAIL_SALT, make_email_change_token
from tests.accounts.test_flows import link_params, post
from tests.factories import TEST_PASSWORD, create_user

pytestmark = pytest.mark.django_db

NEW_PASSWORD = "a brand new long passphrase"


def signed_in(user: User) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def test_a_person_can_change_their_name() -> None:
    user = create_user()
    answer = signed_in(user).patch(
        "/api/accounts/me/", {"full_name": "  Asha Khan "}, format="json"
    )
    assert answer.status_code == 200
    assert answer.json()["full_name"] == "Asha Khan"
    user.refresh_from_db()
    assert user.full_name == "Asha Khan"


def test_the_name_can_be_blank_but_not_too_long() -> None:
    client = signed_in(create_user())
    assert client.patch("/api/accounts/me/", {"full_name": ""}, format="json").status_code == 200
    long_name = {"full_name": "x" * 151}
    assert client.patch("/api/accounts/me/", long_name, format="json").status_code == 400


def test_changing_the_password_keeps_this_device_and_signs_out_the_others() -> None:
    user = create_user()
    here, elsewhere = signed_in(user), signed_in(user)
    mail.outbox.clear()
    body = {"current_password": TEST_PASSWORD, "password": NEW_PASSWORD}
    assert here.post("/api/accounts/password/", body, format="json").status_code == 204
    assert here.get("/api/accounts/me/").status_code == 200
    assert elsewhere.get("/api/accounts/me/").status_code == 403
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)
    assert "password was changed" in str(mail.outbox[0].subject)


def test_the_password_needs_the_current_one() -> None:
    user = create_user()
    body = {"current_password": "not my password", "password": NEW_PASSWORD}
    answer = signed_in(user).post("/api/accounts/password/", body, format="json")
    assert answer.status_code == 400
    assert "current_password" in answer.json()
    user.refresh_from_db()
    assert user.check_password(TEST_PASSWORD)


def test_a_weak_new_password_is_refused() -> None:
    body = {"current_password": TEST_PASSWORD, "password": "12345678"}
    answer = signed_in(create_user()).post("/api/accounts/password/", body, format="json")
    assert answer.status_code == 400
    assert "password" in answer.json()


def test_a_google_only_account_is_sent_to_forgot_password() -> None:
    user = create_user()
    user.set_unusable_password()
    user.save()
    client = signed_in(user)
    assert client.get("/api/accounts/me/").json()["has_password"] is False
    body = {"current_password": "", "password": NEW_PASSWORD}
    answer = client.post("/api/accounts/password/", body, format="json")
    assert answer.status_code == 400
    assert "Forgot password" in answer.json()["current_password"][0]


def test_changing_email_waits_for_the_link_sent_to_the_new_address() -> None:
    user = create_user()
    old = user.email
    mail.outbox.clear()
    body = {"email": "New.Address@Example.test", "current_password": TEST_PASSWORD}
    assert signed_in(user).post("/api/accounts/email/", body, format="json").status_code == 202
    user.refresh_from_db()
    assert user.email == old
    sent = mail.outbox[0]
    assert sent.to == ["new.address@example.test"]
    token = link_params(str(sent.body))["token"]
    mail.outbox.clear()
    assert post("/api/accounts/email/confirm/", {"token": token}) == 204
    user.refresh_from_db()
    assert user.email == "new.address@example.test"
    assert user.email_verified_at is not None
    assert mail.outbox[0].to == [old]


def test_an_email_link_works_once() -> None:
    user = create_user()
    token = make_email_change_token(user, "once@example.test")
    assert post("/api/accounts/email/confirm/", {"token": token}) == 204
    assert post("/api/accounts/email/confirm/", {"token": token}) == 400


def test_a_taken_email_looks_the_same_and_tells_its_owner() -> None:
    other = create_user()
    user = create_user()
    mail.outbox.clear()
    body = {"email": other.email.upper(), "current_password": TEST_PASSWORD}
    assert signed_in(user).post("/api/accounts/email/", body, format="json").status_code == 202
    assert mail.outbox[0].to == [other.email]
    assert "nothing was changed" in str(mail.outbox[0].body)


def test_an_address_taken_after_the_link_was_sent_is_refused() -> None:
    user = create_user()
    token = make_email_change_token(user, "race@example.test")
    create_user(email="race@example.test")
    assert post("/api/accounts/email/confirm/", {"token": token}) == 400
    user.refresh_from_db()
    assert user.email != "race@example.test"


def test_changing_email_needs_the_current_password() -> None:
    body = {"email": "x@example.test", "current_password": "wrong"}
    answer = signed_in(create_user()).post("/api/accounts/email/", body, format="json")
    assert answer.status_code == 400
    assert mail.outbox == []


def test_the_same_email_is_refused() -> None:
    user = create_user()
    body = {"email": user.email, "current_password": TEST_PASSWORD}
    assert signed_in(user).post("/api/accounts/email/", body, format="json").status_code == 400


def test_a_forged_or_old_email_link_is_refused() -> None:
    user = create_user()
    forged = signing.dumps(
        {"u": str(user.public_id), "e": user.email, "n": "x@example.test"}, salt="other"
    )
    assert post("/api/accounts/email/confirm/", {"token": forged}) == 400
    assert post("/api/accounts/email/confirm/", {"token": "garbage"}) == 400
    stale = signing.dumps(
        {"u": str(user.public_id), "e": "old@example.test", "n": "y@example.test"},
        salt=CHANGE_EMAIL_SALT,
    )
    assert post("/api/accounts/email/confirm/", {"token": stale}) == 400


def test_settings_need_a_signed_in_person() -> None:
    client = APIClient()
    assert client.patch("/api/accounts/me/", {"full_name": "x"}, format="json").status_code == 403
    assert client.post("/api/accounts/password/", {}, format="json").status_code == 403
    assert client.post("/api/accounts/email/", {}, format="json").status_code == 403


def _queue_down(*_: object) -> None:
    raise OperationalError("broker down")


def test_a_password_change_still_succeeds_when_the_queue_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(emails, "send_password_changed", _queue_down)
    user = create_user()
    body = {"current_password": TEST_PASSWORD, "password": NEW_PASSWORD}
    assert signed_in(user).post("/api/accounts/password/", body, format="json").status_code == 204
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)


def test_an_email_change_still_succeeds_when_the_queue_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(emails, "send_email_changed", _queue_down)
    user = create_user()
    token = make_email_change_token(user, "queue@example.test")
    assert post("/api/accounts/email/confirm/", {"token": token}) == 204
    user.refresh_from_db()
    assert user.email == "queue@example.test"


def test_changing_the_password_ends_a_pending_email_change() -> None:
    user = create_user()
    token = make_email_change_token(user, "attacker@example.test")
    user.set_password(NEW_PASSWORD)
    user.save()
    assert post("/api/accounts/email/confirm/", {"token": token}) == 400
    user.refresh_from_db()
    assert user.email != "attacker@example.test"


def test_an_old_link_stays_dead_when_the_email_comes_back() -> None:
    user = create_user()
    original = user.email
    first = make_email_change_token(user, "second@example.test")
    assert post("/api/accounts/email/confirm/", {"token": first}) == 204
    user.refresh_from_db()
    back = make_email_change_token(user, original)
    assert post("/api/accounts/email/confirm/", {"token": back}) == 204
    user.refresh_from_db()
    assert user.email == original
    assert post("/api/accounts/email/confirm/", {"token": first}) == 400
    user.refresh_from_db()
    assert user.email == original
