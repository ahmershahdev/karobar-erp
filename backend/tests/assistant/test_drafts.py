import json
from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.assistant import drafts, services
from apps.assistant.models import ChatMessage
from apps.inventory.models import Warehouse
from apps.purchasing.models import PurchaseOrder, Supplier
from apps.sales.models import Invoice, SalesOrder
from apps.tenancy.context import tenant_context
from apps.tenancy.models import AuditEvent
from tests.conftest import Member
from tests.factories import create_membership, create_role
from tests.sales.test_sales import Seller, make_seller

D = Decimal


@pytest.fixture(autouse=True)
def groq(settings: SettingsWrapper) -> None:
    settings.GROQ_API_KEY = "test-key"
    settings.CHAT_SIGNING_KEY = "test-signing-key"


@pytest.fixture
def seller(db: None) -> Iterator[Seller]:
    built = make_seller()
    with tenant_context(built.shop.member.tenant):
        built.shop.soap.sale_price = D("150")
        built.shop.soap.save()
        yield built


def owner(s: Seller) -> Member:
    return s.shop.member


def staff(s: Seller, permissions: dict[str, list[str]]) -> Member:
    membership = create_membership(role=create_role(permissions=permissions))
    return Member(user=membership.user, tenant=s.shop.member.tenant, membership=membership)


def calls(tool: str, **arguments: Any) -> Any:
    return patch.object(
        services, "complete", return_value=services.ToolCall(tool, json.dumps(arguments))
    )


def ask(member: Member, text: str = "Make a bill") -> Any:
    return member.client().post("/api/assistant/ask/", {"message": text}, format="json")


def soap_bill(quantity: Any = 4, **extra: Any) -> Any:
    item = {"product": "invented soap", "quantity": quantity, **extra}
    return calls("draft_sales_invoice", customer="Invented Kiryana", items=[item])


def card_of(reply: Any) -> dict[str, Any]:
    assert reply.status_code == 200, reply.content
    body = reply.json()
    assert body["role"] == "draft"
    return dict(body["card"])


def confirm(member: Member, pk: int) -> Any:
    return member.client().post(f"/api/assistant/drafts/{pk}/confirm/")


def test_a_draft_is_only_a_card_until_confirmed(seller: Seller) -> None:
    with soap_bill():
        card = card_of(ask(owner(seller)))
    assert card["party"] == {"id": seller.customer.pk, "name": "Invented Kiryana"}
    assert card["warehouse"]["name"] == "Main store"
    assert card["lines"][0]["quantity"] == "4"
    assert card["lines"][0]["unit_price"] == "150.00"
    assert card["lines"][0]["unit_code"] == "PCS"
    assert card["total"] == "600.00"
    assert not Invoice.objects.exists()


def test_confirm_saves_a_draft_through_the_normal_save(seller: Seller) -> None:
    with soap_bill():
        pk = ask(owner(seller)).json()["id"]
    reply = confirm(owner(seller), pk)
    assert reply.status_code == 200, reply.content
    invoice = Invoice.objects.get()
    assert invoice.status == Invoice.Status.DRAFT
    assert invoice.customer == seller.customer
    assert invoice.total == D("600.00")
    assert invoice.created_by == seller.user
    assert reply.json()["card"] == {"draft": pk, "kind": "sales_invoice", "document": invoice.pk}
    assert AuditEvent.objects.filter(model="sales.Invoice", object_id=str(invoice.pk)).exists()
    assert services.verify(seller.user)["ok"] is True


def test_a_draft_is_saved_only_once(seller: Seller) -> None:
    with soap_bill():
        pk = ask(owner(seller)).json()["id"]
    assert confirm(owner(seller), pk).status_code == 200
    again = confirm(owner(seller), pk)
    assert again.status_code == 409
    assert Invoice.objects.count() == 1


def test_a_price_the_person_gave_wins(seller: Seller) -> None:
    with soap_bill(quantity="2.5", price=90):
        card = card_of(ask(owner(seller)))
    assert card["lines"][0]["unit_price"] == "90.00"
    assert card["total"] == "225.00"


