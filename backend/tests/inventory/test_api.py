from decimal import Decimal

import pytest
from django.utils import timezone

from apps.inventory import services
from apps.inventory.models import StockEntry, Unit, Warehouse
from tests.conftest import make_member

from .conftest import Shop, line, post

pytestmark = pytest.mark.django_db
D = Decimal


def test_products_with_packs_and_barcodes(shop: Shop) -> None:
    client = shop.member.client()
    created = client.post(
        "/api/inventory/products/",
        {
            "sku": "TEA-500",
            "name": "Invented Tea 500g",
            "unit": shop.pcs.pk,
            "reorder_level": "10",
            "attributes": {"size": "500g"},
            "packs": [{"unit": shop.ctn.pk, "factor": "24", "barcode": "8960000000024"}],
        },
        format="json",
    )
    assert created.status_code == 201, created.json()
    tea = created.json()
    assert tea["packs"][0]["unit_code"] == "CTN"
    assert tea["on_hand"] == "0.0000"

    found = client.get("/api/inventory/products/?barcode=8960000000024").json()["results"]
    assert [row["sku"] for row in found] == ["TEA-500"]
    assert [
        row["sku"] for row in client.get("/api/inventory/products/?q=tea").json()["results"]
    ] == ["TEA-500"]
    assert services.find_by_barcode("8960000000024") is not None
    assert services.find_by_barcode("missing") is None

    duplicate = client.post(
        "/api/inventory/products/",
        {"sku": "TEA-500", "name": "Again", "unit": shop.pcs.pk},
        format="json",
    )
    assert duplicate.status_code == 400
    clash = client.patch(
        f"/api/inventory/products/{tea['id']}/",
        {"packs": [{"unit": shop.ctn.pk, "factor": "24", "barcode": "8960000000017"}]},
        format="json",
    )
    assert clash.status_code == 400
    renamed = client.patch(f"/api/inventory/products/{tea['id']}/", {"name": "Tea"}, format="json")
    assert renamed.json()["name"] == "Tea"
    twice = client.patch(
        f"/api/inventory/products/{tea['id']}/",
        {"packs": [{"unit": shop.ctn.pk, "factor": "1"}, {"unit": shop.ctn.pk, "factor": "2"}]},
        format="json",
    )
    assert twice.status_code == 400
    bad_attrs = client.patch(
        f"/api/inventory/products/{tea['id']}/", {"attributes": {"a": 1}}, format="json"
    )
    assert bad_attrs.status_code == 400
    assert client.delete(f"/api/inventory/products/{tea['id']}/").status_code == 204


def test_master_data_crud(shop: Shop) -> None:
    client = shop.member.client()
    unit = client.post("/api/inventory/units/", {"code": "KG", "name": "Kilogram"}, format="json")
    assert unit.status_code == 201
    assert (
        client.post(
            "/api/inventory/units/", {"code": "KG", "name": "Again"}, format="json"
        ).status_code
        == 400
    )
    assert (
        client.patch(
            f"/api/inventory/units/{unit.json()['id']}/", {"name": "Kilo"}, format="json"
        ).json()["name"]
        == "Kilo"
    )
    assert client.delete(f"/api/inventory/units/{shop.pcs.pk}/").status_code == 400
    assert client.delete(f"/api/inventory/units/{unit.json()['id']}/").status_code == 204
    category = client.post("/api/inventory/categories/", {"name": "Grocery"}, format="json")
    assert category.status_code == 201
    warehouse = client.post(
        "/api/inventory/warehouses/", {"code": "W2", "name": "Godown"}, format="json"
    )
    assert warehouse.status_code == 201
    assert len(client.get("/api/inventory/warehouses/").json()) == 3


def test_stock_entry_api_flow(shop: Shop) -> None:
    client = shop.member.client()
    body = {
        "kind": "receipt",
        "date": str(timezone.localdate()),
        "warehouse": shop.main.pk,
        "lines": [
            {"product": shop.soap.pk, "unit": shop.ctn.pk, "quantity": "1", "unit_cost": "600"}
        ],
    }
    created = client.post("/api/inventory/stock-entries/", body, format="json")
    assert created.status_code == 201, created.json()
    entry_id = created.json()["id"]
    body["lines"][0]["quantity"] = "2"  # type: ignore[index]
    assert (
        client.put(f"/api/inventory/stock-entries/{entry_id}/", body, format="json").status_code
        == 200
    )
    posted = client.post(f"/api/inventory/stock-entries/{entry_id}/post/").json()
    assert posted["number"] == "GRN-000001"
    assert posted["journal_number"] == "JV-000001"
    assert (
        client.put(f"/api/inventory/stock-entries/{entry_id}/", body, format="json").status_code
        == 400
    )
    assert client.delete(f"/api/inventory/stock-entries/{entry_id}/").status_code == 400

    levels = client.get("/api/inventory/stock-levels/").json()["results"]
    assert [(row["sku"], row["quantity"], row["value"]) for row in levels] == [
        ("SOAP-1", "24.0000", "1200.00")
    ]
    assert (
        client.get(f"/api/inventory/stock-levels/?warehouse={shop.branch.pk}").json()["results"]
        == []
    )
    moves = client.get(f"/api/inventory/products/{shop.soap.pk}/moves/").json()["results"]
    assert moves[0]["number"] == "GRN-000001"
    assert client.get(f"/api/inventory/batches/?product={shop.soap.pk}").json() == []
    assert (
        len(
            client.get("/api/inventory/stock-entries/?kind=receipt&status=posted").json()[
                "results"
            ]
        )
        == 1
    )

    draft = client.post(
        "/api/inventory/stock-entries/", {**body, "kind": "issue"}, format="json"
    ).json()
    assert client.delete(f"/api/inventory/stock-entries/{draft['id']}/").status_code == 204
    too_much = client.post(
        "/api/inventory/stock-entries/",
        {
            **body,
            "kind": "issue",
            "lines": [{"product": shop.soap.pk, "unit": shop.ctn.pk, "quantity": "9"}],
        },
        format="json",
    ).json()
    refused = client.post(f"/api/inventory/stock-entries/{too_much['id']}/post/")
    assert refused.status_code == 400
    assert "enough stock" in refused.json()["detail"]


def test_master_delete_of_used_rows_is_refused(shop: Shop) -> None:
    post(shop, "receipt", [line(shop, "1", "1")])
    with pytest.raises(services.InUseError):
        services.delete_master(shop.member.user, Warehouse.objects.get(pk=shop.main.pk))
    assert Unit.objects.filter(pk=shop.pcs.pk).exists()
    assert StockEntry.objects.count() == 1


def test_inventory_needs_permission() -> None:
    viewer = make_member(permissions={"sales": ["view"]})
    assert viewer.client().get("/api/inventory/products/").status_code == 403
