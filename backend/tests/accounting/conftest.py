from collections.abc import Iterator
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounting import services
from apps.accounting.models import Account, JournalEntry
from apps.tenancy.context import tenant_context
from tests.conftest import Member, make_member


def with_books(member: Member) -> Member:
    with tenant_context(member.tenant):
        services.install_chart(member.tenant, member.user)
        services.create_current_fiscal_year(member.user, start_month=1)
    return member


@pytest.fixture
def bookkeeper(db: None) -> Iterator[Member]:
    member = with_books(make_member(owner=True))
    with tenant_context(member.tenant):
        yield member


def account(role: str) -> Account:
    found: Account = Account.objects.get(role=role)
    return found


def draft(member: Member, amount: str = "100", memo: str = "Cash sale") -> JournalEntry:
    value = Decimal(amount)
    return services.save_draft(
        member.user,
        timezone.localdate(),
        memo,
        [
            services.LineInput(account("cash"), value, Decimal(0)),
            services.LineInput(account("sales"), Decimal(0), value),
        ],
    )


def lines_payload(
    debit_account: int, credit_account: int, amount: str = "250.00"
) -> list[dict[str, object]]:
    return [
        {"account": debit_account, "debit": amount, "credit": "0"},
        {"account": credit_account, "debit": "0", "credit": amount},
    ]
