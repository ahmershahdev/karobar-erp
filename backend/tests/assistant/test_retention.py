import importlib.util
from datetime import timedelta
from unittest.mock import patch

import environ
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from apps.assistant import services, tasks
from apps.assistant.models import ChatChainStart, ChatJob, ChatMessage
from apps.core.chain import sign
from config.settings import base
from tests.assistant.test_assistant import boss, staff  # noqa: F401
from tests.conftest import Member

pytestmark = pytest.mark.django_db


def written(member: Member, content: str, days_ago: int) -> ChatMessage:
    message = services.record(member.user, ChatMessage.Role.USER, content)
    # Backdated for the test; the signature covers the time, so it is signed again in order.
    when = timezone.now() - timedelta(days=days_ago)
    ChatMessage.all_tenants.filter(pk=message.pk).update(created_at=when)
    return message


def resign(member: Member) -> None:
    """Sign the backdated chain again, as if each message had been written at its new time."""
    previous = ""
    for row in services.mine(member.user).order_by("id"):
        signature = sign(services._key(), services._fields(row), previous)
        ChatMessage.all_tenants.filter(pk=row.pk).update(signature=signature)
        previous = signature


def chat(member: Member) -> None:
    for content, days in (("Old one", 200), ("Old two", 100), ("New one", 30), ("New two", 1)):
        written(member, content, days)
    resign(member)
    assert services.verify(member.user)["ok"] is True


def test_messages_past_ninety_days_go_and_the_rest_still_check(boss: Member) -> None:  # noqa: F811
    chat(boss)
    assert tasks.clear_old_chats() == 2
    kept = list(services.mine(boss.user).order_by("id").values_list("content", flat=True))
    assert kept == ["New one", "New two"]
    assert services.verify(boss.user) == {"ok": True, "count": 2, "broken_at": None}
    assert tasks.clear_old_chats() == 0
    services.record(boss.user, ChatMessage.Role.USER, "Newest")
    assert services.verify(boss.user)["ok"] is True


def test_moving_the_start_to_hide_more_is_caught(boss: Member) -> None:  # noqa: F811
    chat(boss)
    tasks.clear_old_chats()
    first = services.mine(boss.user).order_by("id").first()
    assert first is not None
    ChatChainStart.objects.update(after_id=first.pk)
    ChatMessage.objects.filter(pk=first.pk).delete()
    assert services.verify(boss.user)["ok"] is False


def test_removing_the_start_is_caught(boss: Member) -> None:  # noqa: F811
    chat(boss)
    tasks.clear_old_chats()
    ChatChainStart.objects.all().delete()
    result = services.verify(boss.user)
    assert result["ok"] is False
    assert result["broken_at"] == services.mine(boss.user).order_by("id").first().pk


def test_a_start_left_with_nothing_after_it_is_still_checked(boss: Member) -> None:  # noqa: F811
    written(boss, "Old", 200)
    resign(boss)
    tasks.clear_old_chats()
    assert services.verify(boss.user) == {"ok": True, "count": 0, "broken_at": None}
    ChatChainStart.objects.update(previous="0" * 64)
    assert services.verify(boss.user)["ok"] is False


def test_the_keep_time_is_a_setting(boss: Member, settings: object) -> None:  # noqa: F811
    chat(boss)
    settings.CHAT_KEEP_DAYS = 365  # type: ignore[attr-defined]
    assert tasks.clear_old_chats() == 0


def test_a_new_message_after_everything_was_cleared_still_checks(boss: Member) -> None:  # noqa: F811
    written(boss, "Old", 200)
    resign(boss)
    assert tasks.clear_old_chats() == 1
    services.record(boss.user, ChatMessage.Role.USER, "Hello again")
    assert services.verify(boss.user) == {"ok": True, "count": 1, "broken_at": None}


def test_a_newer_message_written_before_an_older_one_is_kept(boss: Member) -> None:  # noqa: F811
    # A clock that went back: the lower id is newer than the cutoff, the higher one older.
    written(boss, "Recent", 10)
    written(boss, "Dated old", 200)
    resign(boss)
    assert tasks.clear_old_chats() == 0
    assert services.mine(boss.user).count() == 2


def test_only_messages_are_counted_not_their_jobs(boss: Member) -> None:  # noqa: F811
    question = written(boss, "Old question", 200)
    ChatJob.objects.create(user=boss.user, question=question)
    resign(boss)
    assert tasks.clear_old_chats() == 1
    assert not ChatJob.objects.exists()


def test_one_person_failing_does_not_stop_the_others(boss: Member) -> None:  # noqa: F811
    chat(boss)
    real = services.clear_before
    seen: list[int] = []

    def flaky(user: object, cutoff: object) -> int:
        seen.append(user.pk)  # type: ignore[attr-defined]
        if len(seen) == 1:
            raise RuntimeError("boom")
        return real(user, cutoff)  # type: ignore[arg-type]

    other = staff(boss)
    written(other, "Other old", 200)
    resign(other)
    with (
        patch.object(services, "clear_before", side_effect=flaky),
        pytest.raises(RuntimeError, match="not cleared"),
    ):
        tasks.clear_old_chats()
    # The owner comes first and fails; the other person is still cleared.
    assert seen == [boss.user.pk, other.user.pk]
    assert services.mine(boss.user).count() == 4
    assert not services.mine(other.user).exists()


@pytest.mark.parametrize("days", ["0", "-1"])
def test_a_keep_time_below_one_day_stops_the_server(
    monkeypatch: pytest.MonkeyPatch, days: str
) -> None:
    monkeypatch.setenv("CHAT_KEEP_DAYS", days)
    monkeypatch.setattr(environ.Env, "read_env", lambda *args, **kwargs: None)
    spec = importlib.util.spec_from_file_location("fresh_base_settings", base.__file__)
    assert spec is not None
    assert spec.loader is not None
    with pytest.raises(ImproperlyConfigured, match="CHAT_KEEP_DAYS"):
        spec.loader.exec_module(importlib.util.module_from_spec(spec))


def test_a_backdated_message_is_not_cleared_and_stays_as_evidence(boss: Member) -> None:  # noqa: F811
    first = services.record(boss.user, ChatMessage.Role.USER, "Recent one")
    services.record(boss.user, ChatMessage.Role.USER, "Recent two")
    # Someone without the key backdates a message to have it cleared.
    old = timezone.now() - timedelta(days=200)
    ChatMessage.all_tenants.filter(pk=first.pk).update(created_at=old)
    with pytest.raises(services.ChainBrokenError):
        services.clear_before(boss.user, timezone.now() - timedelta(days=90))
    assert services.mine(boss.user).count() == 2
    assert not ChatChainStart.objects.exists()
    assert services.verify(boss.user)["ok"] is False


def test_a_changed_start_stops_the_next_clear(boss: Member) -> None:  # noqa: F811
    chat(boss)
    tasks.clear_old_chats()
    ChatChainStart.objects.update(cleared_at=timezone.now() - timedelta(days=1))
    # A cutoff in the future makes the kept messages due without touching their signatures,
    # so only the changed start can stop the clear.
    with pytest.raises(services.ChainBrokenError):
        services.clear_before(boss.user, timezone.now() + timedelta(days=1))
    assert services.mine(boss.user).count() == 2
