"""Every endpoint is either public, user-level, or tenant-owned and proven isolated here.

A new URL that isn't listed below fails test_every_endpoint_is_classified, which is the point:
nobody can add an endpoint without deciding how tenants are kept apart on it.
"""

import io
import json
from collections.abc import Callable, Iterator
from decimal import Decimal
from typing import Any

import pytest
from django.conf import settings
from django.urls import URLPattern, URLResolver, get_resolver
from django.utils import timezone
from PIL import Image

from apps.accounting import services as accounting
from apps.accounting.models import Account, FiscalPeriod, FiscalYear, JournalEntry, TaxRate
from apps.assistant import drafts
from apps.assistant import services as assistant
from apps.core.salary_tax import Slab
from apps.hr import services as hr
from apps.hr import time_off
from apps.hr.models import (
    Contract,
    Department,
    Employee,
    Holiday,
    LeaveRequest,
    LeaveType,
    SalaryStructure,
)
from apps.inventory import services as inventory
from apps.inventory.models import (
    Batch,
    Category,
    Product,
    StockEntry,
    StockLevel,
    Unit,
    Warehouse,
)
from apps.payroll import runs as payroll
from apps.payroll import services as payroll_tax
from apps.payroll.models import PayrollRun, Payslip, TaxTable
from apps.pos import services as pos
from apps.pos.models import PosSession
from apps.purchasing import services as purchasing
from apps.purchasing.models import Bill, GoodsReceipt, PurchaseOrder, Supplier, SupplierPayment
from apps.sales import billing
from apps.sales import services as sales
from apps.sales.models import CreditNote, Customer, CustomerReceipt, Invoice, SalesOrder
from apps.tenancy import audit, services
from apps.tenancy.models import AuditEvent, Membership, Role, Tenant
from tests.conftest import Member
from tests.factories import create_user

PUBLIC = {
    "api/health/",
    "api/accounts/csrf/",
    "api/accounts/login/",
    "api/accounts/signup/",
    "api/accounts/verify-email/",
    "api/accounts/password-reset/",
    "api/accounts/password-reset/confirm/",
    "api/accounts/email/confirm/",
    "api/accounts/config/",
    "api/accounts/session/",
    "api/accounts/oauth/<str:provider>/start/",
    "api/accounts/oauth/<str:provider>/callback/",
    "api/public/bills/<str:token>/",
}
USER_LEVEL = {
    "api/accounts/logout/",
    "api/accounts/me/",
    "api/accounts/password/",
    "api/accounts/email/",
    "api/accounts/delete/",
    "api/assistant/ask/",
    "api/assistant/reset/",
    "api/hr/holidays/fill/",
    "api/payroll/tax-tables/fill/",
    "api/accounts/verify-email/resend/",
    "api/tenants/",
    "api/invitations/accept/",
    "api/schema/",
}

# Each entry creates a row in the member's tenant and returns (url, id of that row). Detail
# urls must be 404 for an outsider; list urls must not contain the row.
TENANT_OWNED: dict[str, Callable[[Member], tuple[str, int]]] = {}


def tenant_endpoint(
    route: str,
) -> Callable[[Callable[[Member], tuple[str, int]]], Callable[[Member], tuple[str, int]]]:
    def register(make: Callable[[Member], tuple[str, int]]) -> Callable[[Member], tuple[str, int]]:
        TENANT_OWNED[route] = make
        return make

    return register


def _event(member: Member) -> int:
    role = Role.objects.create(name="Audited")
    event: AuditEvent = audit.record(AuditEvent.Action.CREATE, role, member.user)
    return event.pk


def _role(member: Member) -> int:
    role: Role = Role.objects.create(name="Private role")
    return role.pk


def _member(member: Member) -> int:
    membership: Membership = Membership.objects.create(user=create_user())
    return membership.pk


def _invitation(member: Member) -> int:
    invitation, _ = services.invite(member.user, member.tenant, "hidden@example.test", None)
    return invitation.pk


def _register(prefix: str, make_row: Callable[[Member], int]) -> None:
    def collection(member: Member) -> tuple[str, int]:
        return f"/api/{prefix}/", make_row(member)

    def detail(member: Member) -> tuple[str, int]:
        pk = make_row(member)
        return f"/api/{prefix}/{pk}/", pk

    tenant_endpoint(f"api/{prefix}/")(collection)
    tenant_endpoint(f"api/{prefix}/<int:pk>/")(detail)


