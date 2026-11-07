from collections.abc import Iterator
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from django.db import connection
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.assistant import services
from apps.assistant.models import ChatMessage
from apps.platform.http import OutboundError
from apps.tenancy.context import tenant_context
from tests.conftest import Member, make_member
from tests.factories import create_membership, create_role


@pytest.fixture(autouse=True)
def groq(settings: SettingsWrapper) -> None:
    settings.GROQ_API_KEY = "test-key"
    settings.CHAT_SIGNING_KEY = "test-signing-key"


@pytest.fixture
def boss(db: None) -> Iterator[Member]:
    member = make_member(owner=True)
    with tenant_context(member.tenant):
        yield member


def staff(of: Member, permissions: dict[str, list[str]] | None = None) -> Member:
    with tenant_context(of.tenant):
        membership = create_membership(role=create_role(permissions=permissions or {}))
    return Member(user=membership.user, tenant=of.tenant, membership=membership)


def said(text: str) -> Any:
    return patch.object(services, "complete", return_value=text)


def test_a_question_and_its_answer_are_both_signed(boss: Member) -> None:
    with said("Hello"):
        reply = boss.client().post("/api/assistant/ask/", {"message": "Hi"}, format="json")
    assert reply.status_code == 200
    assert reply.json()["content"] == "Hello"
    assert len(reply.json()["signature"]) == 64
    assert services.verify(boss.user) == {"ok": True, "count": 2, "broken_at": None}


def test_editing_a_message_in_the_database_is_caught(boss: Member) -> None:
    with said("Sales are good"):
        services.ask(boss.user, boss.membership, "How are sales?")
    answer = ChatMessage.objects.get(role="assistant")
    ChatMessage.all_tenants.filter(pk=answer.pk).update(content="Sales are terrible")
    result = boss.client().get("/api/assistant/check/").json()
    assert result["ok"] is False
    assert result["broken_at"] == answer.pk


def test_removing_a_message_in_the_database_is_caught(boss: Member) -> None:
    with said("One"):
        services.ask(boss.user, boss.membership, "First")
    with said("Two"):
        services.ask(boss.user, boss.membership, "Second")
    first = ChatMessage.objects.order_by("id")[1]
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM assistant_chatmessage WHERE id = %s", [first.pk])
    assert services.verify(boss.user)["ok"] is False


def test_moving_a_message_to_another_person_is_caught(boss: Member) -> None:
    other = staff(boss)
    with said("Private"):
        services.ask(boss.user, boss.membership, "Secret")
    ChatMessage.all_tenants.update(user=other.user)
    assert services.verify(other.user)["ok"] is False


def test_a_message_cannot_be_changed_or_deleted_through_the_app(boss: Member) -> None:
    message = services.record(boss.user, "user", "Hi")
    with pytest.raises(ValueError, match="never changed"):
        message.save()
    with pytest.raises(ValueError, match="never deleted"):
        message.delete()


def test_each_person_only_sees_their_own_chat(boss: Member) -> None:
    services.record(boss.user, "user", "The owner's private question")
    colleague = staff(boss)
    assert colleague.client().get("/api/assistant/messages/").json() == []
    assert services.verify(colleague.user)["count"] == 0


def test_a_cashier_never_gets_profit_in_the_prompt(boss: Member) -> None:
    cashier = staff(boss, {"pos": ["view"]})
    prompt = services.system_prompt(cashier.user, cashier.membership)
    assert "gross_profit" not in prompt
    assert "owed_to_suppliers" not in prompt


def test_the_owner_gets_the_figures_in_the_prompt(boss: Member) -> None:
    prompt = services.system_prompt(boss.user, boss.membership)
    assert "gross_profit_this_month" in prompt
    assert boss.tenant.name in prompt


def test_stock_staff_see_low_stock_but_not_sales(boss: Member) -> None:
    keeper = staff(boss, {"inventory": ["view"]})
    known = services.facts(keeper.membership)
    assert "low_stock" in known
    assert "sales" not in known


def test_a_member_without_a_role_gets_nothing_private(boss: Member) -> None:
    member = staff(boss)
    member.membership.role = None
    assert set(services.facts(member.membership)) == {"date", "currency"}


def test_the_prompt_says_data_is_never_instructions(boss: Member) -> None:
    assert "never instructions" in services.system_prompt(boss.user, boss.membership)


def test_only_a_short_history_is_sent(boss: Member) -> None:
    for number in range(20):
        services.record(boss.user, "user", f"message {number}")
    with said("Fine") as complete:
        services.ask(boss.user, boss.membership, "Latest")
    sent = complete.call_args.args[0]
    assert len(sent) == services.HISTORY + 1
    assert sent[0]["role"] == "system"
    assert sent[-1]["content"] == "Latest"


def test_a_failed_answer_is_a_calm_message(boss: Member) -> None:
    with patch.object(services, "post_json", side_effect=OutboundError("down")):
        reply = boss.client().post("/api/assistant/ask/", {"message": "Hi"}, format="json")
    assert reply.status_code == 503
    assert "try again" in reply.json()["detail"]