def test_quotations_and_purchase_orders_can_be_drafted(seller: Seller) -> None:
    Supplier.objects.create(code="S1", name="Invented Wholesale")
    item = {"product": "SOAP-1", "quantity": 10}
    with calls("draft_quotation", customer="C1", items=[item]):
        quote = ask(owner(seller)).json()["id"]
    with calls("draft_purchase_order", supplier="invented wholesale", items=[item]):
        reply = ask(owner(seller))
    card = card_of(reply)
    # Nothing was bought before, so there is no price to suggest, and the card says so.
    assert card["lines"][0]["unit_price"] is None
    assert confirm(owner(seller), quote).status_code == 200
    assert confirm(owner(seller), reply.json()["id"]).status_code == 200
    assert SalesOrder.objects.get().status == SalesOrder.Status.DRAFT
    order = PurchaseOrder.objects.get()
    assert order.status == PurchaseOrder.Status.DRAFT
    assert order.lines.get().unit_price == D(0)


def test_a_purchase_order_suggests_the_last_price_paid(seller: Seller) -> None:
    Supplier.objects.create(code="S1", name="Invented Wholesale")
    item = {"product": "Invented Soap", "quantity": 10, "price": 55}
    with calls("draft_purchase_order", supplier="S1", items=[item]):
        assert confirm(owner(seller), ask(owner(seller)).json()["id"]).status_code == 200
    with calls(
        "draft_purchase_order", supplier="S1", items=[{"product": "SOAP-1", "quantity": 3}]
    ):
        card = card_of(ask(owner(seller)))
    assert card["lines"][0]["unit_price"] == "55.00"


def test_a_name_that_is_not_found_is_said_plainly(seller: Seller) -> None:
    with calls("draft_sales_invoice", customer="Nobody", items=[{"product": "x", "quantity": 1}]):
        card = card_of(ask(owner(seller)))
    assert card["problem"] == {
        "code": "not_found",
        "field": "customer",
        "name": "Nobody",
        "options": [],
    }
    assert confirm(owner(seller), ChatMessage.objects.get(role="draft").pk).status_code == 404


def test_a_name_matching_several_lists_them(seller: Seller) -> None:
    item = {"product": "soap", "quantity": 1}
    with calls("draft_sales_invoice", customer="Invented", items=[item]):
        card = card_of(ask(owner(seller)))
    # "Invented" is in one customer's name only; the other is "Imaginary Store".
    assert "problem" not in card
    with calls("draft_sales_invoice", customer="Store", items=[item]):
        assert "problem" not in card_of(ask(owner(seller)))
    with calls("draft_sales_invoice", customer="i", items=[item]):
        card = card_of(ask(owner(seller)))
    assert card["problem"]["code"] == "ambiguous"
    assert sorted(card["problem"]["options"]) == ["Imaginary Store", "Invented Kiryana"]


@pytest.mark.parametrize(
    "arguments",
    [
        "not json",
        "[]",
        json.dumps({"customer": "C1"}),
        json.dumps({"customer": "C1", "items": [{"product": "SOAP-1", "quantity": 0}]}),
        json.dumps({"customer": "C1", "items": [{"product": "SOAP-1", "quantity": True}]}),
        json.dumps({"customer": "C1", "items": [{"product": "SOAP-1", "quantity": "lots"}]}),
        json.dumps({"customer": "C1", "items": [{"product": "SOAP-1", "quantity": "NaN"}]}),
        json.dumps({"customer": "C1", "items": ["SOAP-1"]}),
        json.dumps(
            {"customer": "C1", "items": [{"product": "SOAP-1", "quantity": 1, "price": -1}]}
        ),
        json.dumps({"customer": "", "items": [{"product": "SOAP-1", "quantity": 1}]}),
    ],
)
def test_strange_arguments_become_an_unclear_card(seller: Seller, arguments: str) -> None:
    with patch.object(
        services, "complete", return_value=services.ToolCall("draft_sales_invoice", arguments)
    ):
        card = card_of(ask(owner(seller)))
    assert card["problem"]["code"] == "unclear"