_register("audit", _event)
_register("roles", _role)
_register("members", _member)
_register("invitations", _invitation)


def _books(member: Member) -> None:
    if not Account.objects.exists():
        accounting.install_chart(member.tenant, member.user)
        accounting.create_current_fiscal_year(member.user, start_month=1)


def _account(member: Member) -> int:
    _books(member)
    cash: Account = Account.objects.get(role="cash")
    return cash.pk


def _draft(member: Member) -> int:
    _books(member)
    amount = Decimal(10)
    entry = accounting.save_draft(
        member.user,
        timezone.localdate(),
        "Private",
        [
            accounting.LineInput(Account.objects.get(role="cash"), amount, Decimal(0)),
            accounting.LineInput(Account.objects.get(role="sales"), Decimal(0), amount),
        ],
    )
    return entry.pk


def _posted(member: Member) -> int:
    entry = JournalEntry.objects.get(pk=_draft(member))
    return accounting.post_entry(member.user, entry).pk


def _fiscal_year(member: Member) -> int:
    _books(member)
    year: FiscalYear = FiscalYear.objects.get()
    return year.pk


def _period(member: Member) -> int:
    _books(member)
    period: FiscalPeriod = FiscalPeriod.objects.all()[0]
    return period.pk


_register("accounting/accounts", _account)
_register("accounting/entries", _draft)
tenant_endpoint("api/accounting/fiscal-years/")(
    lambda m: ("/api/accounting/fiscal-years/", _fiscal_year(m))
)


def _detail(
    template: str, make_row: Callable[[Member], int]
) -> Callable[[Member], tuple[str, int]]:
    def probe(member: Member) -> tuple[str, int]:
        pk = make_row(member)
        return template.format(pk=pk), pk

    return probe


tenant_endpoint("api/accounting/periods/<int:pk>/")(
    _detail("/api/accounting/periods/{pk}/", _period)
)
tenant_endpoint("api/accounting/accounts/<int:pk>/ledger/")(
    _detail("/api/accounting/accounts/{pk}/ledger/", _account)
)


def _trial_balance(member: Member) -> tuple[str, int]:
    _posted(member)
    return "/api/accounting/reports/trial-balance/", Account.objects.get(role="cash").pk


tenant_endpoint("api/accounting/reports/trial-balance/")(_trial_balance)


def _shop(member: Member) -> dict[str, Any]:
    _books(member)
    pcs, _ = Unit.objects.get_or_create(code="PCS", defaults={"name": "Piece"})
    main, _ = Warehouse.objects.get_or_create(code="MAIN", defaults={"name": "Main"})
    product, _ = Product.objects.get_or_create(sku="P1", defaults={"name": "Private", "unit": pcs})
    return {"unit": pcs, "warehouse": main, "product": product}


def _stock_draft(member: Member) -> int:
    shop = _shop(member)
    entry = inventory.save_draft(
        member.user,
        {
            "kind": "receipt",
            "date": timezone.localdate(),
            "memo": "",
            "warehouse": shop["warehouse"],
        },
        [inventory.LineInput(shop["product"], shop["unit"], Decimal(2), Decimal(5))],
    )
    return entry.pk


def _stock_level(member: Member) -> int:
    entry = StockEntry.objects.get(pk=_stock_draft(member))
    inventory.post_entry(member.user, entry)
    level: StockLevel = StockLevel.objects.get(product__sku="P1")
    return level.pk


def _row(field: str) -> Callable[[Member], int]:
    def make(member: Member) -> int:
        row = _shop(member)[field]
        return int(row.pk)

    return make


def _category(member: Member) -> int:
    category, _ = Category.objects.get_or_create(name="Private")
    return int(category.pk)


_register("inventory/units", _row("unit"))
_register("inventory/warehouses", _row("warehouse"))
_register("inventory/products", _row("product"))
_register("inventory/categories", _category)
_register("inventory/stock-entries", _stock_draft)
tenant_endpoint("api/inventory/products/<int:pk>/moves/")(
    _detail("/api/inventory/products/{pk}/moves/", _row("product"))
)
tenant_endpoint("api/inventory/stock-levels/")(
    lambda m: ("/api/inventory/stock-levels/", _stock_level(m))
)


