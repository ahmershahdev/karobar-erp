"""Every change to stock goes through here.

A posted stock entry locks the stock levels it touches (in primary-key order, via lock_rows),
writes its stock moves, updates levels, batches and FIFO layers, and posts the cost to the books,
all in one transaction. FIFO layers and batch levels are only read or written while their
product-warehouse StockLevel row is locked, so that one lock protects all of them.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db import IntegrityError, models, transaction
from django.db.models import F, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.accounting import services as accounting
from apps.accounting.models import Account
from apps.accounts.models import User
from apps.core import posting
from apps.core.journal import Line
from apps.core.money import quantize_money, quantize_quantity
from apps.core.valuation import (
    Holding,
    InsufficientStockError,
    Layer,
    average_issue,
    average_receive,
    fifo_issue,
    to_base,
)
from apps.platform.locking import lock_rows, retry_on_deadlock
from apps.tenancy import audit
from apps.tenancy.context import get_current_tenant
from apps.tenancy.models import AuditEvent

from .models import (
    Batch,
    BatchLevel,
    CostLayer,
    Product,
    ProductUnit,
    StockEntry,
    StockEntryLine,
    StockLevel,
    StockMove,
    Unit,
    Warehouse,
)

ZERO = Decimal(0)
Action = AuditEvent.Action
Kind = StockEntry.Kind
SERIES = {
    Kind.RECEIPT: ("GRN", "GRN-"),
    Kind.ISSUE: ("GIN", "GIN-"),
    Kind.TRANSFER: ("TRF", "TRF-"),
    Kind.ADJUSTMENT: ("ADJ", "ADJ-"),
}


class InventoryError(Exception):
    """A stock rule was broken. Subclasses carry a fixed message the API can show."""

    message = "That isn't allowed for stock."


class NotEnoughStockError(InventoryError):
    message = "There isn't enough stock for this."


class NoLinesError(InventoryError):
    message = "Add at least one line."


class BadTransferError(InventoryError):
    message = "A transfer needs a different destination warehouse."


class UnknownPackError(InventoryError):
    message = "This product isn't set up in that unit."


class BatchRequiredError(InventoryError):
    message = "This product is tracked by batch; enter the batch number."


class CostRequiredError(InventoryError):
    message = "Receipts need a unit cost for every line."


class AlreadyPostedError(InventoryError):
    message = "This stock entry is already posted."


class DuplicateError(InventoryError):
    message = "Something with this code, SKU or barcode already exists."


class InUseError(InventoryError):
    message = "This is in use, so it can't be deleted."


@dataclass(frozen=True)
class PackInput:
    unit: Unit
    factor: Decimal
    barcode: str | None


@dataclass(frozen=True)
class LineInput:
    product: Product
    unit: Unit
    quantity: Decimal
    unit_cost: Decimal | None = None
    batch_number: str = ""
    expiry_date: date | None = None


# Master data


def _save(
    actor: User, instance: models.Model, values: dict[str, Any], fields: tuple[str, ...]
) -> Any:
    creating = instance.pk is None
    before = {f: getattr(instance, f, None) for f in fields}
    for key, value in values.items():
        setattr(instance, key, value)
    try:
        with transaction.atomic():
            instance.save()
    except IntegrityError as exc:
        raise DuplicateError from exc
    after = {f: getattr(instance, f, None) for f in fields}
    changes = {
        k: [None if creating else before[k], after[k]]
        for k in fields
        if creating or before[k] != after[k]
    }
    audit.record(Action.CREATE if creating else Action.UPDATE, instance, actor, changes)
    return instance


@transaction.atomic
def save_master(actor: User, instance: models.Model, values: dict[str, Any]) -> Any:
    fields = tuple(
        f.attname for f in instance._meta.concrete_fields if f.attname not in ("id", "tenant_id")
    )
    return _save(actor, instance, values, fields)


@transaction.atomic
def delete_master(actor: User, instance: models.Model) -> None:
    audit.record(Action.DELETE, instance, actor, {"str": [str(instance), None]})
    try:
        with transaction.atomic():
            instance.delete()
    except models.ProtectedError as exc:
        raise InUseError from exc


@transaction.atomic
def save_product(
    actor: User,
    values: dict[str, Any],
    packs: list[PackInput] | None,
    product: Product | None = None,
) -> Product:
    target = product or Product()
    fields = (
        "sku",
        "name",
        "category_id",
        "unit_id",
        "variant_of_id",
        "track_batches",
        "reorder_level",
        "sale_price",
        "is_active",
    )
    saved: Product = _save(actor, target, values, fields)
    if packs is not None:
        saved.packs.all().delete()
        try:
            with transaction.atomic():
                for pack in packs:
                    ProductUnit.objects.create(
                        product=saved,
                        unit=pack.unit,
                        factor=quantize_quantity(pack.factor),
                        barcode=pack.barcode or None,
                    )
        except IntegrityError as exc:
            raise DuplicateError from exc
    return saved


def factor_for(product: Product, unit: Unit) -> Decimal:
    if unit.pk == product.unit_id:
        return Decimal(1)
    pack: ProductUnit | None = ProductUnit.objects.filter(product=product, unit=unit).first()
    if pack is None:
        raise UnknownPackError
    factor: Decimal = pack.factor
    return factor


def find_by_barcode(code: str) -> tuple[Product, Decimal] | None:
    pack = ProductUnit.objects.select_related("product").filter(barcode=code).first()
    return (pack.product, pack.factor) if pack else None


# Drafts


def _locked_draft(entry: StockEntry) -> StockEntry:
    locked: StockEntry = lock_rows(StockEntry.objects.filter(pk=entry.pk))[0]
    if locked.status == StockEntry.Status.POSTED:
        raise AlreadyPostedError
    return locked


@transaction.atomic
def save_draft(
    actor: User,
    header: dict[str, Any],
    lines: list[LineInput],
    entry: StockEntry | None = None,
) -> StockEntry:
    target = _locked_draft(entry) if entry is not None else StockEntry(created_by=actor)
    for key in ("kind", "date", "memo", "warehouse", "to_warehouse", "contra_account"):
        if key in header:
            setattr(target, key, header[key])
    target.save()
    target.lines.all().delete()
    StockEntryLine.objects.bulk_create(
        StockEntryLine(
            tenant=target.tenant,
            entry=target,
            product=line.product,
            unit=line.unit,
            quantity=quantize_quantity(line.quantity),
            unit_cost=None if line.unit_cost is None else quantize_quantity(line.unit_cost),
            batch_number=line.batch_number.strip(),
            expiry_date=line.expiry_date,
        )
        for line in lines
    )
    audit.record(
        Action.UPDATE if entry else Action.CREATE,
        target,
        actor,
        {"kind": [None, target.kind], "lines": [None, len(lines)]},
    )
    return target


@transaction.atomic
def delete_draft(actor: User, entry: StockEntry) -> None:
    draft = _locked_draft(entry)
    audit.record(Action.DELETE, draft, actor, {"kind": [draft.kind, None]})
    draft.delete()


# Posting


def _lock_levels(pairs: set[tuple[int, int]]) -> dict[tuple[int, int], StockLevel]:
    tenant = get_current_tenant()
    match = Q()
    for product_id, warehouse_id in pairs:
        match |= Q(product_id=product_id, warehouse_id=warehouse_id)
    # Insert only rows that don't exist yet. INSERT IGNORE on an existing row takes a shared
    # lock, and two posts each holding one while waiting for FOR UPDATE deadlock each other.
    existing = set(StockLevel.objects.filter(match).values_list("product_id", "warehouse_id"))
    missing = sorted(pairs - existing)
    if missing:
        StockLevel.objects.bulk_create(
            [StockLevel(tenant=tenant, product_id=p, warehouse_id=w) for p, w in missing],
            ignore_conflicts=True,
        )
    return {
        (level.product_id, level.warehouse_id): level
        for level in lock_rows(StockLevel.objects.filter(match))
    }


def _batch(line: StockEntryLine, create: bool) -> Batch | None:
    if not line.product.track_batches:
        return None
    if not line.batch_number:
        raise BatchRequiredError
    found: Batch | None = Batch.objects.filter(
        product=line.product, number=line.batch_number
    ).first()
    if found is None:
        if not create:
            raise NotEnoughStockError
        try:
            with transaction.atomic():
                found = Batch.objects.create(
                    product=line.product, number=line.batch_number, expiry_date=line.expiry_date
                )
        except IntegrityError:
            found = Batch.objects.get(product=line.product, number=line.batch_number)
    return found


def _move_batch(batch: Batch | None, warehouse: Warehouse, quantity: Decimal) -> None:
    if batch is None:
        return
    level, _ = BatchLevel.objects.get_or_create(
        product=batch.product, warehouse=warehouse, batch=batch
    )
    new = quantize_quantity(level.quantity + quantity)
    if new < 0:
        raise NotEnoughStockError
    level.quantity = new
    level.save(update_fields=["quantity"])


def _receive(level: StockLevel, quantity: Decimal, unit_cost: Decimal, fifo: bool) -> Decimal:
    before = level.value
    holding = average_receive(Holding(level.quantity, level.value), quantity, unit_cost)
    level.quantity, level.value = holding.quantity, holding.value
    if fifo:
        CostLayer.objects.create(
            product_id=level.product_id,
            warehouse_id=level.warehouse_id,
            quantity_left=quantity,
            unit_cost=unit_cost,
        )
    return quantize_money(level.value - before)


def _issue(
    level: StockLevel, quantity: Decimal, fifo: bool
) -> tuple[Decimal, list[tuple[Decimal, Decimal]]]:
    """Take stock out; returns the cost and, for FIFO, the (quantity, unit cost) pieces taken."""
    try:
        if not fifo:
            holding, cost = average_issue(Holding(level.quantity, level.value), quantity)
            level.quantity, level.value = holding.quantity, holding.value
            unit = cost / quantity if quantity else ZERO
            return cost, [(quantity, unit)]
        layers = list(
            CostLayer.objects.filter(
                product_id=level.product_id, warehouse_id=level.warehouse_id, quantity_left__gt=0
            ).order_by("id")
        )
        taken, _ = fifo_issue(
            [Layer(layer.pk, layer.quantity_left, layer.unit_cost) for layer in layers], quantity
        )
    except InsufficientStockError as exc:
        raise NotEnoughStockError from exc
    by_id = {layer.pk: layer for layer in layers}
    pieces: list[tuple[Decimal, Decimal]] = []
    for part in taken:
        layer = by_id[part.key]
        layer.quantity_left = quantize_quantity(layer.quantity_left - part.quantity)
        layer.save(update_fields=["quantity_left"])
        pieces.append((part.quantity, layer.unit_cost))
    level.quantity = quantize_quantity(level.quantity - quantity)
    # Rounding each issue's cost to paisa would drift: a 0.1060 unit cost issued one unit at a
    # time costs 0.11 every time and walks the value below zero. Instead the level is revalued
    # from the layers that remain, and the cost is exactly the drop in value. Books and stock
    # stay equal, and the value never goes negative or up on an issue. Each layer is rounded on
    # its own, as its receipt was, so many small receipts don't lose their rounding all at once.
    remaining = sum(
        (quantize_money(layer.quantity_left * layer.unit_cost) for layer in layers), ZERO
    )
    before = quantize_money(level.value)
    level.value = ZERO if level.quantity == 0 else min(before, max(remaining, ZERO))
    return quantize_money(before - level.value), pieces


def _receive_pieces(
    level: StockLevel, pieces: list[tuple[Decimal, Decimal]], cost: Decimal, fifo: bool
) -> None:
    # A transfer moves cost, it doesn't create it: the destination gets exactly what left the
    # source, layer by layer under FIFO.
    level.quantity = quantize_quantity(level.quantity + sum((q for q, _ in pieces), ZERO))
    level.value = quantize_money(level.value + cost)
    if fifo:
        for quantity, unit_cost in pieces:
            CostLayer.objects.create(
                product_id=level.product_id,
                warehouse_id=level.warehouse_id,
                quantity_left=quantity,
                unit_cost=unit_cost,
            )


def _record(
    entry: StockEntry,
    line: StockEntryLine,
    warehouse: Warehouse,
    batch: Batch | None,
    quantity: Decimal,
    value: Decimal,
) -> None:
    StockMove.objects.create(
        entry=entry,
        product=line.product,
        warehouse=warehouse,
        batch=batch,
        date=entry.date,
        quantity=quantity,
        value=value,
        source_type="stock_entry",
        source_id=str(entry.pk),
    )


@dataclass
class _Posting:
    entry: StockEntry
    levels: dict[tuple[int, int], StockLevel]
    fifo: bool
    stock_in: Decimal = ZERO
    stock_out: Decimal = ZERO

    def level(self, line: StockEntryLine, warehouse_id: int) -> StockLevel:
        return self.levels[(line.product_id, warehouse_id)]


def _post_receipt(run: _Posting, line: StockEntryLine, quantity: Decimal, factor: Decimal) -> None:
    if line.unit_cost is None:
        raise CostRequiredError
    batch = _batch(line, create=True)
    value = _receive(
        run.level(line, run.entry.warehouse_id), quantity, line.unit_cost / factor, run.fifo
    )
    _move_batch(batch, run.entry.warehouse, quantity)
    _record(run.entry, line, run.entry.warehouse, batch, quantity, value)
    run.stock_in += value


def _post_issue(run: _Posting, line: StockEntryLine, quantity: Decimal, factor: Decimal) -> None:
    batch = _batch(line, create=False)
    cost, _ = _issue(run.level(line, run.entry.warehouse_id), quantity, run.fifo)
    _move_batch(batch, run.entry.warehouse, -quantity)
    _record(run.entry, line, run.entry.warehouse, batch, -quantity, -cost)
    run.stock_out += cost


def _post_transfer(
    run: _Posting, line: StockEntryLine, quantity: Decimal, factor: Decimal
) -> None:
    source, destination = run.entry.warehouse, run.entry.to_warehouse
    if destination is None:
        raise BadTransferError
    batch = _batch(line, create=False)
    cost, pieces = _issue(run.level(line, source.pk), quantity, run.fifo)
    _receive_pieces(run.level(line, destination.pk), pieces, cost, run.fifo)
    _move_batch(batch, source, -quantity)
    _move_batch(batch, destination, quantity)
    _record(run.entry, line, source, batch, -quantity, -cost)
    _record(run.entry, line, destination, batch, quantity, cost)


def _post_adjustment(
    run: _Posting, line: StockEntryLine, counted: Decimal, factor: Decimal
) -> None:
    warehouse = run.entry.warehouse
    level = run.level(line, warehouse.pk)
    batch = _batch(line, create=True)
    on_hand = level.quantity
    if batch is not None:
        held = BatchLevel.objects.filter(warehouse=warehouse, batch=batch).values_list(
            "quantity", flat=True
        )
        on_hand = held.first() or ZERO
    difference = quantize_quantity(counted - on_hand)
    if difference > 0:
        # Stock found in a count comes in at the cost given, or else at today's average.
        if line.unit_cost is not None:
            unit_cost = line.unit_cost / factor
        else:
            unit_cost = level.value / level.quantity if level.quantity else ZERO
        value = _receive(level, difference, unit_cost, run.fifo)
        _move_batch(batch, warehouse, difference)
        _record(run.entry, line, warehouse, batch, difference, value)
        run.stock_in += value
    elif difference < 0:
        cost, _ = _issue(level, -difference, run.fifo)
        _move_batch(batch, warehouse, difference)
        _record(run.entry, line, warehouse, batch, difference, -cost)
        run.stock_out += cost


HANDLERS = {
    Kind.RECEIPT: _post_receipt,
    Kind.ISSUE: _post_issue,
    Kind.TRANSFER: _post_transfer,
    Kind.ADJUSTMENT: _post_adjustment,
}


def post_entry(actor: User, entry: StockEntry) -> StockEntry:
    """Post a stock entry, starting over if InnoDB chooses it as a deadlock victim."""
    posted: StockEntry = retry_on_deadlock(_post_entry)(actor, entry)
    return posted


@transaction.atomic
def _post_entry(actor: User, entry: StockEntry) -> StockEntry:
    locked = _locked_draft(entry)
    lines = list(locked.lines.select_related("product", "unit"))
    if not lines:
        raise NoLinesError
    kind = StockEntry.Kind(locked.kind)
    warehouse_ids = [locked.warehouse_id]
    if kind == Kind.TRANSFER:
        if locked.to_warehouse_id is None or locked.to_warehouse_id == locked.warehouse_id:
            raise BadTransferError
        warehouse_ids.append(locked.to_warehouse_id)
    run = _Posting(
        entry=locked,
        levels=_lock_levels({(line.product_id, w) for line in lines for w in warehouse_ids}),
        fifo=get_current_tenant().valuation_method == "fifo",
    )
    for line in lines:
        factor = factor_for(line.product, line.unit)
        HANDLERS[kind](run, line, to_base(line.quantity, factor), factor)
    for level in run.levels.values():
        level.save(update_fields=["quantity", "value"])

    locked.number = accounting.next_number(*SERIES[kind])
    rule_lines: list[Line] = []
    if run.stock_in:
        rule_lines += posting.stock_in(run.stock_in, "contra")
    if run.stock_out:
        rule_lines += posting.stock_out(run.stock_out, "contra")
    if rule_lines:
        contra = locked.contra_account or accounting.account_for_role("inventory_adjustments")
        locked.journal_entry = accounting.post_rule_lines(
            actor,
            locked.date,
            locked.memo or f"{locked.get_kind_display()} {locked.number}",
            _net(rule_lines),
            {"contra": contra},
            ("stock_entry", str(locked.pk)),
        )
    locked.status = StockEntry.Status.POSTED
    locked.posted_by = actor
    locked.posted_at = timezone.now()
    locked.save(update_fields=["number", "status", "posted_by", "posted_at", "journal_entry"])
    audit.record(Action.POST, locked, actor, {"number": [None, locked.number]})
    return locked


def _net(lines: list[Line]) -> list[Line]:
    """An adjustment that both found and lost stock nets to one debit and one credit."""
    totals: dict[str, Decimal] = {}
    for line in lines:
        totals[line.account] = totals.get(line.account, ZERO) + line.debit - line.credit
    return [
        Line(account, amount if amount > 0 else ZERO, -amount if amount < 0 else ZERO)
        for account, amount in totals.items()
        if amount
    ]


# Alerts


@dataclass(frozen=True)
class LowStock:
    product: Product
    on_hand: Decimal


@dataclass(frozen=True)
class Expiring:
    batch: Batch
    warehouse: Warehouse
    quantity: Decimal


def low_stock() -> list[LowStock]:
    products = (
        Product.objects.filter(is_active=True, reorder_level__gt=0)
        .annotate(
            on_hand=Coalesce(Sum("levels__quantity"), ZERO, output_field=models.DecimalField())
        )
        .filter(on_hand__lt=F("reorder_level"))
        .order_by("name")
    )
    return [LowStock(product, product.on_hand) for product in products]


def expiring(within_days: int = 30) -> list[Expiring]:
    limit = timezone.localdate() + timedelta(days=within_days)
    rows = (
        BatchLevel.objects.filter(quantity__gt=0, batch__expiry_date__lte=limit)
        .select_related("batch", "batch__product", "warehouse")
        .order_by("batch__expiry_date")
    )
    return [Expiring(row.batch, row.warehouse, row.quantity) for row in rows]


def contra_default() -> Account:
    return accounting.account_for_role("inventory_adjustments")
