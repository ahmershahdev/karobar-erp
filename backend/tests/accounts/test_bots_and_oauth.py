import importlib.util
import io
import urllib.error
import urllib.request
from collections.abc import Callable
from email.message import Message
from functools import partial
from typing import Any
from urllib.parse import parse_qs, urlparse

import environ
import pytest
from django.core import mail
from django.test import override_settings
from django.utils import timezone
from pytest_django.fixtures import Settings as SettingsWrapper
from rest_framework.test import APIClient

from apps.accounts import humans, oauth
from apps.accounts.models import SocialAccount, User
from apps.platform import http
from config.settings import base
from tests.factories import TEST_PASSWORD, create_user

from .test_flows import form_client

pytestmark = pytest.mark.django_db
Replies = dict[str, Any]


def submit(path: str, body: dict[str, str]) -> Any:
    client, headers = form_client()
    return client.post(path, body, format="json", **headers)  # type: ignore[arg-type]


@pytest.fixture
def captcha(settings: SettingsWrapper, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    """Turn reCAPTCHA on and answer siteverify by token: "good", "low", "v2ok", "wrong-action"."""
    settings.RECAPTCHA_V3_SECRET_KEY = "v3-secret"
    settings.RECAPTCHA_V2_SECRET_KEY = "v2-secret"
    calls: list[dict[str, str]] = []

    def verify(url: str, fields: dict[str, str]) -> dict[str, Any]:
        calls.append(fields)
        token = fields["response"]
        if token == "down":
            raise http.OutboundError("timeout")
        if fields["secret"] == "v2-secret":
            return {"success": token == "v2ok"}
        replies: dict[str, Replies] = {
            "good": {"success": True, "score": 0.9, "action": "signup"},
            "login": {"success": True, "score": 0.9, "action": "login"},
            "low": {"success": True, "score": 0.1, "action": "signup"},
        }
        return replies.get(token, {"success": False})

    monkeypatch.setattr(humans, "post_form", verify)
    return calls


def test_honeypot_answers_like_success_but_does_nothing() -> None:
    body = {"email": "bot@example.test", "password": TEST_PASSWORD, "website": "http://spam"}
    assert submit("/api/accounts/signup/", body).status_code == 202
    assert not User.objects.filter(email="bot@example.test").exists()
    assert mail.outbox == []
    create_user(email="real@example.test")
    trapped = {"email": "real@example.test", "password": TEST_PASSWORD, "website": "x"}
    assert submit("/api/accounts/login/", trapped).status_code == 403
    assert submit("/api/accounts/password-reset/", trapped).status_code == 204
    assert mail.outbox == []


def test_good_v3_score_passes(captcha: list[dict[str, str]]) -> None:
    body = {"email": "person@example.test", "password": TEST_PASSWORD, "captcha_v3": "good"}
    assert submit("/api/accounts/signup/", body).status_code == 202
    assert User.objects.filter(email="person@example.test").exists()
    assert captcha[0]["secret"] == "v3-secret"
    assert "remoteip" in captcha[0]


@pytest.mark.parametrize("token", ["low", "login", "forged", ""])
def test_weak_or_misused_v3_asks_for_the_checkbox(
    captcha: list[dict[str, str]], token: str
) -> None:
    body = {"email": "person@example.test", "password": TEST_PASSWORD, "captcha_v3": token}
    response = submit("/api/accounts/signup/", body)
    assert response.status_code == 400
    assert response.json()["code"] == "captcha_v2_required"
    assert not User.objects.filter(email="person@example.test").exists()


def test_the_v2_checkbox_lets_people_through(captcha: list[dict[str, str]]) -> None:
    body = {"email": "person@example.test", "password": TEST_PASSWORD, "captcha_v2": "v2ok"}
    assert submit("/api/accounts/signup/", body).status_code == 202
    body["captcha_v2"] = "replayed"
    assert submit("/api/accounts/signup/", body).status_code == 400


def test_login_checks_its_own_action(captcha: list[dict[str, str]]) -> None:
    create_user(email="member@example.test")
    body = {"email": "member@example.test", "password": TEST_PASSWORD, "captcha_v3": "login"}
    assert submit("/api/accounts/login/", body).status_code == 200
    body["captcha_v3"] = "good"
    assert submit("/api/accounts/login/", body).status_code == 400


def test_google_outage_fails_closed(captcha: list[dict[str, str]]) -> None:
    body = {"email": "person@example.test", "password": TEST_PASSWORD, "captcha_v3": "down"}
    response = submit("/api/accounts/signup/", body)
    assert response.status_code == 503
    assert response.json()["code"] == "captcha_unavailable"


def test_config_lists_public_keys_and_enabled_providers(settings: SettingsWrapper) -> None:
    settings.RECAPTCHA_V3_SITE_KEY = "site-v3"
    settings.GOOGLE_OAUTH_CLIENT_ID = "gid"
    settings.GOOGLE_OAUTH_CLIENT_SECRET = "gsecret"
    settings.FACEBOOK_APP_ID = "fid"
    settings.FACEBOOK_APP_SECRET = ""
    # A developer's own .env may have the demo switched on.
    settings.DEMO_MODE = False
    body = APIClient().get("/api/accounts/config/").json()
    assert body == {
        "recaptcha_v3_site_key": "site-v3",
        "recaptcha_v2_site_key": "",
        "oauth_providers": ["google"],
        "demo": None,
    }
    assert "gsecret" not in str(body)


# OAuth


@pytest.fixture
def providers(settings: SettingsWrapper) -> None:
    settings.SITE_URL = "https://erp.example.test"
    settings.GOOGLE_OAUTH_CLIENT_ID = "gid"
    settings.GOOGLE_OAUTH_CLIENT_SECRET = "gsecret"
    settings.FACEBOOK_SIGN_IN = True
    settings.FACEBOOK_APP_ID = "fid"
    settings.FACEBOOK_APP_SECRET = "fsecret"


def fake_provider(
    monkeypatch: pytest.MonkeyPatch,
    profile: dict[str, Any],
    token: str = "at",  # noqa: S107
) -> list[str]:
    seen: list[str] = []

    def post(url: str, fields: dict[str, str]) -> dict[str, Any]:
        seen.append(url)
        assert fields["client_secret"] == "gsecret"
        assert fields["code_verifier"]
        return {"access_token": token}

    def get(url: str, bearer: str | None = None) -> dict[str, Any]:
        seen.append(url)
        if "access_token" in url:
            assert "client_secret=fsecret" in url
            return {"access_token": token}
        assert bearer == token
        return profile

    monkeypatch.setattr(oauth, "post_form", post)
    monkeypatch.setattr(oauth, "get_json", get)
    return seen


def sign_in(provider: str, next_path: str = "/app/abc") -> tuple[APIClient, Any]:
    client = APIClient()
    start = client.get(f"/api/accounts/oauth/{provider}/start/?next={next_path}")
    assert start.status_code == 302
    query = parse_qs(urlparse(start["Location"]).query)
    assert query["redirect_uri"] == [
        f"https://erp.example.test/api/accounts/oauth/{provider}/callback/"
    ]
    state = query["state"][0]
    back = client.get(f"/api/accounts/oauth/{provider}/callback/?state={state}&code=c0de")
    return client, back


def test_google_creates_a_verified_user_and_signs_in(
    providers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_provider(
        monkeypatch,
        {"sub": "g-1", "email": "New@Example.test", "email_verified": True, "name": "Asha"},
    )
    client, back = sign_in("google")
    assert back.status_code == 302
    assert back["Location"] == "https://erp.example.test/app/abc"
    user = User.objects.get(email="new@example.test")
    assert user.email_verified_at is not None
    assert not user.has_usable_password()
    assert client.get("/api/accounts/me/").json()["email"] == "new@example.test"
    # The second time the same identity signs in the same user, even if the email changed.
    fake_provider(
        monkeypatch, {"sub": "g-1", "email": "other@example.test", "email_verified": True}
    )
    sign_in("google")
    assert SocialAccount.objects.get().user == user


def test_google_links_an_existing_account_only_with_a_verified_email(
    providers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = create_user(email="owner@example.test")
    fake_provider(
        monkeypatch, {"sub": "g-2", "email": "owner@example.test", "email_verified": False}
    )
    _, back = sign_in("google")
    assert back["Location"].endswith("/login?error=email_in_use")
    fake_provider(
        monkeypatch, {"sub": "g-2", "email": "owner@example.test", "email_verified": True}
    )
    _, back = sign_in("google")
    assert back["Location"] == "https://erp.example.test/app/abc"
    assert SocialAccount.objects.get(uid="g-2").user == existing


def test_google_takes_an_unverified_account_from_whoever_registered_it(
    providers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    squatter = create_user(email="owner@example.test", password="squatter password one")
    assert squatter.email_verified_at is None
    fake_provider(
        monkeypatch, {"sub": "g-3", "email": "owner@example.test", "email_verified": True}
    )
    sign_in("google")
    squatter.refresh_from_db()
    assert squatter.email_verified_at is not None
    assert not squatter.check_password("squatter password one")
    assert not squatter.has_usable_password()


def test_google_removes_a_squatter_who_came_in_through_another_provider(
    providers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    squatter = create_user(email="owner@example.test")
    SocialAccount.objects.create(user=squatter, provider="facebook", uid="fb-1")
    fake_provider(
        monkeypatch, {"sub": "g-5", "email": "owner@example.test", "email_verified": True}
    )
    sign_in("google")
    assert list(squatter.social_accounts.values_list("provider", flat=True)) == ["google"]


def test_google_keeps_the_password_of_a_verified_account(
    providers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = create_user(
        email="owner@example.test",
        password="owner password number one",
        email_verified_at=timezone.now(),
    )
    fake_provider(
        monkeypatch, {"sub": "g-4", "email": "owner@example.test", "email_verified": True}
    )
    sign_in("google")
    owner.refresh_from_db()
    assert owner.check_password("owner password number one")


def test_facebook_never_takes_over_an_existing_email(
    providers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_user(email="owner@example.test")
    seen = fake_provider(monkeypatch, {"id": "f-1", "email": "owner@example.test", "name": "X"})
    _, back = sign_in("facebook")
    assert back["Location"].endswith("error=email_in_use")
    assert any("appsecret_proof=" in url for url in seen)
    fake_provider(monkeypatch, {"id": "f-2", "email": "fresh@example.test", "name": "Fresh"})
    _, back = sign_in("facebook")
    assert back.status_code == 302
    fresh = User.objects.get(email="fresh@example.test")
    assert fresh.email_verified_at is None


@pytest.mark.parametrize(
    ("profile", "error"),
    [({"id": "f-3"}, "email_missing"), ({"email": "x@example.test"}, "oauth_failed")],
)
def test_facebook_profiles_need_an_id_and_email(
    providers: None, monkeypatch: pytest.MonkeyPatch, profile: dict[str, str], error: str
) -> None:
    fake_provider(monkeypatch, profile)
    _, back = sign_in("facebook")
    assert back["Location"].endswith(f"error={error}")


def test_disabled_users_cannot_sign_in(providers: None, monkeypatch: pytest.MonkeyPatch) -> None:
    user = create_user(email="gone@example.test")
    user.is_active = False
    user.save()
    fake_provider(
        monkeypatch, {"sub": "g-9", "email": "gone@example.test", "email_verified": True}
    )
    _, back = sign_in("google")
    assert back["Location"].endswith("error=account_disabled")
    SocialAccount.objects.create(user=user, provider="google", uid="g-10")
    fake_provider(monkeypatch, {"sub": "g-10", "email": "x@example.test", "email_verified": True})
    _, back = sign_in("google")
    assert back["Location"].endswith("error=account_disabled")


def test_callbacks_need_the_state_from_this_browser(
    providers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_provider(monkeypatch, {"sub": "g-1", "email": "a@example.test", "email_verified": True})
    stranger = APIClient()
    back = stranger.get("/api/accounts/oauth/google/callback/?state=guess&code=c")
    assert back["Location"].endswith("error=oauth_state")
    client = APIClient()
    start = client.get("/api/accounts/oauth/google/start/")
    state = parse_qs(urlparse(start["Location"]).query)["state"][0]
    wrong = client.get("/api/accounts/oauth/facebook/callback/?state=" + state + "&code=c")
    assert wrong["Location"].endswith("error=oauth_state")
    client.get("/api/accounts/oauth/google/start/")
    cancelled = APIClient()
    start = cancelled.get("/api/accounts/oauth/google/start/")
    state = parse_qs(urlparse(start["Location"]).query)["state"][0]
    back = cancelled.get(f"/api/accounts/oauth/google/callback/?state={state}&error=access_denied")
    assert back["Location"].endswith("error=oauth_cancelled")
    start = cancelled.get("/api/accounts/oauth/google/start/")
    state = parse_qs(urlparse(start["Location"]).query)["state"][0]
    back = cancelled.get(f"/api/accounts/oauth/google/callback/?state={state}")
    assert back["Location"].endswith("error=oauth_failed")
    assert not User.objects.exists()


def test_facebook_is_off_unless_switched_on(settings: SettingsWrapper) -> None:
    settings.FACEBOOK_SIGN_IN = False
    settings.FACEBOOK_APP_ID = "fid"
    settings.FACEBOOK_APP_SECRET = "fsecret"
    assert "facebook" not in APIClient().get("/api/accounts/config/").json()["oauth_providers"]
    back = APIClient().get("/api/accounts/oauth/facebook/start/")
    assert back["Location"].endswith("error=provider_unavailable")


def test_facebook_stays_off_when_the_setting_is_not_given(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FACEBOOK_SIGN_IN", raising=False)
    monkeypatch.setenv("FACEBOOK_APP_ID", "fid")
    monkeypatch.setenv("FACEBOOK_APP_SECRET", "fsecret")
    monkeypatch.setattr(environ.Env, "read_env", lambda *args, **kwargs: None)
    spec = importlib.util.spec_from_file_location("fresh_base_settings", base.__file__)
    assert spec is not None
    assert spec.loader is not None
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)
    assert fresh.FACEBOOK_APP_ID == "fid"
    assert fresh.FACEBOOK_SIGN_IN is False


def test_unconfigured_or_unknown_providers_bounce_back(settings: SettingsWrapper) -> None:
    settings.FACEBOOK_APP_ID = ""
    for name in ("facebook", "myspace"):
        back = APIClient().get(f"/api/accounts/oauth/{name}/start/")
        assert back["Location"].endswith("error=provider_unavailable")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/app/one", "/app/one"),
        ("/accept-invite?token=abc", "/accept-invite?token=abc"),
        ("https://evil.test", "/app"),
        ("//evil.test", "/app"),
        ("/app//evil.test", "/app"),
        ("/app\\evil", "/app"),
        (None, "/app"),
    ],
)
def test_next_stays_inside_the_app(raw: str | None, expected: str) -> None:
    assert oauth.safe_next(raw) == expected


def test_a_provider_without_a_token_is_a_failure(
    providers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_provider(monkeypatch, {}, token="")
    _, back = sign_in("google")
    assert back["Location"].endswith("error=oauth_failed")

    def down(*args: object, **kwargs: object) -> dict[str, Any]:
        raise http.OutboundError("down")

    monkeypatch.setattr(oauth, "post_form", down)
    _, back = sign_in("google")
    assert back["Location"].endswith("error=oauth_failed")


# The outbound helper


class FakeResponse(io.BytesIO):
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def opener(result: Callable[[], Any]) -> Callable[..., Any]:
    def urlopen(request: Any, timeout: int) -> Any:
        assert timeout == http.TIMEOUT_SECONDS
        return result()

    return urlopen


def test_http_helper_reads_json_objects_and_rejects_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(http.OPENER, "open", opener(lambda: FakeResponse(b'{"a": 1}')))
    assert http.get_json("https://example.test/x", bearer="t") == {"a": 1}
    assert http.post_form("https://example.test/x", {"k": "v"}) == {"a": 1}
    with pytest.raises(http.OutboundError, match="https"):
        http.get_json("http://example.test/x")
    for body, message in ((b"[1]", "object"), (b"nope", "JSON"), (b"x" * 300_000, "large")):
        monkeypatch.setattr(http.OPENER, "open", opener(partial(FakeResponse, body)))
        with pytest.raises(http.OutboundError, match=message):
            http.get_json("https://example.test/x")


def test_redirects_are_refused_so_a_token_cannot_follow_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def redirected() -> Any:
        raise urllib.error.HTTPError(
            "https://example.test", 302, "moved", Message(), io.BytesIO(b"{}")
        )

    monkeypatch.setattr(http.OPENER, "open", opener(redirected))
    with pytest.raises(http.OutboundError, match="redirects"):
        http.get_json("https://example.test/x", bearer="secret")
    handler = http._NoRedirects()
    assert handler.redirect_request() is None


def test_http_errors_still_return_their_json_and_network_errors_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def bad_request() -> Any:
        raise urllib.error.HTTPError(
            "https://example.test",
            400,
            "bad",
            Message(),
            io.BytesIO(b'{"error": "x"}'),
        )

    monkeypatch.setattr(http.OPENER, "open", opener(bad_request))
    assert http.get_json("https://example.test/x") == {"error": "x"}

    def offline() -> Any:
        raise urllib.error.URLError("no route")

    monkeypatch.setattr(http.OPENER, "open", opener(offline))
    with pytest.raises(http.OutboundError):
        http.get_json("https://example.test/x")


@override_settings(RECAPTCHA_V3_SECRET_KEY="", RECAPTCHA_V2_SECRET_KEY="")
def test_without_keys_the_check_is_off() -> None:
    assert not humans.enabled()
    humans.check({}, "signup", None)


def test_two_callbacks_racing_to_link_the_same_identity(
    providers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = create_user(email="owner@example.test", email_verified_at=timezone.now())
    SocialAccount.objects.create(user=user, provider="google", uid="g-9")
    # This callback looked before the other one committed, so it saw no link.
    monkeypatch.setattr(SocialAccount.objects, "select_for_update", SocialAccount.objects.none)
    profile = oauth.Profile(uid="g-9", email="owner@example.test", name="", email_verified=True)
    assert oauth._user_for("google", profile) == user


def test_losing_a_race_leaves_no_account_behind(
    providers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = create_user(email="winner@example.test", email_verified_at=timezone.now())
    SocialAccount.objects.create(user=user, provider="facebook", uid="fb-9")
    monkeypatch.setattr(SocialAccount.objects, "select_for_update", SocialAccount.objects.none)
    profile = oauth.Profile(uid="fb-9", email="other@example.test", name="", email_verified=False)
    assert oauth._user_for("facebook", profile) == user
    assert not User.objects.filter(email="other@example.test").exists()