def _batch(member: Member) -> int:
    shop = _shop(member)
    batch = Batch.objects.create(product=shop["product"], number="B-PRIVATE")
    return int(batch.pk)


def _alerts(member: Member) -> tuple[str, int]:
    shop = _shop(member)
    shop["product"].reorder_level = Decimal(10)
    shop["product"].save()
    return "/api/inventory/alerts/", int(shop["product"].pk)


tenant_endpoint("api/inventory/stock-value/")(
    lambda m: ("/api/inventory/stock-value/", _stock_level(m))
)
tenant_endpoint("api/inventory/batches/")(lambda m: ("/api/inventory/batches/", _batch(m)))
tenant_endpoint("api/inventory/alerts/")(_alerts)


def _supplier(member: Member) -> Supplier:
    _shop(member)
    supplier: Supplier = Supplier.objects.get_or_create(code="S-P", defaults={"name": "Private"})[
        0
    ]
    return supplier


def _order(member: Member, confirm: bool = False) -> PurchaseOrder:
    shop = _shop(member)
    order = purchasing.save_order(
        member.user,
        {
            "supplier": _supplier(member),
            "date": timezone.localdate(),
            "warehouse": shop["warehouse"],
        },
        [purchasing.OrderLineInput(shop["product"], shop["unit"], Decimal(2), Decimal(5))],
    )
    return purchasing.confirm_order(member.user, order) if confirm else order


def _receipt(member: Member, post: bool = False) -> int:
    receipt = purchasing.receive_order(member.user, _order(member, True), timezone.localdate())
    return (purchasing.post_receipt(member.user, receipt) if post else receipt).pk


def _bill(member: Member) -> int:
    receipt = GoodsReceipt.objects.get(pk=_receipt(member, post=True))
    return purchasing.bill_receipt(member.user, receipt, timezone.localdate()).pk


def _posted_bill(member: Member) -> Bill:
    return purchasing.post_bill(member.user, Bill.objects.get(pk=_bill(member)))


def _payment(member: Member) -> int:
    payment = purchasing.save_payment(
        member.user,
        {
            "supplier": _supplier(member),
            "date": timezone.localdate(),
            "amount": Decimal(10),
            "paid_from": Account.objects.get(role="cash"),
        },
        [purchasing.AllocationInput(_posted_bill(member), Decimal(10))],
    )
    return payment.pk


def _customer(member: Member) -> Customer:
    _shop(member)
    customer: Customer = Customer.objects.get_or_create(code="C-P", defaults={"name": "Private"})[
        0
    ]
    return customer


def _sales_order(member: Member, confirm: bool = False) -> SalesOrder:
    shop = _shop(member)
    order = sales.save_order(
        member.user,
        {
            "customer": _customer(member),
            "warehouse": shop["warehouse"],
            "date": timezone.localdate(),
        },
        [sales.OrderLineInput(shop["product"], shop["unit"], Decimal(1), Decimal(5))],
    )
    return sales.confirm_order(member.user, order) if confirm else order


def _invoice(member: Member, post: bool = False) -> Invoice:
    _stock_level(member)
    invoice = sales.invoice_order(member.user, _sales_order(member, True), timezone.localdate())
    return sales.post_invoice(member.user, invoice) if post else invoice


def _sales_receipt(member: Member) -> CustomerReceipt:
    return sales.save_receipt(
        member.user,
        {
            "customer": _customer(member),
            "date": timezone.localdate(),
            "amount": Decimal(5),
            "received_into": Account.objects.get(role="bank"),
        },
        [],
    )


def _credit_note(member: Member) -> CreditNote:
    return sales.credit_invoice(member.user, _invoice(member, True), timezone.localdate())


tenant_endpoint("api/sales/customers/<int:pk>/statement/")(
    lambda m: (f"/api/sales/customers/{_customer(m).pk}/statement/", _customer(m).pk)
)
tenant_endpoint("api/purchasing/suppliers/<int:pk>/statement/")(
    lambda m: (f"/api/purchasing/suppliers/{_supplier(m).pk}/statement/", _supplier(m).pk)
)
tenant_endpoint("api/sales/ageing/")(
    lambda m: ("/api/sales/ageing/", _invoice(m, True).customer_id)
)
tenant_endpoint("api/purchasing/ageing/")(
    lambda m: ("/api/purchasing/ageing/", _posted_bill(m).supplier_id)
)


