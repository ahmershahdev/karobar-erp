"""Stock valuation: what stock is worth, and what it costs when it leaves.

Two methods, chosen per business:

- Moving average: every receipt re-averages the unit cost of what is on hand; issues leave at
  that average. Simple, smooth, and what most small shops in Pakistan and the Gulf use.
- FIFO: stock leaves in the order it arrived, each unit at the cost it was bought for. Closest to
  how perishables physically move; required when cost layers must be auditable.

Quantities use four decimal places and money two, both rounded in apps.core.money.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from .money import quantize_money, quantize_quantity

ZERO = Decimal(0)


class InsufficientStockError(ValueError):
    pass


class ValuationError(ValueError):
    pass


def to_base(quantity: Decimal, factor: Decimal) -> Decimal:
    """Convert a quantity in a pack unit (a carton of 12) to the product's base unit."""
    if factor <= 0:
        raise ValuationError("a unit conversion factor must be positive")
    return quantize_quantity(quantity * factor)


@dataclass(frozen=True, slots=True)
class Holding:
    """What sits in one warehouse: quantity in base units and its total book value."""

    quantity: Decimal
    value: Decimal


def _positive(quantity: Decimal) -> Decimal:
    qty = quantize_quantity(quantity)
    if qty <= 0:
        raise ValuationError("quantity must be positive")
    return qty


def average_receive(holding: Holding, quantity: Decimal, unit_cost: Decimal) -> Holding:
    qty = _positive(quantity)
    if unit_cost < 0:
        raise ValuationError("unit cost cannot be negative")
    return Holding(
        quantize_quantity(holding.quantity + qty),
        quantize_money(holding.value + qty * unit_cost),
    )


def average_issue(holding: Holding, quantity: Decimal) -> tuple[Holding, Decimal]:
    """Take `quantity` out at the average cost. Returns the new holding and the cost taken.

    Issuing everything takes the whole remaining value, so rounding never leaves a few paisa of
    value sitting on zero stock.
    """
    qty = _positive(quantity)
    if qty > holding.quantity:
        raise InsufficientStockError(f"only {holding.quantity} on hand, {qty} requested")
    if qty == holding.quantity:
        return Holding(ZERO, ZERO), quantize_money(holding.value)
    cost = quantize_money(holding.value * qty / holding.quantity)
    return Holding(
        quantize_quantity(holding.quantity - qty), quantize_money(holding.value - cost)
    ), cost


@dataclass(frozen=True, slots=True)
class Layer:
    """One FIFO cost layer: what is left of a receipt, at the cost it came in at."""

    key: int
    quantity: Decimal
    unit_cost: Decimal


@dataclass(frozen=True, slots=True)
class Consumption:
    key: int
    quantity: Decimal
    cost: Decimal


def fifo_issue(layers: Sequence[Layer], quantity: Decimal) -> tuple[list[Consumption], Decimal]:
    """Consume `quantity` from the oldest layers first.

    `layers` must already be in arrival order. Returns what was taken from each layer and the
    total cost. Nothing is consumed unless the whole quantity is available.
    """
    qty = _positive(quantity)
    available = sum((layer.quantity for layer in layers), ZERO)
    if qty > available:
        raise InsufficientStockError(f"only {available} on hand, {qty} requested")
    remaining = qty
    taken: list[Consumption] = []
    for layer in layers:
        if remaining <= 0:
            break
        take = min(layer.quantity, remaining)
        if take <= 0:
            continue
        taken.append(Consumption(layer.key, take, quantize_money(take * layer.unit_cost)))
        remaining = quantize_quantity(remaining - take)
    return taken, quantize_money(sum((part.cost for part in taken), ZERO))
