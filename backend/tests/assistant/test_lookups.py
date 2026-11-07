import json
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.assistant import lookups, services
from apps.assistant.models import ChatMessage
from apps.purchasing.models import Supplier
from apps.sales import services as sales
from apps.tenancy.context import tenant_context
from tests.assistant.conftest import staff_in
from tests.conftest import Member
from tests.sales.test_sales import Seller, make_seller

D = Decimal


def look(tool: str, name: str) -> services.ToolCall:
    return services.ToolCall(tool, json.dumps({"name": name}), "call-1")


def found(member: Member, tool: str, name: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = json.loads(
        lookups.run(member.membership, tool, json.dumps({"name": name}))
    )["found"]
    return result


def names(member: Member) -> set[str]:
    return {tool["function"]["name"] for tool in lookups.tools(member.membership)}


def test_a_lookup_result_reaches_the_model_and_the_answer_is_kept(seller: Seller) -> None:
    replies = [look("look_up_product", "soap"), "You have 20 soap at 150 each."]
    with patch.object(services, "complete", side_effect=replies) as complete:
        reply = seller.shop.member.client().post(
            "/api/assistant/ask/", {"message": "How much soap?"}, format="json"
        )
    assert reply.json()["content"] == "You have 20 soap at 150 each."
    sent = complete.call_args_list[1].args[0]
    assert sent[-2]["tool_calls"][0]["function"]["name"] == "look_up_product"
    assert sent[-1]["role"] == "tool"
    assert sent[-1]["tool_call_id"] == "call-1"
    result = json.loads(sent[-1]["content"])["found"][0]
    assert result["sale_price_per_unit"] == "150"
    assert result["on_hand_total"] == "20"
    assert result["on_hand_by_warehouse"] == {"Main store": "20"}
    assert result["packs"] == [{"unit": "CTN", "units_in_pack": "12"}]
    # Only the question and the answer are kept; the lookup itself is not part of the chat.
    assert list(ChatMessage.objects.values_list("role", flat=True)) == ["user", "assistant"]
    assert services.verify(seller.user)["ok"] is True


def test_a_lookup_can_lead_to_a_draft(seller: Seller) -> None:
    draft = services.ToolCall(
        "draft_sales_invoice",
        json.dumps({"customer": "C1", "items": [{"product": "SOAP-1", "quantity": 2}]}),
    )
    with patch.object(services, "complete", side_effect=[look("look_up_customer", "C1"), draft]):
        reply = seller.shop.member.client().post(
            "/api/assistant/ask/", {"message": "Bill Kiryana 2 soap"}, format="json"
        )
    assert reply.json()["role"] == "draft"
    assert reply.json()["card"]["total"] == "300.00"


def test_customer_lookups_carry_balances_and_bills_but_no_contact_details(
    seller: Seller,
) -> None:
    invoice = sales.save_invoice(
        seller.user,
        {"customer": seller.customer, "warehouse": seller.shop.main, "date": timezone.localdate()},
        [sales.InvoiceLineInput(seller.shop.soap, seller.shop.pcs, D(2), D(100))],
    )
    sales.post_invoice(seller.user, invoice)
    sales.save_invoice(
        seller.user,
        {"customer": seller.customer, "warehouse": seller.shop.main, "date": timezone.localdate()},
        [sales.InvoiceLineInput(seller.shop.soap, seller.shop.pcs, D(1), D(999))],
    )
    [row] = found(seller.shop.member, "look_up_customer", "kiryana")
    assert row["owes_us"] == "200"
    draft, posted = row["recent_invoices"]
    # A draft isn't owed, so it shows no open amount that would contradict the balance.
    assert (draft["status"], draft["still_open"]) == ("draft", None)
    assert posted["still_open"] == "200"
    text = json.dumps(row)
    assert "03000000000" not in text
    assert "example.invalid" not in text


def test_supplier_lookups_carry_what_we_owe(seller: Seller) -> None:
    Supplier.objects.create(code="S1", name="Invented Wholesale")
    [row] = found(seller.shop.member, "look_up_supplier", "S1")
    assert row["we_owe_them"] == "0"
    assert row["recent_bills"] == []


def test_lookups_follow_the_role(seller: Seller) -> None:
    cashier = staff_in(seller, {"sales": ["view"]})
    stock = staff_in(seller, {"inventory": ["view"]})
    nobody = staff_in(seller, {})
    assert names(cashier) == {"look_up_product", "look_up_customer"}
    assert names(stock) == {"look_up_product"}
    assert names(nobody) == set()
    assert names(seller.shop.member) == set(lookups.LOOKUPS)
    # A cashier can see the price but not the stock.
    [row] = found(cashier, "look_up_product", "SOAP-1")
    assert row["sale_price_per_unit"] == "150"
    assert "on_hand_total" not in row


def test_a_lookup_the_role_may_not_make_is_refused(seller: Seller) -> None:
    cashier = staff_in(seller, {"sales": ["view"]})
    result = json.loads(lookups.run(cashier.membership, "look_up_supplier", '{"name": "S1"}'))
    assert result == {"error": "not allowed for this person"}
    unknown = json.loads(lookups.run(cashier.membership, "drop_tables", "{}"))
    assert unknown == {"error": "not allowed for this person"}


@pytest.mark.parametrize("arguments", ["nonsense", "[]", "{}", '{"name": "  "}', '{"name": 5}'])
def test_strange_lookup_arguments_are_answered_calmly(seller: Seller, arguments: str) -> None:
    result = json.loads(lookups.run(seller.shop.member.membership, "look_up_product", arguments))
    assert "error" in result


def test_another_business_is_never_looked_up(seller: Seller) -> None:
    other = make_seller()
    with tenant_context(other.shop.member.tenant):
        other.customer.name = "Far Away Traders"
        other.customer.save()
    assert found(seller.shop.member, "look_up_customer", "Far Away") == []


def test_lookups_stop_after_a_few_and_the_last_turn_must_answer(seller: Seller) -> None:
    replies = [look("look_up_product", "soap")] * services.MAX_LOOKUPS + ["Done looking."]
    with patch.object(services, "complete", side_effect=replies) as complete:
        reply = seller.shop.member.client().post(
            "/api/assistant/ask/", {"message": "Stock?"}, format="json"
        )
    assert reply.json()["content"] == "Done looking."
    last_tools = complete.call_args_list[-1].args[1]
    assert not {tool["function"]["name"] for tool in last_tools} & set(lookups.LOOKUPS)


def test_a_model_that_keeps_looking_gets_a_calm_message(seller: Seller) -> None:
    replies = [look("look_up_product", "soap")] * (services.MAX_LOOKUPS + 1)
    with patch.object(services, "complete", side_effect=replies):
        reply = seller.shop.member.client().post(
            "/api/assistant/ask/", {"message": "Stock?"}, format="json"
        )
    assert reply.status_code == 503


def test_an_answer_out_of_time_is_a_calm_message(seller: Seller) -> None:
    clock = iter([0.0, 0.0, 24.0])
    with (
        patch("apps.assistant.services.time.monotonic", side_effect=lambda: next(clock)),
        patch.object(services, "complete", return_value=look("look_up_product", "soap")),
    ):
        reply = seller.shop.member.client().post(
            "/api/assistant/ask/", {"message": "Stock?"}, format="json"
        )
    assert reply.status_code == 503


def test_each_call_gets_only_the_time_left(seller: Seller) -> None:
    clock = iter([0.0, 0.0, 12.0])
    replies = [look("look_up_product", "soap"), "ok"]
    with (
        patch("apps.assistant.services.time.monotonic", side_effect=lambda: next(clock)),
        patch.object(services, "complete", side_effect=replies) as complete,
    ):
        seller.shop.member.client().post("/api/assistant/ask/", {"message": "?"}, format="json")
    assert [call.args[2] for call in complete.call_args_list] == [20, 13]


def test_the_tool_call_id_is_read_from_groq(seller: Seller) -> None:
    reply = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {"id": "abc", "function": {"name": "look_up_product", "arguments": "{}"}}
                    ]
                }
            }
        ]
    }
    with patch.object(services, "post_json", return_value=reply) as sent:
        answer = services.complete([], lookups.tools(seller.shop.member.membership), 7)
    assert answer == services.ToolCall("look_up_product", "{}", "abc")
    assert sent.call_args.args[3] == 7


def test_only_one_tool_call_is_asked_for_at_a_time(seller: Seller) -> None:
    reply = {"choices": [{"message": {"content": "Hi"}}]}
    with patch.object(services, "post_json", return_value=reply) as sent:
        services.complete([], lookups.tools(seller.shop.member.membership))
    assert sent.call_args.args[1]["parallel_tool_calls"] is False