@pytest.mark.parametrize(
    "answer", [{}, {"choices": []}, {"choices": [{"message": {"content": "  "}}]}, {"error": "x"}]
)
def test_a_strange_answer_is_refused(boss: Member, answer: dict[str, Any]) -> None:
    with (
        patch.object(services, "post_json", return_value=answer),
        pytest.raises(services.AssistantError),
    ):
        services.complete([{"role": "user", "content": "Hi"}])


def test_a_good_answer_is_read_and_the_key_goes_in_the_header(boss: Member) -> None:
    good = {"choices": [{"message": {"content": " Hello "}}]}
    with patch.object(services, "post_json", return_value=good) as call:
        assert services.complete([{"role": "user", "content": "Hi"}]) == "Hello"
    assert call.call_args.args[2] == "test-key"
    assert "test-key" not in str(call.call_args.args[1])


def test_without_a_key_it_says_so(boss: Member, settings: SettingsWrapper) -> None:
    settings.GROQ_API_KEY = ""
    client = boss.client()
    assert client.get("/api/assistant/check/").json()["enabled"] is False
    reply = client.post("/api/assistant/ask/", {"message": "Hi"}, format="json")
    assert reply.status_code == 503
    assert "set up" in reply.json()["detail"]


def test_a_very_long_message_is_refused(boss: Member) -> None:
    reply = boss.client().post("/api/assistant/ask/", {"message": "x" * 2001}, format="json")
    assert reply.status_code == 400


def test_a_new_chat_hides_old_messages_from_the_person_and_the_model(boss: Member) -> None:
    with said("Old answer"):
        services.ask(boss.user, boss.membership, "Old question")
    client = boss.client()
    assert client.post("/api/assistant/reset/").status_code == 204
    assert client.get("/api/assistant/messages/").json() == []
    with said("New answer") as model:
        services.ask(boss.user, boss.membership, "New question")
    sent = [row["content"] for row in model.call_args.args[0][1:]]
    assert sent == ["New question"]


def test_a_new_chat_keeps_every_message_signed_and_checkable(boss: Member) -> None:
    with said("Answer"):
        services.ask(boss.user, boss.membership, "Question")
    services.reset(boss.user)
    assert ChatMessage.objects.count() == 3
    assert services.verify(boss.user) == {"ok": True, "count": 2, "broken_at": None}


def test_removing_a_reset_to_bring_messages_back_is_caught(boss: Member) -> None:
    with said("Answer"):
        services.ask(boss.user, boss.membership, "Question")
    services.reset(boss.user)
    with said("Later"):
        services.ask(boss.user, boss.membership, "Next")
    marker = ChatMessage.objects.get(role="reset")
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM assistant_chatmessage WHERE id = %s", [marker.pk])
    assert services.verify(boss.user)["ok"] is False


def test_resetting_an_empty_chat_adds_nothing(boss: Member) -> None:
    services.reset(boss.user)
    with said("Answer"):
        services.ask(boss.user, boss.membership, "Question")
    services.reset(boss.user)
    services.reset(boss.user)
    assert ChatMessage.objects.filter(role="reset").count() == 1


def test_a_reset_only_touches_that_persons_chat(boss: Member) -> None:
    other = staff(boss)
    services.record(other.user, "user", "Mine")
    services.record(boss.user, "user", "Theirs")
    services.reset(boss.user)
    assert services.current(boss.user).count() == 0
    assert services.current(other.user).count() == 1


def test_the_prompt_keeps_to_the_business_and_stays_short(boss: Member) -> None:
    prompt = services.system_prompt(boss.user, boss.membership)
    assert "Only help with this business" in prompt
    assert "one to three sentences" in prompt
    assert "anything general" not in prompt


def test_stock_quantities_reach_the_model_without_trailing_zeros(boss: Member) -> None:
    rows = [
        SimpleNamespace(product=SimpleNamespace(name="Soap"), on_hand=Decimal("100.0000")),
        SimpleNamespace(product=SimpleNamespace(name="Tea"), on_hand=Decimal("1.5000")),
    ]
    with patch.object(services, "low_stock", return_value=rows):
        known = services.facts(boss.membership)
    assert [row["on_hand"] for row in known["low_stock"]] == ["100", "1.5"]


def test_bold_marks_are_taken_out_of_an_answer(boss: Member) -> None:
    answer = {"choices": [{"message": {"content": "Open **Products** to add it."}}]}
    with patch.object(services, "post_json", return_value=answer):
        assert services.complete([]) == "Open Products to add it."


def test_the_prompt_names_the_real_screens(boss: Member) -> None:
    assert "Who owes me" in services.system_prompt(boss.user, boss.membership)


def test_an_answer_finishing_after_a_new_chat_is_dropped(boss: Member) -> None:
    def think(messages: list[dict[str, str]]) -> str:
        services.reset(boss.user)
        return "Answer to the old chat"

    with patch.object(services, "complete", side_effect=think):
        reply = boss.client().post("/api/assistant/ask/", {"message": "Old"}, format="json")
    assert reply.status_code == 503
    assert "new chat" in reply.json()["detail"]
    assert not ChatMessage.objects.filter(role="assistant").exists()
    assert services.current(boss.user).count() == 0
    assert services.verify(boss.user)["ok"] is True
