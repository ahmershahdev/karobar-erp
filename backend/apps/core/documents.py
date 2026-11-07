"""Arithmetic shared by purchase and sales documents: line amounts, discounts and partial
clearing."""

from collections.abc import Sequence
from decimal import Decimal

from .money import quantize_money

ZERO = Decimal(0)
HUNDRED = Decimal(100)


class DocumentError(ValueError):
    pass


def line_amount(quantity: Decimal, unit_price: Decimal) -> Decimal:
    """Quantity times price, rounded once per line, as printed on the document."""
    if quantity < 0 or unit_price < 0:
        raise DocumentError("quantity and price cannot be negative")
    return quantize_money(quantity * unit_price)


def share(value: Decimal, done: Decimal, part: Decimal, whole: Decimal) -> Decimal:
    """The slice of `value` that `part` more units of `whole` account for, `done` units already.

    Computed as the difference of two rounded running totals rather than by rounding each slice,
    so the slices of one value always add back to exactly that value: billing a receipt line of
    10.00 in thirds clears 3.33, 3.34 and 3.33, never 9.99.
    """
    if whole <= 0 or part < 0 or done < 0 or done + part > whole:
        raise DocumentError("the part must fit inside the whole")
    before = quantize_money(value * done / whole)
    after = quantize_money(value * (done + part) / whole)
    return after - before


def percent_of(amount: Decimal, percent: Decimal) -> Decimal:
    """A percentage of an amount, rounded once: 12.5% off 99.99 is 12.50."""
    if amount < 0 or not ZERO <= percent <= HUNDRED:
        raise DocumentError("a percentage is between 0 and 100 of an amount that isn't negative")
    return quantize_money(amount * percent / HUNDRED)


def spread(amount: Decimal, weights: Sequence[Decimal]) -> list[Decimal]:
    """Split a bill discount over its lines in proportion to their amounts.

    Uses the same running totals as `share`, so the parts always add back to exactly `amount`:
    1.00 off three equal lines is 0.33, 0.34 and 0.33. A discount larger than the lines it comes
    off would leave a line below zero, so it is refused.
    """
    if amount < 0 or any(weight < 0 for weight in weights):
        raise DocumentError("a discount and the lines it comes off can't be negative")
    if amount == 0:
        return [ZERO for _ in weights]
    total = sum(weights, ZERO)
    if amount > total:
        raise DocumentError("a discount can't be more than the lines it comes off")
    parts = []
    done = ZERO
    for weight in weights:
        parts.append(share(amount, done, weight, total))
        done += weight
    return parts