def _chat(member: Member) -> tuple[str, int]:
    return "/api/assistant/messages/", assistant.record(member.user, "user", "Private").pk


def _chat_check(member: Member) -> tuple[str, int]:
    assistant.record(member.user, "user", "Private")
    return "/api/assistant/check/", 0


def _chat_draft(member: Member) -> int:
    _customer(member)
    card = drafts.build(
        "draft_sales_invoice",
        json.dumps({"customer": "C-P", "items": [{"product": "P1", "quantity": 1}]}),
    )
    return assistant.record(member.user, "draft", json.dumps(card)).pk


tenant_endpoint("api/assistant/messages/")(_chat)
tenant_endpoint("api/assistant/check/")(_chat_check)


def _automation(member: Member) -> tuple[str, int]:
    Tenant.objects.filter(pk=member.tenant.pk).update(daily_summary=False)
    return "/api/automation/", 0


tenant_endpoint("api/automation/")(_automation)


def _department(member: Member) -> Department:
    department: Department = Department.objects.get_or_create(
        code="D-P", defaults={"name": "Private"}
    )[0]
    return department


def _structure(member: Member) -> SalaryStructure:
    found = SalaryStructure.objects.filter(name="Private").first()
    return found or hr.save_structure(
        member.user, {"name": "Private"}, [hr.ComponentInput("Rent", "earning", None, Decimal(10))]
    )


def _employee(member: Member) -> Employee:
    found: Employee | None = Employee.objects.filter(code="E-P").first()
    if found is None:
        found = Employee.objects.create(
            code="E-P",
            full_name="Private",
            joined_on=timezone.localdate(),
            department=_department(member),
        )
    return found


def _contract(member: Member) -> Contract:
    found = Contract.objects.filter(employee=_employee(member)).first()
    return found or hr.save_contract(
        member.user,
        {
            "employee": _employee(member),
            "structure": _structure(member),
            "starts_on": timezone.localdate(),
            "basic_salary": Decimal(1000),
        },
    )


tenant_endpoint("api/hr/departments/")(lambda m: ("/api/hr/departments/", _department(m).pk))
tenant_endpoint("api/hr/departments/<int:pk>/")(
    lambda m: (f"/api/hr/departments/{_department(m).pk}/", _department(m).pk)
)
tenant_endpoint("api/hr/salary-structures/")(
    lambda m: ("/api/hr/salary-structures/", _structure(m).pk)
)
tenant_endpoint("api/hr/salary-structures/<int:pk>/")(
    lambda m: (f"/api/hr/salary-structures/{_structure(m).pk}/", _structure(m).pk)
)
tenant_endpoint("api/hr/salary-structures/<int:pk>/preview/")(
    lambda m: (
        f"/api/hr/salary-structures/{_structure(m).pk}/preview/?basic=100",
        _structure(m).pk,
    )
)
tenant_endpoint("api/hr/employees/")(lambda m: ("/api/hr/employees/", _employee(m).pk))
tenant_endpoint("api/hr/employees/<int:pk>/")(
    lambda m: (f"/api/hr/employees/{_employee(m).pk}/", _employee(m).pk)
)


def _holiday(member: Member) -> Holiday:
    holiday: Holiday = Holiday.objects.get_or_create(
        on=timezone.localdate(), defaults={"name": "Private"}
    )[0]
    return holiday


def _leave_type(member: Member) -> LeaveType:
    kind: LeaveType = LeaveType.objects.get_or_create(
        name="Private", defaults={"days_per_year": 0}
    )[0]
    return kind


def _leave(member: Member) -> LeaveRequest:
    found: LeaveRequest | None = LeaveRequest.objects.filter(employee=_employee(member)).first()
    if found is None:
        found = LeaveRequest.objects.create(
            employee=_employee(member),
            leave_type=_leave_type(member),
            starts_on=timezone.localdate(),
            ends_on=timezone.localdate(),
            days=Decimal(1),
        )
    return found


def _hr_settings(member: Member) -> tuple[str, int]:
    time_off.save_settings(member.user, {"weekend": [4, 5]})
    return "/api/hr/settings/", 0


def _attendance(member: Member) -> tuple[str, int]:
    _employee(member)
    return f"/api/hr/attendance/?date={timezone.localdate()}", _employee(member).pk