def test_too_many_items_are_refused(seller: Seller) -> None:
    items = [{"product": "SOAP-1", "quantity": 1}] * (drafts.MAX_ITEMS + 1)
    with calls("draft_sales_invoice", customer="C1", items=items):
        assert card_of(ask(owner(seller)))["problem"]["code"] == "too_many"


def test_another_business_rows_are_never_found(seller: Seller) -> None:
    other = make_seller()
    with tenant_context(other.shop.member.tenant):
        other.customer.name = "Far Away Traders"
        other.customer.save()
    with calls(
        "draft_sales_invoice",
        customer="Far Away Traders",
        items=[{"product": "SOAP-1", "quantity": 1}],
    ):
        assert card_of(ask(owner(seller)))["problem"]["code"] == "not_found"


def test_tools_follow_what_the_role_may_create(seller: Seller) -> None:
    cashier = staff(seller, {"sales": ["view", "create"]})
    viewer = staff(seller, {"sales": ["view"], "purchasing": ["view"]})
    names = {tool["function"]["name"] for tool in drafts.tools(cashier.membership)}
    assert names == {"draft_sales_invoice", "draft_quotation"}
    assert drafts.tools(viewer.membership) == []
    assert "can't change anything" in services.system_prompt(viewer.user, viewer.membership)
    prompt = services.system_prompt(cashier.user, cashier.membership)
    assert "draft_sales_invoice" in prompt
    assert "can't post, pay, delete" in prompt


def test_a_tool_the_person_was_not_given_makes_nothing(seller: Seller) -> None:
    viewer = staff(seller, {"sales": ["view"]})
    with soap_bill():
        card = card_of(ask(viewer))
    assert card["problem"]["code"] == "not_allowed"
    assert confirm(viewer, ChatMessage.objects.get(role="draft").pk).status_code == 404
    assert not Invoice.objects.exists()


def test_losing_the_permission_before_confirm_stops_it(seller: Seller) -> None:
    clerk = staff(seller, {"sales": ["view", "create"]})
    with soap_bill():
        pk = ask(clerk).json()["id"]
    role = clerk.membership.role
    assert role is not None
    role.permissions = {"sales": ["view"]}
    role.save()
    clerk.membership.refresh_from_db()
    reply = confirm(clerk, pk)
    assert reply.status_code == 403
    assert not Invoice.objects.exists()
    assert not ChatMessage.objects.filter(role="done").exists()


def test_only_the_person_who_asked_can_confirm(seller: Seller) -> None:
    clerk = staff(seller, {"sales": ["view", "create"]})
    with soap_bill():
        pk = ask(owner(seller)).json()["id"]
    assert confirm(clerk, pk).status_code == 404
    other = make_seller()
    with tenant_context(other.shop.member.tenant):
        assert confirm(other.shop.member, pk).status_code == 404
    assert not Invoice.objects.exists()


def test_a_card_from_before_a_new_chat_cannot_be_confirmed(seller: Seller) -> None:
    with soap_bill():
        pk = ask(owner(seller)).json()["id"]
    services.reset(seller.user)
    assert confirm(owner(seller), pk).status_code == 404


def test_the_document_and_its_record_are_saved_together(seller: Seller) -> None:
    with soap_bill():
        pk = ask(owner(seller)).json()["id"]
    real = services.record

    def fail_on_done(user: Any, role: str, *args: Any, **kwargs: Any) -> Any:
        if role == ChatMessage.Role.DONE:
            raise RuntimeError("disk full")
        return real(user, role, *args, **kwargs)

    with patch.object(services, "record", side_effect=fail_on_done):
        assert confirm(owner(seller), pk).status_code == 500
    assert not Invoice.objects.exists()
    assert confirm(owner(seller), pk).status_code == 200


