from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone

from apps.accounting.models import Account
from apps.purchasing import services as purchasing
from apps.purchasing.models import Supplier
from apps.reports import services
from apps.sales import services as sales
from apps.tenancy.context import tenant_context
from tests.sales.test_sales import Seller, invoice, make_seller, receipt

pytestmark = pytest.mark.django_db
D = Decimal


@pytest.fixture
def seller(db: None) -> Iterator[Seller]:
    built = make_seller()
    with tenant_context(built.shop.member.tenant):
        yield built


def today() -> Any:
    return timezone.localdate()


def test_profit_follows_the_sale_and_its_return(seller: Seller) -> None:
    sold = invoice(seller)
    report = services.profit_loss(today().replace(day=1), today())
    assert report.income.total == D("1000.00")
    assert report.cost_of_sales.total == D("600.00")
    assert report.net_profit == D("400.00")
    sales.post_credit_note(seller.user, sales.credit_invoice(seller.user, sold, today()))
    report = services.profit_loss(today().replace(day=1), today())
    assert report.income.total == D(0)
    assert report.net_profit == D(0)


def test_the_balance_sheet_balances_after_a_full_cycle(seller: Seller) -> None:
    sold = invoice(seller)
    receipt(seller, "500", [(sold, "500")])
    report = services.position(today())
    assert report.balanced
    assert report.profit_to_date == D("400.00")
    assert report.assets.total == report.total_liabilities_and_equity


def test_cash_flow_ends_on_what_cash_and_bank_hold(seller: Seller) -> None:
    sold = invoice(seller)
    receipt(seller, "500", [(sold, "500")])
    flow = services.cash_flow(today().replace(day=1), today())
    assert flow.from_customers == D("500.00")
    assert flow.to_suppliers == D(0)
    assert flow.closing == flow.opening + D("500.00")


def test_cash_flow_counts_a_sub_account_of_bank(seller: Seller) -> None:
    bank = Account.objects.get(role="bank")
    child = Account.objects.create(code="1121", name="Second bank", type="asset", parent=bank)
    sold = invoice(seller)
    draft = sales.save_receipt(
        seller.user,
        {"customer": seller.customer, "date": today(), "amount": D("70"), "received_into": child},
        [sales.AllocationInput(sold, D("70"))],
    )
    sales.post_receipt(seller.user, draft)
    assert services.cash_flow(today().replace(day=1), today()).from_customers == D("70.00")


def test_sales_tax_nets_what_was_collected_against_what_was_paid(seller: Seller) -> None:
    sold = invoice(seller)
    supplier = Supplier.objects.create(code="S1", name="Invented Traders")
    bill = purchasing.save_bill(
        seller.user,
        {"supplier": supplier, "date": today()},
        [
            purchasing.BillLineInput(
                D(1),
                D("100"),
                account=Account.objects.get(role="salaries"),
                tax_amount=D("18"),
            )
        ],
    )
    purchasing.post_bill(seller.user, bill)
    report = services.sales_tax(today().replace(day=1), today())
    assert report.taxable_sales == D("1000.00")
    assert report.output_tax == D("180.00")
    assert report.taxable_purchases == D("100.00")
    assert report.input_tax == D("18.00")
    assert report.payable == D("162.00")
    sales.post_credit_note(seller.user, sales.credit_invoice(seller.user, sold, today()))
    report = services.sales_tax(today().replace(day=1), today())
    assert report.taxable_sales == D(0)
    assert report.output_tax == D(0)


def test_dashboard_adds_up(seller: Seller) -> None:
    invoice(seller, quantity="2", price="100", tax="0")
    numbers = services.dashboard(today())
    assert numbers["sales_today"] == D("200.00")
    assert numbers["sales_month"] == D("200.00")
    assert numbers["gross_profit_month"] == D("80.00")
    assert numbers["margin_percent"] == D("40.00")
    assert numbers["stock_value"] == D("1080.00")
    assert numbers["receivable"] == D("200.00")
    assert numbers["payable"] == D(0)
    assert len(numbers["sales_by_day"]) == 30
    assert numbers["sales_by_day"][-1]["amount"] == D("200.00")
    assert numbers["top_products"] == [{"name": "Invented Soap", "amount": D("200.00")}]


def test_a_new_business_sees_zeros_not_an_error(seller: Seller) -> None:
    numbers = services.dashboard(today())
    assert numbers["sales_month"] == D(0)
    assert numbers["margin_percent"] is None
    assert numbers["top_products"] == []


def test_every_dashboard_sales_figure_is_net_of_returns(seller: Seller) -> None:
    sold = invoice(seller, quantity="2", price="100", tax="0")
    invoice(seller, quantity="1", price="100", tax="0")
    sales.post_credit_note(seller.user, sales.credit_invoice(seller.user, sold, today()))
    numbers = services.dashboard(today())
    assert numbers["sales_today"] == D("100.00")
    assert numbers["sales_month"] == D("100.00")
    assert numbers["sales_by_day"][-1]["amount"] == D("100.00")
    assert numbers["top_products"] == [{"name": "Invented Soap", "amount": D("100.00")}]


def test_a_fully_returned_product_leaves_the_best_sellers(seller: Seller) -> None:
    sold = invoice(seller, quantity="1", price="100", tax="0")
    sales.post_credit_note(seller.user, sales.credit_invoice(seller.user, sold, today()))
    assert services.dashboard(today())["top_products"] == []
