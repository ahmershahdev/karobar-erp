"""Build a demo business with a year of documents.

Everything goes through the same services the screens use, so the books balance, stock moves
under its locks, and each document is numbered and audited as if a person had made it. Only
the dates are in the past. A fixed random seed makes two runs give the same business.
"""

import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db.models import F, Sum

from apps.accounting import services as accounting
from apps.accounting.models import Account, FiscalYear, JournalLine, TaxRate
from apps.accounts.models import User
from apps.hr import services as hr
from apps.hr import time_off
from apps.hr.models import Attendance, Department, Employee, LeaveType
from apps.inventory import services as inventory
from apps.inventory.models import Batch as StockBatch
from apps.inventory.models import Category, Product, Unit, Warehouse
from apps.payroll import contributions, gratuity, payments, runs
from apps.payroll import services as payroll
from apps.payroll.models import ContributionRate, PayrollRun, TaxTable
from apps.purchasing import services as purchasing
from apps.purchasing.models import Bill, Supplier
from apps.sales import services as sales
from apps.sales.models import Customer, Invoice
from apps.tenancy import services as tenancy
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

from . import data
from .data import Item, Party, Plan
from .models import DemoBusiness

D = Decimal
ZERO = D(0)
CENT = D("0.01")

# Who buys each kind of item, by supplier position in the plan.
BUYS_FROM = {
    "Grocery": 0,
    "Dairy": 2,
    "Spices": 3,
    "Snacks": 4,
    "Beverages": 5,
    "Personal care": 6,
    "Household": 6,
    "Fresh": 7,
    "Bakery": 7,
}
OIL = ("OIL-", "GHEE-")
OPENING_CAPITAL = {"pk": D(6_000_000), "ae": D(400_000)}
CASH_FLOAT = {"pk": D(25_000), "ae": D(2_000)}
SHELF_DAYS = {"Dairy": 45, "Fresh": 20, "Bakery": 20}


@dataclass
class Batch:
    number: str
    expiry: date
    quantity: Decimal


@dataclass
class Stocked:
    item: Item
    product: Product
    supplier: Supplier
    # Kept in pieces, the product's base unit.
    on_hand: Decimal
    target: Decimal
    batches: list[Batch]


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def month_start(day: date) -> date:
    return day.replace(day=1)


def next_month(day: date) -> date:
    return (day.replace(day=28) + timedelta(days=4)).replace(day=1)


