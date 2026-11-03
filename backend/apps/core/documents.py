"""Arithmetic shared by purchase and sales documents: line amounts and partial clearing."""

from decimal import Decimal

from .money import quantize_money

ZERO = Decimal(0)


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
