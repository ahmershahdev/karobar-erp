from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from .money import quantize_money


class UnbalancedEntryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Line:
    account: str
    debit: Decimal = Decimal(0)
    credit: Decimal = Decimal(0)


def validate_lines(lines: Sequence[Line]) -> None:
    """Raise unless the lines form a postable double-entry journal entry."""
    if len(lines) < 2:
        raise UnbalancedEntryError("a journal entry needs at least two lines")
    for line in lines:
        debit, credit = quantize_money(line.debit), quantize_money(line.credit)
        if debit < 0 or credit < 0:
            raise UnbalancedEntryError(f"negative amount on {line.account}")
        # A line is either a debit or a credit. Allowing both hides netting mistakes.
        if (debit == 0) == (credit == 0):
            raise UnbalancedEntryError(f"line on {line.account} must have exactly one side")
    debits = _total(line.debit for line in lines)
    credits = _total(line.credit for line in lines)
    if debits != credits:
        raise UnbalancedEntryError(f"debits {debits} do not equal credits {credits}")


def _total(amounts: Iterable[Decimal]) -> Decimal:
    return quantize_money(sum((quantize_money(a) for a in amounts), Decimal(0)))
