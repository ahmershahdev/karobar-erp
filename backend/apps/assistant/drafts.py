"""Drafts the chat can prepare. The model only names things; this module finds them in the
business, and nothing is saved until the person presses Confirm on the card. Confirm runs the
same serializer and save as the document's own screen, with the person's own permissions, and
only ever makes a draft: nothing here posts, pays or deletes."""

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db.models import Q, QuerySet
from django.utils import timezone
from rest_framework.request import Request

from apps.core.documents import line_amount
from apps.core.money import MoneyError, quantize_money, quantize_quantity
from apps.inventory.models import Product, ProductUnit, Unit, Warehouse
from apps.purchasing import views as purchasing
from apps.purchasing.models import PurchaseOrderLine, Supplier
from apps.sales import views as sales
from apps.sales.models import Customer
from apps.tenancy.models import Membership

from . import lookups

MAX_ITEMS = 30
MAX_NAME = 150
MAX_NOTE = 255
MAX_QUANTITY = Decimal(1_000_000_000)
OPTIONS_SHOWN = 5


@dataclass(frozen=True)
class DraftKind:
    module: str
    party: str
    document: Any
    tool: str
    description: str
    sale_price: bool


KINDS = {
    "sales_invoice": DraftKind(
        "sales",
        "customer",
        sales.INVOICE,
        "draft_sales_invoice",
        "Prepare a draft sales invoice (a bill to a customer). It is only saved after the person "
        "presses Confirm, and it stays a draft until they post it themselves.",
        True,
    ),
    "quotation": DraftKind(
        "sales",
        "customer",
        sales.ORDER,
        "draft_quotation",
        "Prepare a draft quotation or sales order for a customer. It is only saved after the "
        "person presses Confirm.",
        True,
    ),
    "purchase_order": DraftKind(
        "purchasing",
        "supplier",
        purchasing.ORDER,
        "draft_purchase_order",
        "Prepare a draft purchase order to a supplier. It is only saved after the person presses "
        "Confirm, and it is never sent or confirmed by you.",
        False,
    ),
}
BY_TOOL = {kind.tool: key for key, kind in KINDS.items()}


class DraftProblemError(Exception):
    """The draft can't be made as asked. The code and details are shown to the person in their
    own language, so no second request to the model is needed to explain it."""

    def __init__(
        self, code: str, field: str = "", name: str = "", options: list[str] | None = None
    ) -> None:
        super().__init__(code)
        self.data = {"code": code, "field": field, "name": name, "options": options or []}


class NotAllowedError(Exception):
    pass


def allowed(membership: Membership, module: str) -> bool:
    """The same test the document screens make before creating one."""
    return lookups.can(membership, module, "create")


def tools(membership: Membership) -> list[dict[str, Any]]:
    """Only the drafts this person could make on the screen themselves."""
    return [_tool(kind) for kind in KINDS.values() if allowed(membership, kind.module)]


def _tool(kind: DraftKind) -> dict[str, Any]:
    text = {"type": "string", "maxLength": MAX_NAME}
    item = {
        "type": "object",
        "properties": {
            "product": {**text, "description": "Product name or code, as the person said it."},
            "quantity": {"type": "number", "exclusiveMinimum": 0},
            "unit": {
                **text,
                "description": "The pack or unit, such as carton, only if the person said one.",
            },
            "price": {
                "type": "number",
                "minimum": 0,
                "description": "Price per unit or pack, only if the person gave one.",
            },
        },
        "required": ["product", "quantity"],
    }
    return {
        "type": "function",
        "function": {
            "name": kind.tool,
            "description": kind.description,
            "parameters": {
                "type": "object",
                "properties": {
                    kind.party: {**text, "description": f"The {kind.party}'s name or code."},
                    "items": {"type": "array", "items": item, "minItems": 1},
                    "warehouse": {**text, "description": "Only if the person named one."},
                    "note": {"type": "string", "maxLength": MAX_NOTE},
                },
                "required": [kind.party, "items"],
            },
        },
    }


def _text(value: Any, limit: int = MAX_NAME) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DraftProblemError("unclear")
    return value.strip()[:limit]


