from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.tenancy.context import tenant_context
from tests.conftest import Member
from tests.factories import create_membership, create_role
from tests.sales.test_sales import Seller, make_seller


@pytest.fixture(autouse=True)
def groq(settings: SettingsWrapper) -> None:
    settings.GROQ_API_KEY = "test-key"
    settings.CHAT_SIGNING_KEY = "test-signing-key"


@pytest.fixture
def seller(db: None) -> Iterator[Seller]:
    """A shop with stock, two customers and a sale price, plus contact details that must never
    reach the model."""
    built = make_seller()
    with tenant_context(built.shop.member.tenant):
        built.shop.soap.sale_price = Decimal("150")
        built.shop.soap.save()
        built.customer.phone = "03000000000"
        built.customer.email = "kiryana@example.invalid"
        built.customer.save()
        yield built


def staff_in(s: Seller, permissions: dict[str, list[str]]) -> Member:
    membership = create_membership(role=create_role(permissions=permissions))
    return Member(user=membership.user, tenant=s.shop.member.tenant, membership=membership)


class Answered:
    """An ask reply read the way the screen reads it: the job's answer once it is done, or its
    error as a 503 when it failed. Tests run Celery eagerly, so the job is finished already."""

    def __init__(self, reply: Any) -> None:
        self.reply = reply
        body = reply.json()
        self.content = reply.content
        if reply.status_code != 202:
            self.status_code, self.body = reply.status_code, body
        elif body["status"] == "done":
            self.status_code, self.body = 200, body["answer"]
        else:
            self.status_code, self.body = 503, {"detail": body["error"]}

    def json(self) -> Any:
        return self.body


def answered(reply: Any) -> Answered:
    return Answered(reply)