tenant_endpoint("api/hr/settings/")(_hr_settings)
tenant_endpoint("api/hr/holidays/")(lambda m: ("/api/hr/holidays/", _holiday(m).pk))
tenant_endpoint("api/hr/holidays/<int:pk>/")(
    lambda m: (f"/api/hr/holidays/{_holiday(m).pk}/", _holiday(m).pk)
)
tenant_endpoint("api/hr/leave-types/")(lambda m: ("/api/hr/leave-types/", _leave_type(m).pk))
tenant_endpoint("api/hr/leave-types/<int:pk>/")(
    lambda m: (f"/api/hr/leave-types/{_leave_type(m).pk}/", _leave_type(m).pk)
)
tenant_endpoint("api/hr/leave/")(lambda m: ("/api/hr/leave/", _leave(m).pk))
tenant_endpoint("api/hr/leave/<int:pk>/")(
    lambda m: (f"/api/hr/leave/{_leave(m).pk}/", _leave(m).pk)
)
tenant_endpoint("api/hr/leave/balances/")(
    lambda m: (f"/api/hr/leave/balances/?employee={_employee(m).pk}", _employee(m).pk)
)
tenant_endpoint("api/hr/attendance/")(_attendance)
tenant_endpoint("api/hr/contracts/")(lambda m: ("/api/hr/contracts/", _contract(m).pk))
tenant_endpoint("api/hr/contracts/<int:pk>/")(
    lambda m: (f"/api/hr/contracts/{_contract(m).pk}/", _contract(m).pk)
)


def _tax_table(member: Member) -> TaxTable:
    today = timezone.localdate()
    found: TaxTable | None = TaxTable.objects.first()
    return found or payroll_tax.save_table(
        member.user,
        {
            "country": "PK",
            "name": "Private",
            "starts_on": today.replace(month=1, day=1),
            "ends_on": today.replace(month=12, day=31),
            "source": "Invented",
        },
        [Slab(Decimal(0), Decimal(0), Decimal(0))],
    )


def _payroll(member: Member, post: bool = False) -> PayrollRun:
    found: PayrollRun | None = PayrollRun.objects.first()
    if found is None:
        _books(member)
        _tax_table(member)
        _contract(member)
        found = payroll.work_out(member.user, timezone.localdate())
        if post:
            assert payroll.post(member.user, found)
            found.refresh_from_db()
    return found


def _payslip(member: Member) -> Payslip:
    found: Payslip = Payslip.objects.get(run=_payroll(member, post=True))
    return found


tenant_endpoint("api/payroll/tax-tables/")(
    lambda m: ("/api/payroll/tax-tables/", _tax_table(m).pk)
)
tenant_endpoint("api/payroll/tax-tables/<int:pk>/")(
    lambda m: (f"/api/payroll/tax-tables/{_tax_table(m).pk}/", _tax_table(m).pk)
)
tenant_endpoint("api/payroll/runs/")(lambda m: ("/api/payroll/runs/", _payroll(m).pk))
tenant_endpoint("api/payroll/runs/<int:pk>/")(
    lambda m: (f"/api/payroll/runs/{_payroll(m).pk}/", _payroll(m).pk)
)
tenant_endpoint("api/payroll/payslips/<int:pk>/pdf/")(
    lambda m: (f"/api/payroll/payslips/{_payslip(m).pk}/pdf/", 0)
)


def _bill_settings(member: Member) -> tuple[str, int]:
    billing.save(member.user, {"address": "Private Street"})
    return "/api/sales/bill-settings/", 0


def _bill_logo(member: Member) -> tuple[str, int]:
    picture = io.BytesIO()
    Image.new("RGB", (20, 20)).save(picture, format="PNG")
    billing.set_image(member.user, "logo", picture.getvalue())
    return "/api/sales/bill-settings/logo/", 0


tenant_endpoint("api/sales/bill-settings/")(_bill_settings)
tenant_endpoint("api/sales/bill-settings/logo/")(_bill_logo)


def _bill_signature(member: Member) -> tuple[str, int]:
    picture = io.BytesIO()
    Image.new("RGB", (40, 20)).save(picture, format="PNG")
    billing.set_image(member.user, "signature", picture.getvalue())
    return "/api/sales/bill-settings/signature/", 0