class Seeder:
    def __init__(self, owner: User, plan: Plan, today: date, days: int, seed: int = 1) -> None:
        self.owner = owner
        self.plan = plan
        self.today = today
        self.start = today - timedelta(days=days)
        # Invented data, not security: a fixed seed gives the same business every night.
        self.rng = random.Random(f"{plan.kind}-{seed}")  # noqa: S311
        self.counts: dict[str, int] = {}

    # Setup

    def run(self) -> Tenant:
        membership = tenancy.create_tenant(
            self.owner,
            self.plan.name,
            self.plan.currency,
            self.plan.locale,
            fiscal_year_start_month=self.plan.fiscal_month,
            valuation_method=self.plan.valuation,
        )
        tenant = membership.tenant
        DemoBusiness.objects.create(tenant=tenant, kind=self.plan.kind)
        with tenant_context(tenant):
            self.books()
            self.masters()
            self.open_shop()
            self.trade()
            self.staff()
            self.payroll()
        return tenant

    def books(self) -> None:
        """Fiscal years back to the first day of the history; the current one exists already."""
        first = FiscalYear.objects.order_by("start").first()
        if first is None:
            first = accounting.create_current_fiscal_year(self.owner, self.plan.fiscal_month)
        while first.start > self.start:
            end = first.start - timedelta(days=1)
            begin = date(end.year - 1, end.month, end.day) + timedelta(days=1)
            first = accounting.create_fiscal_year(self.owner, begin, end)
        self.bank = Account.objects.get(role="bank")
        self.cash = Account.objects.get(role="cash")
        self.capital = Account.objects.get(role="capital")
        self.adjustments = Account.objects.get(role="inventory_adjustments")
        self.rent_account = Account.objects.get(code="6200")
        self.power_account = Account.objects.get(code="6300")
        self.tax = accounting.save_tax_rate(
            self.owner,
            TaxRate(),
            {
                "name": self.plan.tax_name,
                "rate": self.plan.tax_percent,
                "valid_from": self.plan.tax_from,
                "valid_to": None,
                "source": self.plan.tax_source,
            },
        )

    def masters(self) -> None:
        self.pcs = Unit.objects.create(code="PCS", name="Piece")
        self.ctn = Unit.objects.create(code="CTN", name="Carton")
        self.main = Warehouse.objects.create(code="MAIN", name="Main shop")
        Warehouse.objects.create(code="STORE", name="Store room")
        categories = {
            name: Category.objects.create(name=name)
            for name in dict.fromkeys(item.category for item in self.plan.items)
        }
        suppliers = [self.supplier(party) for party in self.plan.suppliers]
        self.landlord = self.supplier(self.plan.landlord)
        self.utility = self.supplier(self.plan.utility)
        self.stock: list[Stocked] = []
        for number, item in enumerate(self.plan.items, start=1):
            target = D(item.carton * 3) if item.carton else D(36)
            code = data.barcode(self.plan.kind, number)
            packs = [inventory.PackInput(self.ctn, D(item.carton), code)] if item.carton else []
            product = inventory.save_product(
                self.owner,
                {
                    "sku": item.sku,
                    "name": item.name,
                    "category_id": categories[item.category].pk,
                    "unit_id": self.pcs.pk,
                    "track_batches": item.batches,
                    "reorder_level": (target / 3).quantize(D(1)),
                    "sale_price": item.price,
                },
                packs,
            )
            index = 1 if item.sku.startswith(OIL) else BUYS_FROM[item.category]
            self.stock.append(Stocked(item, product, suppliers[index], ZERO, target, []))
        self.customers = [self.customer(party) for party in self.plan.customers]
        self.walk_in, self.regulars = self.customers[0], self.customers[1:]

    def supplier(self, party: Party) -> Supplier:
        made: Supplier = purchasing.save_supplier(
            self.owner,
            Supplier(),
            {
                "code": party.code,
                "name": party.name,
                "phone": party.phone,
                "payment_terms_days": party.terms,
            },
        )
        return made

    def customer(self, party: Party) -> Customer:
        made: Customer = sales.save_customer(
            self.owner,
            Customer(),
            {
                "code": party.code,
                "name": party.name,
                "phone": party.phone,
                "payment_terms_days": party.terms,
            },
        )
        return made

    def open_shop(self) -> None:
        """The owner puts money in the bank and counts the stock already on the shelves."""
        capital = OPENING_CAPITAL[self.plan.kind]
        entry = accounting.save_draft(
            self.owner,
            self.start,
            "Owner's capital",
            [
                accounting.LineInput(self.bank, capital, ZERO),
                accounting.LineInput(self.capital, ZERO, capital),
            ],
        )
        accounting.post_entry(self.owner, entry)
        lines = []
        for row in self.stock:
            quantity = row.target
            lines.append(self.stock_line(row, quantity, self.start))
            self.add(row, quantity, self.start)
        draft = inventory.save_draft(
            self.owner,
            {
                "kind": "receipt",
                "date": self.start,
                "memo": "Opening stock",
                "warehouse": self.main,
                "to_warehouse": None,
                "contra_account": self.capital,
            },
            lines,
        )
        inventory.post_entry(self.owner, draft)

    def stock_line(self, row: Stocked, quantity: Decimal, on: date) -> inventory.LineInput:
        number, expiry = self.batch_for(row, on)
        return inventory.LineInput(row.product, self.pcs, quantity, row.item.cost, number, expiry)

    def batch_for(self, row: Stocked, on: date) -> tuple[str, date | None]:
        if not row.item.batches:
            return "", None
        days = SHELF_DAYS.get(row.item.category, 180)
        return f"{row.item.sku}-{on:%y%m%d}", on + timedelta(days=days)

    def add(self, row: Stocked, quantity: Decimal, on: date) -> None:
        row.on_hand += quantity
        number, expiry = self.batch_for(row, on)
        if expiry is not None:
            row.batches.append(Batch(number, expiry, quantity))

    # A year of trading

    def trade(self) -> None:
        day = self.start + timedelta(days=1)
        while day < self.today:
            if day.day == 1:
                self.monthly_bills(day)
            if day.weekday() == 0:
                self.restock(day)
                self.deposit(day)
            if day.weekday() == 3:
                self.pay_suppliers(day)
                self.collect(day)
            if day.weekday() == 4 and self.rng.random() < 0.5:
                self.take_back(day)
            low, high = self.plan.sales_a_day
            for _ in range(self.rng.randint(low, high)):
                self.sell(day)
            day += timedelta(days=1)

    def count(self, key: str) -> None:
        self.counts[key] = self.counts.get(key, 0) + 1

    def sell(self, day: date) -> None:
        credit = self.rng.random() < 0.35
        customer = self.rng.choice(self.regulars) if credit else self.walk_in
        lines = []
        for row in self.rng.sample(self.stock, self.rng.randint(2, 7)):
            if credit and row.item.carton and row.on_hand >= row.item.carton:
                unit, factor = self.ctn, D(row.item.carton)
                quantity = D(1)
                price = row.item.price * factor
            else:
                unit, factor = self.pcs, D(1)
                quantity = D(self.rng.randint(1, 8 if credit else 4))
                price = row.item.price
            pieces = quantity * factor
            batch = self.take(row, pieces, day)
            if batch is None:
                continue
            lines.append(
                sales.InvoiceLineInput(
                    row.product, unit, quantity, price, batch_number=batch, tax_rate=self.tax
                )
            )
        if not lines:
            return
        due = day + timedelta(days=max(customer.payment_terms_days, 0))
        draft = sales.save_invoice(
            self.owner,
            {"customer": customer, "warehouse": self.main, "date": day, "due_date": due},
            lines,
        )
        invoice = sales.post_invoice(self.owner, draft)
        self.count("sales bills")
        if not credit:
            self.receive(customer, day, invoice.total, [(invoice, invoice.total)], self.cash)

    def available(self, row: Stocked, day: date) -> Decimal:
        """What can still be sold: a batch past its expiry date doesn't count."""
        if not row.item.batches:
            return row.on_hand
        return sum((b.quantity for b in row.batches if b.expiry > day), ZERO)

    def take(self, row: Stocked, pieces: Decimal, day: date) -> str | None:
        """Take stock for a sale, or None when there isn't enough. A batch item comes from the
        batch that expires first and still has enough in it."""
        if self.available(row, day) < pieces:
            return None
        if not row.item.batches:
            row.on_hand -= pieces
            return ""
        for batch in sorted(row.batches, key=lambda b: b.expiry):
            if batch.quantity >= pieces and batch.expiry > day:
                batch.quantity -= pieces
                row.on_hand -= pieces
                row.batches = [b for b in row.batches if b.quantity > 0]
                return batch.number
        return None

    def receive(
        self,
        customer: Customer,
        day: date,
        amount: Decimal,
        allocations: list[tuple[Invoice, Decimal]],
        into: Account,
    ) -> None:
        draft = sales.save_receipt(
            self.owner,
            {"customer": customer, "date": day, "amount": amount, "received_into": into},
            [sales.AllocationInput(invoice, value) for invoice, value in allocations],
        )
        sales.post_receipt(self.owner, draft)
        self.count("money received")

    def collect(self, day: date) -> None:
        """Regular customers pay what has fallen due, most of them on time."""
        due = (
            Invoice.objects.filter(
                customer__in=self.regulars,
                status=Invoice.Status.POSTED,
                due_date__lte=day,
                total__gt=F("amount_paid") + F("amount_credited"),
            )
            .select_related("customer")
            .order_by("customer_id", "date")
        )
        owed: dict[int, list[tuple[Invoice, Decimal]]] = {}
        for invoice in due:
            left = invoice.total - invoice.amount_paid - invoice.amount_credited
            owed.setdefault(invoice.customer_id, []).append((invoice, left))
        for rows in owed.values():
            # A few customers fall behind, so the ageing report has something to show.
            if self.rng.random() < 0.15:
                continue
            total = sum((left for _, left in rows), ZERO)
            self.receive(rows[0][0].customer, day, total, rows, self.bank)

    def take_back(self, day: date) -> None:
        """Now and then a regular customer brings back a whole small bill."""
        recent = (
            Invoice.objects.filter(
                customer__in=self.regulars,
                status=Invoice.Status.POSTED,
                date__gte=day - timedelta(days=10),
                amount_paid=0,
                amount_credited=0,
            )
            .order_by("total")
            .first()
        )
        if recent is None:
            return
        note = sales.credit_invoice(self.owner, recent, day)
        sales.post_credit_note(self.owner, note)
        for line in recent.lines.select_related("product"):
            row = next(r for r in self.stock if r.product.pk == line.product_id)
            pieces = line.quantity * (D(row.item.carton) if line.unit_id == self.ctn.pk else D(1))
            row.on_hand += pieces
            if row.item.batches:
                expiry = StockBatch.objects.get(
                    product=row.product, number=line.batch_number
                ).expiry_date
                same = next((b for b in row.batches if b.number == line.batch_number), None)
                if same is not None:
                    same.quantity += pieces
                elif expiry is not None:
                    row.batches.append(Batch(line.batch_number, expiry, pieces))
        self.count("returns")

    def restock(self, day: date) -> None:
        """Each Monday, throw away what has expired, then top up what is running low."""
        self.write_off(day)
        wanted: dict[int, list[Stocked]] = {}
        for row in self.stock:
            if self.available(row, day) < row.target * D("0.6"):
                wanted.setdefault(row.supplier.pk, []).append(row)
        for rows in wanted.values():
            supplier = rows[0].supplier
            if any(row.item.batches for row in rows):
                self.buy_direct(day, supplier, rows)
            else:
                self.buy_on_order(day, supplier, rows)

    def write_off(self, day: date) -> None:
        lines = []
        for row in self.stock:
            for batch in [b for b in row.batches if b.expiry <= day and b.quantity > 0]:
                lines.append(
                    inventory.LineInput(row.product, self.pcs, batch.quantity, None, batch.number)
                )
                row.on_hand -= batch.quantity
                batch.quantity = ZERO
            row.batches = [b for b in row.batches if b.quantity > 0]
        if not lines:
            return
        draft = inventory.save_draft(
            self.owner,
            {
                "kind": "issue",
                "date": day,
                "memo": "Expired stock thrown away",
                "warehouse": self.main,
                "to_warehouse": None,
                "contra_account": self.adjustments,
            },
            lines,
        )
        inventory.post_entry(self.owner, draft)
        self.count("expired write-offs")

    def cartons(self, row: Stocked) -> Decimal:
        """How many cartons (or pieces) to buy to get back above the target."""
        short = row.target * D("1.5") - row.on_hand
        if row.item.carton:
            return max((short / row.item.carton).quantize(D(1)), D(1))
        return max(short.quantize(D(1)), D(1))

    def buy_on_order(self, day: date, supplier: Supplier, rows: list[Stocked]) -> None:
        lines = []
        for row in rows:
            unit, factor = (self.ctn, D(row.item.carton)) if row.item.carton else (self.pcs, D(1))
            lines.append(
                purchasing.OrderLineInput(
                    row.product, unit, self.cartons(row), row.item.cost * factor
                )
            )
        order = purchasing.save_order(
            self.owner,
            {"supplier": supplier, "date": day, "expected_date": day, "warehouse": self.main},
            lines,
        )
        order = purchasing.confirm_order(self.owner, order)
        receipt = purchasing.receive_order(self.owner, order, day)
        receipt = purchasing.post_receipt(self.owner, receipt)
        for row, line in zip(rows, lines, strict=True):
            factor = D(row.item.carton) if row.item.carton else D(1)
            self.add(row, line.quantity * factor, day)
        self.bill(day, receipt)
        self.count("purchase orders")

    def buy_direct(self, day: date, supplier: Supplier, rows: list[Stocked]) -> None:
        """Fresh goods arrive with a batch and expiry on the delivery note, without an order."""
        lines = []
        for row in rows:
            pieces = self.cartons(row) * (D(row.item.carton) if row.item.carton else D(1))
            number, expiry = self.batch_for(row, day)
            lines.append(
                purchasing.ReceiptLineInput(
                    row.product, self.pcs, pieces, row.item.cost, None, number, expiry
                )
            )
            self.add(row, pieces, day)
        receipt = purchasing.save_receipt(
            self.owner, {"supplier": supplier, "date": day, "warehouse": self.main}, lines
        )
        receipt = purchasing.post_receipt(self.owner, receipt)
        self.bill(day, receipt)

    def bill(self, day: date, receipt: Any) -> None:
        draft = purchasing.bill_receipt(self.owner, receipt, day)
        terms = receipt.supplier.payment_terms_days
        draft.due_date = day + timedelta(days=terms)
        draft.supplier_reference = f"INV-{receipt.supplier.code}-{day:%y%m%d}"
        draft.save(update_fields=["due_date", "supplier_reference"])
        purchasing.post_bill(self.owner, draft)
        self.count("supplier bills")

    def pay_suppliers(self, day: date) -> None:
        """Each Thursday, pay the bills that have fallen due, from the bank."""
        for supplier in Supplier.objects.order_by("pk"):
            rows = [
                (bill, bill.total - bill.amount_paid)
                for bill in purchasing.outstanding_bills(supplier).filter(due_date__lte=day)
            ]
            if not rows:
                continue
            self.pay(supplier, day, rows)

    def pay(self, supplier: Supplier, day: date, rows: list[tuple[Bill, Decimal]]) -> None:
        total = sum((left for _, left in rows), ZERO)
        draft = purchasing.save_payment(
            self.owner,
            {"supplier": supplier, "date": day, "amount": total, "paid_from": self.bank},
            [purchasing.AllocationInput(bill, left) for bill, left in rows],
        )
        purchasing.post_payment(self.owner, draft)
        self.count("supplier payments")

    def monthly_bills(self, day: date) -> None:
        """Rent on the first, and the electricity bill, both paid straight away."""
        low, high = self.plan.power
        for supplier, account, amount, what in (
            (self.landlord, self.rent_account, self.plan.rent, "Shop rent"),
            (self.utility, self.power_account, D(self.rng.randint(low, high)), "Electricity"),
        ):
            draft = purchasing.save_bill(
                self.owner,
                {
                    "supplier": supplier,
                    "supplier_reference": f"{what[:4].upper()}-{day:%y%m}",
                    "date": day,
                    "due_date": day,
                },
                [purchasing.BillLineInput(D(1), amount, account=account, description=what)],
            )
            bill = purchasing.post_bill(self.owner, draft)
            self.pay(supplier, day, [(bill, bill.total)])

    def deposit(self, day: date) -> None:
        """Each Monday, the week's cash above the float goes to the bank."""
        held = accounting_balance(self.cash, day)
        amount = money(held - CASH_FLOAT[self.plan.kind])
        if amount <= 0:
            return
        entry = accounting.save_draft(
            self.owner,
            day,
            "Cash deposited at the bank",
            [
                accounting.LineInput(self.bank, amount, ZERO),
                accounting.LineInput(self.cash, ZERO, amount),
            ],
        )
        accounting.post_entry(self.owner, entry)

    # Staff and payroll

    def staff(self) -> None:
        plan = self.plan
        time_off.save_settings(
            self.owner,
            {
                "weekend": plan.weekend,
                "holiday_country": plan.country,
                "default_province": plan.province,
                "wps_employer_id": plan.wps_employer_id,
                "wps_bank_code": plan.wps_bank_code,
            },
        )
        for year in range(self.start.year, self.today.year + 1):
            time_off.fill_holidays(self.owner, year)
        departments = {
            name: inventory.save_master(
                self.owner, Department(), {"code": name[:5].upper(), "name": name}
            )
            for name in dict.fromkeys(person.department for person in plan.people)
        }
        annual = inventory.save_master(
            self.owner, LeaveType(), {"name": "Annual leave", "paid": True, "days_per_year": 14}
        )
        inventory.save_master(
            self.owner, LeaveType(), {"name": "Sick leave", "paid": True, "days_per_year": 8}
        )
        self.people: list[Employee] = []
        for number, person in enumerate(plan.people, start=1):
            worker = hr.save_employee(self.owner, Employee(), self.employee_values(person, number))
            worker.department = departments[person.department]
            worker.save(update_fields=["department"])
            parts = []
            if person.housing:
                parts.append(
                    hr.ComponentInput("Housing", "earning", person.housing, None, True, True)
                )
            name = f"{person.title} pay ({person.code})"
            structure = hr.save_structure(self.owner, {"name": name}, parts)
            hr.save_contract(
                self.owner,
                {
                    "employee": worker,
                    "structure": structure,
                    "kind": "permanent",
                    "starts_on": person.joined,
                    "ends_on": None,
                    "basic_salary": person.basic,
                },
            )
            self.people.append(worker)
        self.time_away(annual)

    def employee_values(self, person: data.Person, number: int) -> dict[str, Any]:
        values: dict[str, Any] = {
            "code": person.code,
            "full_name": person.name,
            "job_title": person.title,
            "joined_on": person.joined,
            "nationality": person.nationality or self.plan.country,
            "bank_account": f"DEMO-{self.plan.kind.upper()}-{number:06d}",
        }
        if self.plan.kind == "pk":
            values.update(
                province=self.plan.province,
                pays_eobi=True,
                national_id=f"00000-{number:07d}-0",
            )
        else:
            values.update(
                national_id=f"784-0000-{number:07d}-0",
                wps_person_id=f"{number:014d}",
                wps_agent_code=data.WPS_AGENT,
            )
        return values

    def time_away(self, annual: LeaveType) -> None:
        """A week of approved leave for most people, and a few days away."""
        for index, worker in enumerate(self.people):
            when = self.start + timedelta(days=60 + index * 41)
            if when.year != (when + timedelta(days=6)).year or when >= self.today:
                continue
            request = time_off.ask_leave(
                self.owner,
                {
                    "employee": worker,
                    "leave_type": annual,
                    "starts_on": when,
                    "ends_on": when + timedelta(days=6),
                    "note": "Family visit",
                },
            )
            time_off.decide_leave(self.owner, request, approve=True)
            away = self.start + timedelta(days=30 + index * 53)
            if away < self.today and away.weekday() not in self.plan.weekend:
                Attendance.objects.create(
                    employee=worker, on=away, status="absent", note="Did not come in"
                )

    def payroll(self) -> None:
        if self.plan.kind == "pk":
            payroll.fill_official(self.owner)
            contributions.fill_official(self.owner)
        else:
            TaxTable.objects.all().delete()
            gratuity.fill_official(self.owner)
        for scheme, employer, employee, options in self.plan.rates:
            contributions.save(
                self.owner,
                ContributionRate(),
                {
                    "scheme": scheme,
                    "province": "",
                    "starts_on": date(2020, 1, 1),
                    "employer_percent": employer,
                    "employee_percent": employee,
                    "source": self.plan.rates_source,
                    **options,
                },
            )
        month = next_month(self.start)
        while next_month(month) <= self.today:
            if self.plan.kind == "pk" and payroll.table_for("PK", month) is None:
                # Only tax years with official slabs can be paid; see the payroll docs.
                month = next_month(month)
                continue
            run = runs.work_out(self.owner, month)
            if not runs.post(self.owner, run):
                runs.post(self.owner, PayrollRun.objects.get(pk=run.pk))
            paid_on = min(next_month(month) + timedelta(days=2), self.today)
            payments.pay(
                self.owner,
                PayrollRun.objects.get(pk=run.pk),
                {"paid_on": paid_on, "paid_from": self.bank, "reference": f"SAL-{month:%Y%m}"},
            )
            self.count("payroll months")
            month = next_month(month)


def accounting_balance(account: Account, on: date) -> Decimal:
    totals = JournalLine.objects.filter(
        account=account, entry__status="posted", entry__date__lte=on
    ).aggregate(debit=Sum("debit"), credit=Sum("credit"))
    return (totals["debit"] or ZERO) - (totals["credit"] or ZERO)


def seed(
    owner: User, kind: str, today: date, days: int = 365, plan: Plan | None = None
) -> tuple[Tenant, dict[str, int]]:
    seeder = Seeder(owner, plan or data.PLANS[kind], today, days)
    tenant = seeder.run()
    return tenant, seeder.counts
