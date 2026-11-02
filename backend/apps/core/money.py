from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# Every amount that reaches the books goes through quantize_money(), so totals computed in
# different places can never disagree by a paisa. ROUND_HALF_UP matches how invoices are
# rounded by hand and by tax authorities in Pakistan and the Gulf; banker's rounding does not.
MONEY_PLACES = 2
QUANTITY_PLACES = 4

_MONEY_EXP = Decimal(1).scaleb(-MONEY_PLACES)
_QUANTITY_EXP = Decimal(1).scaleb(-QUANTITY_PLACES)


class MoneyError(ValueError):
    pass


def to_decimal(value: Decimal | int | str) -> Decimal:
    # float is refused on purpose: Decimal(0.1) is 0.1000000000000000055511151231257827...
    if isinstance(value, bool) or not isinstance(value, Decimal | int | str):
        raise MoneyError(f"expected Decimal, int or str, got {type(value).__name__}")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise MoneyError(f"not a number: {value!r}") from exc
    if not result.is_finite():
        raise MoneyError(f"not a finite number: {value!r}")
    return result


def quantize_money(value: Decimal | int | str) -> Decimal:
    return to_decimal(value).quantize(_MONEY_EXP, rounding=ROUND_HALF_UP)


def quantize_quantity(value: Decimal | int | str) -> Decimal:
    return to_decimal(value).quantize(_QUANTITY_EXP, rounding=ROUND_HALF_UP)
