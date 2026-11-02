"""Which side an account's balance normally sits on, and how to read a balance from totals."""

from decimal import Decimal
from enum import StrEnum

from .money import quantize_money


class AccountType(StrEnum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    INCOME = "income"
    EXPENSE = "expense"


DEBIT_NORMAL = frozenset({AccountType.ASSET, AccountType.EXPENSE})


def is_debit_normal(account_type: AccountType) -> bool:
    return account_type in DEBIT_NORMAL


def balance(account_type: AccountType, debits: Decimal, credits: Decimal) -> Decimal:
    """The account's balance, positive when it sits on its normal side.

    An asset with more debits than credits has a positive balance; so does income with more
    credits than debits. A negative result is an unusual balance worth a look (an overdrawn
    bank, a customer who paid twice).
    """
    net = quantize_money(debits) - quantize_money(credits)
    return net if is_debit_normal(account_type) else -net


def split(account_type: AccountType, amount: Decimal) -> tuple[Decimal, Decimal]:
    """Place a balance in the debit or credit column of a trial balance."""
    debit_side = (amount >= 0) == is_debit_normal(account_type)
    value = abs(quantize_money(amount))
    return (value, Decimal("0.00")) if debit_side else (Decimal("0.00"), value)
