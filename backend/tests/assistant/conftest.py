from collections.abc import Iterator
from decimal import Decimal

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