tenant_endpoint("api/sales/bill-settings/signature/")(_bill_signature)
tenant_endpoint("api/sales/invoices/<int:pk>/share/")(
    lambda m: (f"/api/sales/invoices/{_invoice(m, True).pk}/share/", 0)
)
tenant_endpoint("api/sales/invoices/<int:pk>/pdf/")(
    lambda m: (f"/api/sales/invoices/{_invoice(m, True).pk}/pdf/", 0)
)
tenant_endpoint("api/sales/receipts/<int:pk>/pdf/")(
    lambda m: (
        f"/api/sales/receipts/{sales.post_receipt(m.user, _sales_receipt(m)).pk}/pdf/",
        0,
    )
)


def _report(path: str) -> Callable[[Member], tuple[str, int]]:
    def make(member: Member) -> tuple[str, int]:
        _invoice(member, True)
        sales.post_receipt(member.user, _sales_receipt(member))
        return f"/api/reports/{path}/", 0

    return make


for _path in ("dashboard", "home", "profit-loss", "balance-sheet", "cash-flow", "sales-tax"):
    tenant_endpoint(f"api/reports/{_path}/")(_report(_path))


def _tax_rate(member: Member) -> int:
    _books(member)
    rate: TaxRate = TaxRate.objects.create(
        name="Private", rate=Decimal(18), valid_from=timezone.localdate(), source="Invented"
    )
    return rate.pk


_register("accounting/tax-rates", _tax_rate)
tenant_endpoint("api/sales/tax-rates/")(lambda m: ("/api/sales/tax-rates/", _tax_rate(m)))


def _till(member: Member) -> PosSession:
    shop = _shop(member)
    open_till = PosSession.objects.filter(status="open").first()
    return open_till or pos.open_till(member.user, shop["warehouse"], Decimal(0))


def _pos_sale(member: Member) -> int:
    _stock_level(member)
    shop = _shop(member)
    shop["product"].sale_price = Decimal(5)
    shop["product"].save()
    line = pos.CartLine(shop["product"], shop["unit"], Decimal(1))
    return pos.sell(member.user, _till(member), [line], "card").pk


_register("pos/sessions", lambda m: _till(m).pk)
tenant_endpoint("api/pos/sales/<int:pk>/receipt/")(
    lambda m: (f"/api/pos/sales/{_pos_sale(m)}/receipt/", 0)
)
tenant_endpoint("api/pos/warehouses/")(
    lambda m: ("/api/pos/warehouses/", _shop(m)["warehouse"].pk)
)
tenant_endpoint("api/pos/tax-rates/")(lambda m: ("/api/pos/tax-rates/", _tax_rate(m)))
tenant_endpoint("api/pos/products/")(
    lambda m: ("/api/pos/products/?q=Private", _shop(m)["product"].pk)
)
_register("sales/customers", lambda m: _customer(m).pk)
_register("sales/orders", lambda m: _sales_order(m).pk)
_register("sales/invoices", lambda m: _invoice(m).pk)
_register("sales/receipts", lambda m: _sales_receipt(m).pk)
_register("sales/credit-notes", lambda m: _credit_note(m).pk)
_register("purchasing/suppliers", lambda m: _supplier(m).pk)
_register("purchasing/orders", lambda m: _order(m).pk)
_register("purchasing/receipts", _receipt)
_register("purchasing/bills", _bill)
_register("purchasing/payments", _payment)

