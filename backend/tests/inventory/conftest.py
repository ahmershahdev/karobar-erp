from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.inventory import services
from apps.inventory.models import Product, ProductUnit, StockEntry, Unit, Warehouse
from apps.tenancy.context import tenant_context
from tests.accounting.conftest import with_books
from tests.conftest import Member, make_member

D = Decimal


@dataclass
class Shop:
    member: Member
    pcs: Unit
    ctn: Unit
    main: Warehouse
    branch: Warehouse
    soap: Product


def make_shop(valuation: str = "average") -> Shop:
    member = with_books(make_member(owner=True))
    member.tenant.valuation_method = valuation
    member.tenant.save()
    with tenant_context(member.tenant):
        pcs = Unit.objects.create(code="PCS", name="Piece")
        ctn = Unit.objects.create(code="CTN", name="Carton")
        main = Warehouse.objects.create(code="MAIN", name="Main store")
        branch = Warehouse.objects.create(code="BR1", name="Branch")
        soap = Product.objects.create(
            sku="SOAP-1", name="Invented Soap", unit=pcs, reorder_level=D(5)
        )
        ProductUnit.objects.create(product=soap, unit=ctn, factor=D(12), barcode="8960000000017")
    return Shop(member, pcs, ctn, main, branch, soap)


@pytest.fixture
def shop(db: None) -> Iterator[Shop]:
    built = make_shop()
    with tenant_context(built.member.tenant):
        yield built


@pytest.fixture
def fifo_shop(db: None) -> Iterator[Shop]:
    built = make_shop("fifo")
    with tenant_context(built.member.tenant):
        yield built


def post(
    shop: Shop,
    kind: str,
    lines: list[services.LineInput],
    warehouse: Warehouse | None = None,
    to_warehouse: Warehouse | None = None,
    on: date | None = None,
) -> StockEntry:
    entry = services.save_draft(
        shop.member.user,
        {
            "kind": kind,
            "date": on or timezone.localdate(),
            "memo": "",
            "warehouse": warehouse or shop.main,
            "to_warehouse": to_warehouse,
        },
        lines,
    )
    return services.post_entry(shop.member.user, entry)


def line(
    shop: Shop, quantity: str, cost: str | None = None, unit: Unit | None = None, **extra: object
) -> services.LineInput:
    return services.LineInput(
        shop.soap,
        unit or shop.pcs,
        D(quantity),
        None if cost is None else D(cost),
        **extra,  # type: ignore[arg-type]
    )
