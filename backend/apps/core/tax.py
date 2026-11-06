"""Sales tax arithmetic. The rates themselves are data, entered with their source and dates."""

from datetime import date
from decimal import Decimal

from .money import quantize_money


def tax_on(amount: Decimal, rate_percent: Decimal) -> Decimal:
    """Tax on a line's amount before tax, rounded once per line as it is printed."""
    return quantize_money(amount * rate_percent / 100)


def is_valid_on(valid_from: date, valid_to: date | None, on: date) -> bool:
    """Both ends count. No end date means the rate still applies."""
    return valid_from <= on and (valid_to is None or on <= valid_to)