# POST-only actions on one tenant-owned row. An outsider must get 404 and change nothing.
TENANT_ACTIONS: dict[str, Callable[[Member], str]] = {
    "api/accounting/entries/<int:pk>/post/": lambda m: (
        f"/api/accounting/entries/{_draft(m)}/post/"
    ),
    "api/hr/leave/<int:pk>/approve/": lambda m: f"/api/hr/leave/{_leave(m).pk}/approve/",
    "api/hr/leave/<int:pk>/reject/": lambda m: f"/api/hr/leave/{_leave(m).pk}/reject/",
    "api/payroll/runs/<int:pk>/post/": lambda m: f"/api/payroll/runs/{_payroll(m).pk}/post/",
    "api/assistant/drafts/<int:pk>/confirm/": lambda m: (
        f"/api/assistant/drafts/{_chat_draft(m)}/confirm/"
    ),
    "api/inventory/stock-entries/<int:pk>/post/": lambda m: (
        f"/api/inventory/stock-entries/{_stock_draft(m)}/post/"
    ),
    "api/accounting/entries/<int:pk>/reverse/": lambda m: (
        f"/api/accounting/entries/{_posted(m)}/reverse/"
    ),
    "api/pos/sessions/<int:pk>/sale/": lambda m: f"/api/pos/sessions/{_till(m).pk}/sale/",
    "api/members/<int:pk>/make-owner/": lambda m: f"/api/members/{_member(m)}/make-owner/",
    "api/pos/sessions/<int:pk>/close/": lambda m: f"/api/pos/sessions/{_till(m).pk}/close/",
    "api/sales/orders/<int:pk>/quote/": lambda m: f"/api/sales/orders/{_sales_order(m).pk}/quote/",
    "api/sales/orders/<int:pk>/confirm/": lambda m: (
        f"/api/sales/orders/{_sales_order(m).pk}/confirm/"
    ),
    "api/sales/orders/<int:pk>/close/": lambda m: (
        f"/api/sales/orders/{_sales_order(m, True).pk}/close/"
    ),
    "api/sales/orders/<int:pk>/invoice/": lambda m: (
        f"/api/sales/orders/{_sales_order(m, True).pk}/invoice/"
    ),
    "api/sales/invoices/<int:pk>/post/": lambda m: f"/api/sales/invoices/{_invoice(m).pk}/post/",
    "api/sales/invoices/<int:pk>/credit/": lambda m: (
        f"/api/sales/invoices/{_invoice(m, True).pk}/credit/"
    ),
    "api/sales/receipts/<int:pk>/post/": lambda m: (
        f"/api/sales/receipts/{_sales_receipt(m).pk}/post/"
    ),
    "api/sales/credit-notes/<int:pk>/post/": lambda m: (
        f"/api/sales/credit-notes/{_credit_note(m).pk}/post/"
    ),
    "api/purchasing/orders/<int:pk>/confirm/": lambda m: (
        f"/api/purchasing/orders/{_order(m).pk}/confirm/"
    ),
    "api/purchasing/orders/<int:pk>/close/": lambda m: (
        f"/api/purchasing/orders/{_order(m, True).pk}/close/"
    ),
    "api/purchasing/orders/<int:pk>/receive/": lambda m: (
        f"/api/purchasing/orders/{_order(m, True).pk}/receive/"
    ),
    "api/purchasing/receipts/<int:pk>/post/": lambda m: (
        f"/api/purchasing/receipts/{_receipt(m)}/post/"
    ),
    "api/purchasing/receipts/<int:pk>/bill/": lambda m: (
        f"/api/purchasing/receipts/{_receipt(m, post=True)}/bill/"
    ),
    "api/purchasing/bills/<int:pk>/post/": lambda m: f"/api/purchasing/bills/{_bill(m)}/post/",
    "api/purchasing/payments/<int:pk>/post/": lambda m: (
        f"/api/purchasing/payments/{_payment(m)}/post/"
    ),
}


def _routes(resolver: URLResolver, prefix: str = "") -> Iterator[str]:
    for entry in resolver.url_patterns:
        route = prefix + str(entry.pattern)
        if isinstance(entry, URLResolver):
            yield from _routes(entry, route)
        elif isinstance(entry, URLPattern):
            yield route


def _views(resolver: URLResolver, prefix: str = "") -> Iterator[tuple[str, object]]:
    for entry in resolver.url_patterns:
        route = prefix + str(entry.pattern)
        if isinstance(entry, URLResolver):
            yield from _views(entry, route)
        elif isinstance(entry, URLPattern):
            yield route, getattr(entry.callback, "cls", None)


def test_every_api_view_has_a_throttle_scope() -> None:
    rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    for route, view in _views(get_resolver()):
        if not route.startswith("api/") or route == "api/schema/":
            continue
        scope = getattr(view, "throttle_scope", None)
        assert scope in rates, f"{route} needs a throttle_scope with a rate in settings"


def test_every_endpoint_is_classified() -> None:
    api_routes = {r for r in _routes(get_resolver()) if r.startswith("api/")}
    classified = PUBLIC | USER_LEVEL | set(TENANT_OWNED) | set(TENANT_ACTIONS)
    assert api_routes - classified == set(), "classify new endpoints in test_isolation.py"
    assert classified - api_routes == set(), "remove deleted endpoints from test_isolation.py"


