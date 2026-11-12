from typing import Any
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone
from pytest_django.fixtures import Settings as SettingsWrapper
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.demo import guard, tasks
from apps.platform import mail
from tests.conftest import Member, make_member

pytestmark = pytest.mark.django_db

DEMO = "demo@example.com"


@pytest.fixture
def demo_mode(settings: SettingsWrapper) -> SettingsWrapper:
    settings.DEMO_MODE = True
    settings.DEMO_EMAIL = DEMO
    settings.DEMO_PASSWORD = "an invented demo passphrase"
    return settings


def demo_member() -> Member:
    member = make_member(owner=True)
    User.objects.filter(pk=member.user.pk).update(email=DEMO, email_verified_at=timezone.now())
    member.user.refresh_from_db()
    return member


BLOCKED: list[tuple[str, str, dict[str, Any]]] = [
    ("patch", "me", {}),
    ("post", "password-change", {}),
    ("post", "email-change", {}),
    ("post", "email-change-confirm", {}),
    ("post", "account-delete", {}),
    ("post", "my-tenants", {}),
    ("post", "member-owner", {"pk": 1}),
    ("post", "invitation-list", {}),
    ("post", "invitation-accept", {}),
    ("post", "assistant-ask", {}),
    ("post", "assistant-confirm", {"pk": 1}),
]


@pytest.mark.parametrize(("method", "name", "kwargs"), BLOCKED)
def test_the_demo_account_cannot_change_itself_or_reach_out(
    demo_mode: SettingsWrapper, method: str, name: str, kwargs: dict[str, Any]
) -> None:
    reply = getattr(demo_member().client(), method)(reverse(name, kwargs=kwargs), {}, "json")
    assert reply.status_code == 403
    assert reply.json() == {"detail": guard.MESSAGE, "code": "demo_account"}


def test_the_demo_account_can_still_read_and_sign_out(demo_mode: SettingsWrapper) -> None:
    client = demo_member().client()
    assert client.get(reverse("me")).status_code == 200
    assert client.get(reverse("my-tenants")).status_code == 200
    assert client.post(reverse("logout")).status_code in {200, 204}


def test_other_people_and_other_servers_are_not_touched(demo_mode: SettingsWrapper) -> None:
    someone = make_member(owner=True)
    reply = someone.client().post(reverse("password-change"), {}, "json")
    assert reply.json().get("code") != "demo_account"
    demo_mode.DEMO_MODE = False
    reply = demo_member().client().post(reverse("password-change"), {}, "json")
    assert reply.json().get("code") != "demo_account"


def test_the_sign_in_page_shows_the_demo_login_only_on_a_demo_server(
    demo_mode: SettingsWrapper,
) -> None:
    config = APIClient().get(reverse("auth-config")).json()
    assert config["demo"] == {"email": DEMO, "password": "an invented demo passphrase"}
    demo_mode.DEMO_MODE = False
    assert APIClient().get(reverse("auth-config")).json()["demo"] is None


def test_nothing_is_emailed_to_the_demo_address(demo_mode: SettingsWrapper) -> None:
    with patch("apps.platform.mail.send_email.delay") as sent:
        mail.send_message("DEMO@example.com", "Hi", "Hi", ["Body"])
        mail.send_message("someone@example.com", "Hi", "Hi", ["Body"])
    assert [call.args[0] for call in sent.call_args_list] == ["someone@example.com"]


def test_the_nightly_reset_does_nothing_outside_demo_mode(settings: SettingsWrapper) -> None:
    settings.DEMO_MODE = False
    assert tasks.reset_demo() == []
