"""Customer credit limits."""

from decimal import Decimal

from .money import quantize_money


def over_limit(balance: Decimal, amount: Decimal, limit: Decimal | None) -> bool:
    """True if `amount` more on a `balance` already owed would pass the customer's limit.

    No limit (None) means the customer may owe any amount. A limit of zero is a real limit: that
    customer buys for cash only. An advance makes `balance` negative, which adds to what they may
    buy, because they have already paid for it.
    """
    if limit is None:
        return False
    return quantize_money(balance) + quantize_money(amount) > quantize_money(limit)