@pytest.mark.django_db
@pytest.mark.parametrize("route", sorted(TENANT_OWNED))
def test_other_tenants_rows_are_invisible(
    route: str,
    owner: Member,
    outsider: Member,
    in_tenant: Callable[[Tenant], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The PDF libraries aren't on every machine; who may fetch one is what's under test here.
    monkeypatch.setattr("apps.sales.documents.to_pdf", lambda html: b"%PDF")
    in_tenant(owner.tenant)
    url, row_id = TENANT_OWNED[route](owner)

    mine = owner.client().get(url)
    assert mine.status_code == 200

    theirs = outsider.client().get(url)
    special = SPECIAL_CHECKS.get(route)
    if special is not None:
        special(mine, theirs, row_id)
    elif "<" in route:
        assert theirs.status_code == 404
        for method in ("patch", "delete"):
            assert getattr(outsider.client(), method)(url, {}, format="json").status_code in (
                404,
                405,
            )
    elif route.startswith("api/reports/"):
        # The owner sold something worth 5.00; none of it may reach another business's report.
        assert theirs.status_code == 200
        assert mine.json() != theirs.json()
        assert '"5.00"' not in theirs.content.decode()
    else:
        assert theirs.status_code == 200
        assert row_id not in _row_ids(theirs.json())


def _row_ids(body: Any) -> list[int]:
    if isinstance(body, dict) and "low_stock" in body:
        return [row["product"] for row in body["low_stock"]]
    rows = body if isinstance(body, list) else body.get("results", body.get("rows"))
    return [row["id"] for row in rows]


def _not_found(mine: Any, theirs: Any, row_id: int) -> None:
    # The owner's row exists; for another business there is no such thing to show.
    assert theirs.status_code == 404


def _same_shape(field: str, owners: Any, others: Any) -> Callable[[Any, Any, int], None]:
    """A one-per-business setting: the owner's change must not show for anyone else."""

    def check(mine: Any, theirs: Any, row_id: int) -> None:
        assert theirs.status_code == 200
        assert mine.json()[field] == owners
        assert theirs.json()[field] == others

    return check


def _no_stock_value(mine: Any, theirs: Any, row_id: int) -> None:
    assert theirs.json() == {"total_value": "0.00", "lines": 0}


def _attendance_rows(mine: Any, theirs: Any, row_id: int) -> None:
    assert theirs.status_code == 200
    assert row_id not in [person["employee"] for person in theirs.json()["people"]]


def _automation_check(mine: Any, theirs: Any, row_id: int) -> None:
    # The owner turned theirs off; that must not reach another business.
    assert mine.json() == {"daily_summary": False}
    assert theirs.json() == {"daily_summary": True}


SPECIAL_CHECKS: dict[str, Callable[[Any, Any, int], None]] = {
    "api/hr/leave/balances/": _not_found,
    "api/sales/bill-settings/logo/": _not_found,
    "api/sales/bill-settings/signature/": _not_found,
    "api/assistant/check/": _same_shape("count", 1, 0),
    "api/hr/settings/": _same_shape("weekend", [4, 5], [6]),
    "api/sales/bill-settings/": _same_shape("address", "Private Street", ""),
    "api/hr/attendance/": _attendance_rows,
    "api/automation/": _automation_check,
    "api/inventory/stock-value/": _no_stock_value,
}


@pytest.mark.django_db
@pytest.mark.parametrize("route", sorted(TENANT_ACTIONS))
def test_other_tenants_rows_cannot_be_acted_on(
    route: str, owner: Member, outsider: Member, in_tenant: Callable[[Tenant], None]
) -> None:
    in_tenant(owner.tenant)
    url = TENANT_ACTIONS[route](owner)
    before = list(JournalEntry.all_tenants.values_list("id", "status", "number"))
    stock_before = list(StockEntry.all_tenants.values_list("id", "status"))
    documents = [PurchaseOrder, GoodsReceipt, Bill, SupplierPayment, Invoice, SalesOrder]
    documents_before = [list(m.all_tenants.values_list("id", "status")) for m in documents]
    response = outsider.client().post(url, {"date": str(timezone.localdate())}, format="json")
    assert response.status_code == 404
    assert list(JournalEntry.all_tenants.values_list("id", "status", "number")) == before
    assert list(StockEntry.all_tenants.values_list("id", "status")) == stock_before
    assert [list(m.all_tenants.values_list("id", "status")) for m in documents] == (
        documents_before
    )