def _number(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise DraftProblemError("unclear")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise DraftProblemError("unclear") from exc
    if not number.is_finite():
        raise DraftProblemError("unclear")
    return number


def _find[M: Any](rows: QuerySet[M], field: str, name: str, *codes: str) -> M:
    """One row by its exact name or code, or else the only one whose name contains the words."""
    exact = Q(name__iexact=name)
    for code in codes:
        exact |= Q(**{f"{code}__iexact": name})
    found = list(rows.filter(exact)[:2]) or list(
        rows.filter(name__icontains=name)[: OPTIONS_SHOWN + 1]
    )
    if len(found) == 1:
        return found[0]
    if not found:
        raise DraftProblemError("not_found", field, name)
    raise DraftProblemError("ambiguous", field, name, [row.name for row in found[:OPTIONS_SHOWN]])


def _unit(product: Product, said: Any) -> tuple[Unit, Decimal]:
    """The unit the person named and its size in base units. Only the product's own base unit
    and packs count, so a line can't be priced in a unit the product isn't sold in."""
    if said is None:
        return product.unit, Decimal(1)
    name = _text(said)
    # "cartons" for a unit called "Carton".
    names = {name.lower(), name.lower().removesuffix("s")}
    base = product.unit
    if base.code.lower() in names or base.name.lower() in names:
        return base, Decimal(1)
    for pack in ProductUnit.objects.filter(product=product).select_related("unit"):
        if pack.unit.code.lower() in names or pack.unit.name.lower() in names:
            return pack.unit, pack.factor
    raise DraftProblemError("not_found", "unit", name)


def _last_cost(product: Product, unit: Unit) -> Decimal | None:
    return (
        PurchaseOrderLine.objects.filter(product=product, unit=unit)
        .order_by("-id")
        .values_list("unit_price", flat=True)
        .first()
    )


def build(tool: str, arguments: str) -> dict[str, Any]:
    """Turn what the model asked for into a card. Every name is looked up in this business only,
    through the tenant-scoped managers, so a draft can't point at another business's rows."""
    key = BY_TOOL.get(tool)
    try:
        args = json.loads(arguments, parse_float=Decimal)
    except (TypeError, ValueError) as exc:
        raise DraftProblemError("unclear") from exc
    if key is None or not isinstance(args, dict):
        raise DraftProblemError("unclear")
    kind = KINDS[key]
    parties: QuerySet[Any] = (
        Customer.objects.filter(is_active=True)
        if kind.party == "customer"
        else Supplier.objects.filter(is_active=True)
    )
    party = _find(parties, kind.party, _text(args.get(kind.party)), "code")
    warehouses = Warehouse.objects.filter(is_active=True).order_by("id")
    if args.get("warehouse"):
        warehouse = _find(warehouses, "warehouse", _text(args["warehouse"]), "code")
    else:
        warehouse = warehouses.first()
        if warehouse is None:
            raise DraftProblemError("no_warehouse")
    items = args.get("items")
    if not isinstance(items, list) or not items:
        raise DraftProblemError("unclear")
    if len(items) > MAX_ITEMS:
        raise DraftProblemError("too_many")
    lines = [_line(kind, item) for item in items]
    total = sum(
        (
            line_amount(Decimal(line["quantity"]), Decimal(line["unit_price"] or 0))
            for line in lines
        ),
        Decimal(0),
    )
    note = args.get("note")
    return {
        "kind": key,
        "party": {"id": party.pk, "name": party.name},
        "warehouse": {"id": warehouse.pk, "name": warehouse.name},
        "lines": lines,
        "memo": _text(note, MAX_NOTE) if isinstance(note, str) and note.strip() else "",
        "total": f"{quantize_money(total):f}",
    }


def _line(kind: DraftKind, item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise DraftProblemError("unclear")
    product = _find(
        Product.objects.filter(is_active=True).select_related("unit"),
        "product",
        _text(item.get("product")),
        "sku",
    )
    unit, factor = _unit(product, item.get("unit"))
    try:
        quantity = quantize_quantity(_number(item.get("quantity")))
    except MoneyError as exc:
        # Too large to round at all, such as 1e999999.
        raise DraftProblemError("unclear") from exc
    if not Decimal(0) < quantity <= MAX_QUANTITY:
        raise DraftProblemError("unclear")
    given = item.get("price")
    if given is not None:
        price: Decimal | None = _number(given)
    elif kind.sale_price:
        # The sale price is per base unit, so a carton of twelve costs twelve of them.
        price = None if product.sale_price is None else product.sale_price * factor
    else:
        price = _last_cost(product, unit)
    if price is not None and not Decimal(0) <= price <= MAX_QUANTITY:
        raise DraftProblemError("unclear")
    return {
        "product": product.pk,
        "name": product.name,
        "sku": product.sku,
        "unit": unit.pk,
        "unit_code": unit.code,
        "quantity": f"{quantity.normalize():f}",
        # No price means the card says so, and the draft opens with zero to fill in.
        "unit_price": None if price is None else f"{quantize_money(price):f}",
    }


def save(request: Request, membership: Membership, draft: dict[str, Any]) -> Any:
    """Save the card as a draft document, the way its own screen would."""
    kind = KINDS[draft["kind"]]
    if not allowed(membership, kind.module):
        raise NotAllowedError
    body = {
        kind.party: draft["party"]["id"],
        "warehouse": draft["warehouse"]["id"],
        "date": str(timezone.localdate()),
        "memo": draft["memo"],
        "lines": [
            {
                "product": line["product"],
                "unit": line["unit"],
                "quantity": line["quantity"],
                "unit_price": line["unit_price"] or "0",
            }
            for line in draft["lines"]
        ],
    }
    serializer = kind.document.serializer(data=body, context={"request": request})
    serializer.is_valid(raise_exception=True)
    view = sales if kind.module == "sales" else purchasing
    return view._save(kind.document, request, serializer.validated_data)