def test_cards_reach_the_model_as_plain_sentences(seller: Seller) -> None:
    with soap_bill():
        pk = ask(owner(seller)).json()["id"]
    confirm(owner(seller), pk)
    with patch.object(services, "complete", return_value="Done") as complete:
        ask(owner(seller), "Thanks")
    history = complete.call_args.args[0][1:]
    assert [row["role"] for row in history] == ["user", "assistant", "assistant", "user"]
    assert "4 PCS Invented Soap" in history[1]["content"]
    assert "Confirm" in history[1]["content"]
    assert "not posted" in history[2]["content"]


def test_a_tool_call_from_groq_is_read(seller: Seller) -> None:
    reply = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {"function": {"name": "draft_quotation", "arguments": "{}"}},
                        {"function": {"name": "draft_sales_invoice", "arguments": "{}"}},
                    ],
                }
            }
        ]
    }
    with patch.object(services, "post_json", return_value=reply) as sent:
        answer = services.complete([], drafts.tools(owner(seller).membership))
    assert answer == services.ToolCall("draft_quotation", "{}")
    assert len(sent.call_args.args[1]["tools"]) == 3


def test_without_tools_none_are_sent(seller: Seller) -> None:
    reply = {"choices": [{"message": {"content": "Hi"}}]}
    with patch.object(services, "post_json", return_value=reply) as sent:
        assert services.complete([]) == "Hi"
    assert "tools" not in sent.call_args.args[1]


def test_a_named_warehouse_is_used(seller: Seller) -> None:
    item = {"product": "SOAP-1", "quantity": 1}
    with calls("draft_sales_invoice", customer="C1", items=[item], warehouse="BR1"):
        assert card_of(ask(owner(seller)))["warehouse"]["name"] == "Branch"


def test_a_business_without_a_warehouse_is_told(seller: Seller) -> None:
    Warehouse.objects.update(is_active=False)
    with soap_bill():
        assert card_of(ask(owner(seller)))["problem"]["code"] == "no_warehouse"


def test_a_card_that_failed_reaches_the_model_as_a_sentence(seller: Seller) -> None:
    with calls("draft_sales_invoice", customer="Nobody", items=[{"product": "x", "quantity": 1}]):
        ask(owner(seller))
    with patch.object(services, "complete", return_value="Sorry") as complete:
        ask(owner(seller), "Why?")
    assert "Nobody" in complete.call_args.args[0][2]["content"]


def test_a_broken_tool_call_is_a_calm_message(seller: Seller) -> None:
    reply = {"choices": [{"message": {"tool_calls": [{"function": {"name": 1, "arguments": 2}}]}}]}
    with (
        patch.object(services, "post_json", return_value=reply),
        pytest.raises(services.AssistantError),
    ):
        services.complete([], drafts.tools(owner(seller).membership))


def test_a_pack_the_person_named_is_used_and_priced(seller: Seller) -> None:
    items = [
        {"product": "Invented Soap", "quantity": 2, "unit": "cartons"},
        {"product": "Invented Soap", "quantity": 3, "unit": "pcs"},
    ]
    with calls("draft_sales_invoice", customer="C1", items=items):
        card = card_of(ask(owner(seller)))
    assert [(line["unit_code"], line["unit_price"]) for line in card["lines"]] == [
        ("CTN", "1800.00"),
        ("PCS", "150.00"),
    ]
    assert card["total"] == "4050.00"
    assert confirm(owner(seller), ask_id(seller)).status_code == 200
    assert Invoice.objects.get().lines.filter(unit=seller.shop.ctn).exists()


def test_a_unit_the_product_is_not_sold_in_is_said_plainly(seller: Seller) -> None:
    items = [{"product": "Invented Soap", "quantity": 2, "unit": "drum"}]
    with calls("draft_sales_invoice", customer="C1", items=items):
        card = card_of(ask(owner(seller)))
    assert card["problem"]["field"] == "unit"
    assert card["problem"]["code"] == "not_found"


def ask_id(seller: Seller) -> int:
    return int(
        ChatMessage.objects.filter(role="draft").order_by("-id").values_list("id", flat=True)[0]
    )
