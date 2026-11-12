from datetime import timedelta

import pytest
from django.utils import timezone

from apps.assistant import services, tasks
from apps.assistant.models import ChatChainStart, ChatMessage
from apps.core.chain import sign
from tests.assistant.test_assistant import boss  # noqa: F401
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
