import threading
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest
from django.db import connection
from django.utils import timezone

from apps.accounting.models import Account, TaxRate
from apps.accounting.reports import trial_balance
from apps.accounts.models import User
from apps.inventory.models import Product, StockLevel
from apps.inventory.services import NotEnoughStockError
from apps.pos import services
from apps.pos.models import PosSale, PosSession
from apps.sales.models import Invoice
from apps.tenancy.context import tenant_context
from tests.sales.test_sales import Seller, make_seller

pytestmark = pytest.mark.django_db
D = Decimal


@dataclass
class Till:
    seller: Seller
    session: PosSession

    @property
    def user(self) -> User:
        return self.seller.user

    @property
    def soap(self) -> Product:
        return self.seller.shop.soap

    def line(self, quantity: str = "2", unit: Any = None) -> services.CartLine:
        return services.CartLine(self.soap, unit or self.seller.shop.pcs, D(quantity))


def make_till() -> Till:
    seller = make_seller()
    with tenant_context(seller.shop.member.tenant):
        seller.shop.soap.sale_price = D("100")
        seller.shop.soap.save()
        session = services.open_till(seller.user, seller.shop.main, D("500"))
    return Till(seller, session)


@pytest.fixture
def till(db: None) -> Iterator[Till]:
    built = make_till()
    with tenant_context(built.seller.shop.member.tenant):
        yield built


def book(role: str) -> Decimal:
    code = Account.objects.get(role=role).code
    report = trial_balance(timezone.localdate())
    amount: Decimal = next(
        (row.debit - row.credit for row in report.rows if row.code == code), D(0)
    )
    return amount


def stock(till: Till) -> Decimal:
    level: StockLevel = StockLevel.objects.get(product=till.soap, warehouse=till.seller.shop.main)
    quantity: Decimal = level.quantity
    return quantity


def test_a_cash_sale_moves_stock_books_and_gives_change(till: Till) -> None:
    sale = services.sell(till.user, till.session, [till.line()], "cash", D("500"))
    assert (sale.amount, sale.tendered, sale.change) == (D("200.00"), D("500"), D("300.00"))
    assert stock(till) == D("18")
    assert book("sales") == D("-200.00")
    assert book("cash") == D("200.00")
    assert book("receivables") == D(0)
    assert sale.invoice.status == Invoice.Status.POSTED


def test_a_card_sale_goes_to_the_bank_and_gives_no_change(till: Till) -> None:
    sale = services.sell(till.user, till.session, [till.line()], "card")
    assert sale.change == D(0)
    assert book("bank") == D("200.00")
    assert book("cash") == D(0)


def test_the_price_comes_from_the_product_and_a_carton_from_its_pack(till: Till) -> None:
    sale = services.sell(till.user, till.session, [till.line("1", till.seller.shop.ctn)], "card")
    assert sale.amount == D("1200.00")
    assert stock(till) == D("8")


def test_scanning_a_carton_finds_the_carton_at_the_carton_price(till: Till) -> None:
    barcode = str(till.soap.packs.get().barcode)
    found = services.find_products(barcode)
    assert len(found) == 1
    assert found[0].exact
    assert found[0].unit == till.seller.shop.ctn
    assert found[0].price == D("1200.0000")


def test_search_by_sku_and_name(till: Till) -> None:
    assert services.find_products("soap-1")[0].exact
    named = services.find_products("Invented")
    assert [row.product for row in named] == [till.soap]
    assert not named[0].exact
    assert services.find_products("nothing like this") == []


def test_tax_is_worked_out_from_the_chosen_rate(till: Till) -> None:
    rate = TaxRate.objects.create(
        name="GST", rate=D("18"), valid_from=timezone.localdate(), source="Invented"
    )
    sale = services.sell(till.user, till.session, [till.line()], "card", None, rate)
    assert sale.amount == D("236.00")
    assert book("tax_output") == D("-36.00")


def test_too_little_cash_stops_the_whole_sale(till: Till) -> None:
    with pytest.raises(services.NotEnoughCashError):
        services.sell(till.user, till.session, [till.line()], "cash", D("199.99"))
    assert stock(till) == D("20")
    assert book("sales") == D(0)
    assert not Invoice.objects.exists()


def test_selling_more_than_is_there_stops_the_whole_sale(till: Till) -> None:
    with pytest.raises(NotEnoughStockError):
        services.sell(till.user, till.session, [till.line("500")], "cash", D("99999"))
    assert stock(till) == D("20")
    assert not PosSale.objects.exists()
    assert not Invoice.objects.exists()


def test_a_product_with_no_price_cannot_be_sold(till: Till) -> None:
    till.soap.sale_price = None
    till.soap.save()
    with pytest.raises(services.NoPriceError):
        services.sell(till.user, till.session, [till.line()], "card")


def test_an_empty_cart_is_refused(till: Till) -> None:
    with pytest.raises(services.EmptyCartError):
        services.sell(till.user, till.session, [], "card")


def test_a_store_can_only_have_one_open_till(till: Till) -> None:
    with pytest.raises(services.TillAlreadyOpenError):
        services.open_till(till.user, till.seller.shop.main, D(0))
    services.open_till(till.user, till.seller.shop.branch, D(0))


def test_closing_with_the_right_cash_books_nothing(till: Till) -> None:
    services.sell(till.user, till.session, [till.line()], "cash", D("200"))
    services.sell(till.user, till.session, [till.line("1")], "card")
    closed = services.close_till(till.user, till.session, D("700"))
    assert closed.expected_cash == D("700.00")
    assert closed.difference == D("0.00")
    assert closed.journal_entry is None
    assert services.takings(closed) == {
        "sales_count": 2,
        "cash_sales": D("200.00"),
        "card_sales": D("100.00"),
    }


def test_short_cash_is_booked_as_a_loss(till: Till) -> None:
    services.sell(till.user, till.session, [till.line()], "cash", D("200"))
    closed = services.close_till(till.user, till.session, D("690"))
    assert closed.difference == D("-10.00")
    assert book("cash_over_short") == D("10.00")
    assert book("cash") == D("190.00")


def test_extra_cash_is_booked_too(till: Till) -> None:
    closed = services.close_till(till.user, till.session, D("505"))
    assert closed.difference == D("5.00")
    assert book("cash_over_short") == D("-5.00")


def test_a_closed_till_takes_no_sales_and_frees_the_store(till: Till) -> None:
    services.close_till(till.user, till.session, D("500"))
    with pytest.raises(services.TillClosedError):
        services.sell(till.user, till.session, [till.line()], "card")
    with pytest.raises(services.TillClosedError):
        services.close_till(till.user, till.session, D("500"))
    services.open_till(till.user, till.seller.shop.main, D(0))


@pytest.mark.django_db(transaction=True)
def test_two_tills_selling_the_last_units_cannot_both_succeed() -> None:
    built = make_till()
    tenant = built.seller.shop.member.tenant
    with tenant_context(tenant):
        second = services.open_till(built.user, built.seller.shop.branch, D(0))
        second.warehouse = built.seller.shop.main
        second.save()
    outcomes: list[str] = []
    gate = threading.Barrier(2)

    def buy(session: PosSession) -> None:
        with tenant_context(tenant):
            gate.wait()
            try:
                services.sell(built.user, session, [built.line("15")], "card")
                outcomes.append("sold")
            except NotEnoughStockError:
                outcomes.append("refused")
            finally:
                connection.close()

    threads = [threading.Thread(target=buy, args=(s,)) for s in (built.session, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["refused", "sold"]
