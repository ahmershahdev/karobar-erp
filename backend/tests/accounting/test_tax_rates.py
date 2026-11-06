from datetime import date
from decimal import Decimal

import pytest

from apps.accounting import services
from apps.accounting.models import TaxRate
from apps.tenancy.models import AuditEvent
from tests.conftest import Member

pytestmark = pytest.mark.django_db
BODY = {
    "name": "GST",
    "rate": "18",
    "valid_from": "2026-07-01",
    "source": "Invented notification 1 of 2026",
}


def test_a_rate_needs_a_source_and_is_audited(bookkeeper: Member) -> None:
    client = bookkeeper.client()
    assert (
        client.post(
            "/api/accounting/tax-rates/", {**BODY, "source": ""}, format="json"
        ).status_code
        == 400
    )
    answer = client.post("/api/accounting/tax-rates/", BODY, format="json")
    assert answer.status_code == 201
    assert answer.json()["valid_to"] is None
    assert AuditEvent.objects.filter(action="create", model__icontains="taxrate").exists()


def test_dates_and_percentages_are_checked(bookkeeper: Member) -> None:
    client = bookkeeper.client()
    wrong = {**BODY, "valid_to": "2026-01-01"}
    assert client.post("/api/accounting/tax-rates/", wrong, format="json").status_code == 400
    too_big = {**BODY, "rate": "101"}
    assert client.post("/api/accounting/tax-rates/", too_big, format="json").status_code == 400


def test_a_rate_can_be_ended_and_an_unused_one_deleted(bookkeeper: Member) -> None:
    rate = TaxRate.objects.create(
        name="GST", rate=Decimal(18), valid_from=date(2026, 7, 1), source="Invented"
    )
    client = bookkeeper.client()
    url = f"/api/accounting/tax-rates/{rate.pk}/"
    assert client.patch(url, {"valid_to": "2027-06-30"}, format="json").status_code == 200
    rate.refresh_from_db()
    assert rate.valid_to == date(2027, 6, 30)
    services.delete_tax_rate(bookkeeper.user, rate)
    assert not TaxRate.objects.filter(pk=rate.pk).exists()


def test_what_a_rate_says_cannot_change_once_saved(bookkeeper: Member) -> None:
    rate = TaxRate.objects.create(
        name="GST", rate=Decimal(18), valid_from=date(2026, 7, 1), source="Invented"
    )
    client = bookkeeper.client()
    url = f"/api/accounting/tax-rates/{rate.pk}/"
    assert client.patch(url, {"rate": "17"}, format="json").status_code == 400
    assert client.patch(url, {"valid_from": "2026-08-01"}, format="json").status_code == 400
    assert client.patch(url, {"rate": "18.0000"}, format="json").status_code == 200


def test_a_new_rate_is_audited_with_nothing_before_it(bookkeeper: Member) -> None:
    bookkeeper.client().post("/api/accounting/tax-rates/", BODY, format="json")
    event = AuditEvent.objects.filter(action="create", model__icontains="taxrate").latest("id")
    assert event.changes["name"] == [None, "GST"]
