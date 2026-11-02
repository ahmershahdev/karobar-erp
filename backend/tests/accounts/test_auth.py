import pytest
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.models import User
from tests.factories import TEST_PASSWORD

pytestmark = pytest.mark.django_db


def csrf_client() -> tuple[APIClient, str]:
    client = APIClient(enforce_csrf_checks=True)
    response = client.get("/api/accounts/csrf/")
    assert response.status_code == 204
    return client, response.cookies["kb_csrftoken"].value


def test_login_sets_an_httponly_session_and_returns_the_public_id(user: User) -> None:
    client, token = csrf_client()
    response = client.post(
        "/api/accounts/login/",
        {"email": user.email.upper(), "password": TEST_PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 200
    assert response.json()["id"] == str(user.public_id)
    assert response.cookies["kb_session"]["httponly"]
    assert client.get("/api/accounts/me/").json()["email"] == user.email


def test_login_without_a_csrf_token_is_refused(user: User) -> None:
    client = APIClient(enforce_csrf_checks=True)
    response = client.post(
        "/api/accounts/login/", {"email": user.email, "password": TEST_PASSWORD}, format="json"
    )
    assert response.status_code == 403


@pytest.mark.parametrize("known_email", [True, False])
def test_wrong_credentials_get_one_generic_message(user: User, known_email: bool) -> None:
    client, token = csrf_client()
    response = client.post(
        "/api/accounts/login/",
        {"email": user.email if known_email else "nobody@example.test", "password": "nope"},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Email or password is incorrect."


def test_logout_ends_the_session(user: User) -> None:
    client = APIClient()
    client.force_login(user)
    assert client.post("/api/accounts/logout/").status_code == 204
    assert client.get("/api/accounts/me/").status_code == 403


def test_passwords_are_hashed(user: User) -> None:
    assert TEST_PASSWORD not in user.password
    assert user.check_password(TEST_PASSWORD)


def test_create_superuser_lowercases_email_and_email_is_required() -> None:
    admin = User.objects.create_superuser("Boss@Example.TEST", "another long password")
    assert admin.is_staff
    assert admin.is_superuser
    assert admin.email == "boss@example.test"
    assert str(admin) == "boss@example.test"
    with pytest.raises(ValueError, match="email"):
        User.objects.create_user("")


def test_auth_endpoints_are_throttled() -> None:
    ScopedRateThrottle.THROTTLE_RATES = {**ScopedRateThrottle.THROTTLE_RATES, "auth": "3/min"}
    try:
        client = APIClient()
        codes = [client.get("/api/accounts/csrf/").status_code for _ in range(4)]
    finally:
        ScopedRateThrottle.THROTTLE_RATES = {**ScopedRateThrottle.THROTTLE_RATES, "auth": "10/min"}
    assert codes[-1] == 429
