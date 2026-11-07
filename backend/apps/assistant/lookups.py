"""Read-only lookups the chat can make while answering. Each one is offered only when the
person's role may view that part of the business, reads through the tenant-scoped managers, and
returns only what is needed to answer: no phone numbers, emails or addresses go to the model."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.db.models import Q, QuerySet

from apps.inventory.models import Product, StockLevel
from apps.purchasing.models import Bill
from apps.purchasing.views import suppliers
from apps.sales.models import Invoice
from apps.sales.services import customers
from apps.tenancy.models import Membership

MATCHES = 5
RECENT = 5
MAX_NAME = 150


def can(membership: Membership, module: str, action: str = "view") -> bool:
    """The same test the screens make."""
    if membership.is_owner:
        return True
    role = membership.role
    return role is not None and action in role.permissions.get(module, [])


def _number(value: Decimal | None) -> str | None:
    return None if value is None else f"{value.normalize():f}"


def _matching[M: Any](rows: QuerySet[M], name: str, code: str) -> list[M]:
    exact = list(rows.filter(Q(name__iexact=name) | Q(**{f"{code}__iexact": name}))[:MATCHES])
    if exact:
        return exact
    return list(rows.filter(Q(name__icontains=name) | Q(**{f"{code}__icontains": name}))[:MATCHES])


def _products(membership: Membership, name: str) -> list[dict[str, Any]]:
    stock = can(membership, "inventory")
    found = []
    rows = (
        Product.objects.filter(is_active=True)
        .select_related("unit")
        .prefetch_related("packs__unit")
    )
    for product in _matching(rows, name, "sku"):
        row: dict[str, Any] = {
            "name": product.name,
            "sku": product.sku,
            "unit": product.unit.code,
            "sale_price_per_unit": _number(product.sale_price),
            "packs": [
                {"unit": pack.unit.code, "units_in_pack": _number(pack.factor)}
                for pack in product.packs.all()
            ],
        }
        if stock:
            levels = StockLevel.objects.filter(product=product).select_related("warehouse")
            row["on_hand_by_warehouse"] = {
                level.warehouse.name: _number(level.quantity) for level in levels
            }
            row["on_hand_total"] = _number(sum((level.quantity for level in levels), Decimal(0)))
            row["reorder_level"] = _number(product.reorder_level)
        found.append(row)
    return found


def _customers(membership: Membership, name: str) -> list[dict[str, Any]]:
    found = []
    for customer in _matching(customers().filter(is_active=True), name, "code"):
        invoices = Invoice.objects.filter(customer=customer).order_by("-date", "-id")[:RECENT]
        found.append(
            {
                "name": customer.name,
                "code": customer.code,
                "owes_us": _number(customer.balance),  # type: ignore[attr-defined]
                "credit_limit": _number(customer.credit_limit),
                "payment_terms_days": customer.payment_terms_days,
                "recent_invoices": [
                    {
                        "number": invoice.number,
                        "date": str(invoice.date),
                        "status": invoice.status,
                        "total": _number(invoice.total),
                        "still_open": _number(
                            invoice.total - invoice.amount_paid - invoice.amount_credited
                        ),
                        "due_date": str(invoice.due_date) if invoice.due_date else None,
                    }
                    for invoice in invoices
                ],
            }
        )
    return found


def _suppliers(membership: Membership, name: str) -> list[dict[str, Any]]:
    found = []
    for supplier in _matching(suppliers().filter(is_active=True), name, "code"):
        bills = Bill.objects.filter(supplier=supplier).order_by("-date", "-id")[:RECENT]
        found.append(
            {
                "name": supplier.name,
                "code": supplier.code,
                "we_owe_them": _number(supplier.balance),  # type: ignore[attr-defined]
                "recent_bills": [
                    {
                        "number": bill.number,
                        "supplier_reference": bill.supplier_reference,
                        "date": str(bill.date),
                        "status": bill.status,
                        "total": _number(bill.total),
                        "still_open": _number(bill.total - bill.amount_paid),
                        "due_date": str(bill.due_date) if bill.due_date else None,
                    }
                    for bill in bills
                ],
            }
        )
    return found


@dataclass(frozen=True)
class Lookup:
    description: str
    find: Callable[[Membership, str], list[dict[str, Any]]]
    modules: tuple[str, ...]

    def allowed(self, membership: Membership) -> bool:
        return any(can(membership, module) for module in self.modules)


LOOKUPS = {
    "look_up_product": Lookup(
        "Find products by name or code: price per unit, packs, and stock on hand if the person "
        "may see stock.",
        _products,
        ("inventory", "sales"),
    ),
    "look_up_customer": Lookup(
        "Find a customer by name or code: what they owe, credit limit and their recent invoices.",
        _customers,
        ("sales",),
    ),
    "look_up_supplier": Lookup(
        "Find a supplier by name or code: what we owe them and their recent bills.",
        _suppliers,
        ("purchasing",),
    ),
}


def tools(membership: Membership) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": lookup.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "maxLength": MAX_NAME,
                            "description": "The name or code, as the person said it.",
                        }
                    },
                    "required": ["name"],
                },
            },
        }
        for name, lookup in LOOKUPS.items()
        if lookup.allowed(membership)
    ]


def run(membership: Membership, tool: str, arguments: str) -> str:
    """The answer to one lookup, as JSON for the model. A lookup the person may not make, or
    one with strange arguments, says so instead of failing the whole answer."""
    lookup = LOOKUPS.get(tool)
    if lookup is None or not lookup.allowed(membership):
        return json.dumps({"error": "not allowed for this person"})
    try:
        args = json.loads(arguments)
    except (TypeError, ValueError):
        args = None
    name = args.get("name") if isinstance(args, dict) else None
    if not isinstance(name, str) or not name.strip():
        return json.dumps({"error": "give a name or code to look up"})
    found = lookup.find(membership, name.strip()[:MAX_NAME])
    return json.dumps({"found": found}, ensure_ascii=False)
