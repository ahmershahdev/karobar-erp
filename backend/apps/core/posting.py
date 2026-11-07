"""Posting rules: which accounts each business event debits and credits.

Rules speak in account roles ("receivables", "sales"), not account codes. Each tenant's chart maps
roles to its own accounts, so the same rule works for every chart of accounts. Every rule returns
lines that pass journal.validate_lines(); zero amounts produce no line.
"""

from collections.abc import Sequence
from decimal import Decimal

from .journal import Line, validate_lines
from .money import quantize_money

ZERO = Decimal(0)


def _lines(*entries: tuple[str, Decimal, Decimal]) -> list[Line]:
    lines = [
        Line(account, quantize_money(debit), quantize_money(credit))
        for account, debit, credit in entries
        if quantize_money(debit) or quantize_money(credit)
    ]
    validate_lines(lines)
    return lines


def _non_negative(**amounts: Decimal) -> None:
    for name, amount in amounts.items():
        if quantize_money(amount) < 0:
            raise ValueError(f"{name} cannot be negative")


def sale(
    net: Decimal, tax: Decimal = ZERO, cost: Decimal = ZERO, discount: Decimal = ZERO
) -> list[Line]:
    """A credit sale: the customer owes net plus tax, and stock leaves at cost.

    `net` is after any discount. The discount is shown on its own account, so sales keep the
    full price and the profit and loss shows what was given away.

    Dr receivables (net + tax); Dr sales discounts (discount); Cr sales (net + discount);
    Cr output tax (tax); Dr cost of goods sold, Cr inventory (cost).
    """
    _non_negative(net=net, tax=tax, cost=cost, discount=discount)
    return _lines(
        ("receivables", net + tax, ZERO),
        ("sales_discounts", discount, ZERO),
        ("sales", ZERO, net + discount),
        ("tax_output", ZERO, tax),
        ("cogs", cost, ZERO),
        ("inventory", ZERO, cost),
    )


def purchase(net: Decimal, tax: Decimal = ZERO) -> list[Line]:
    """A credit purchase of stock. Input tax is recoverable, so it is an asset, not a cost.

    Dr inventory (net); Dr input tax (tax); Cr payables (net + tax).
    """
    _non_negative(net=net, tax=tax)
    return _lines(
        ("inventory", net, ZERO),
        ("tax_input", tax, ZERO),
        ("payables", ZERO, net + tax),
    )


def supplier_bill(
    received: Decimal,
    billed_goods: Decimal,
    expenses: Sequence[tuple[str, Decimal]] = (),
    tax: Decimal = ZERO,
) -> list[Line]:
    """A supplier's bill for goods already received and, optionally, services or expenses.

    The goods receipt booked stock at the order price against goods received not invoiced
    (GRNI). The bill clears GRNI at that same `received` value; whatever the supplier charged
    above or below it goes to purchase price variance. Stock already issued may have left at the
    old cost, so the variance goes to the books rather than back into stock value.

    Dr GRNI (received); Dr or Cr purchase variance (billed_goods - received);
    Dr each expense account; Dr input tax; Cr payables (everything billed plus tax).
    """
    _non_negative(received=received, billed_goods=billed_goods, tax=tax)
    for account, amount in expenses:
        _non_negative(**{account: amount})
    variance = quantize_money(billed_goods) - quantize_money(received)
    total = billed_goods + sum((amount for _, amount in expenses), ZERO) + tax
    return _lines(
        ("grni", received, ZERO),
        ("purchase_variance", max(variance, ZERO), max(-variance, ZERO)),
        *((account, amount, ZERO) for account, amount in expenses),
        ("tax_input", tax, ZERO),
        ("payables", ZERO, total),
    )


def receipt(amount: Decimal, into: str = "cash") -> list[Line]:
    """A customer pays: Dr cash or bank; Cr receivables."""
    _non_negative(amount=amount)
    return _lines((into, amount, ZERO), ("receivables", ZERO, amount))


def payment(amount: Decimal, out_of: str = "cash") -> list[Line]:
    """We pay a supplier: Dr payables; Cr cash or bank."""
    _non_negative(amount=amount)
    return _lines(("payables", amount, ZERO), (out_of, ZERO, amount))


def credit_note(net: Decimal, tax: Decimal = ZERO) -> list[Line]:
    """Goods come back: the sale is undone, through returns so it still shows in the books.

    Dr sales returns (net); Dr output tax (tax); Cr receivables (net + tax). The stock coming
    back is a stock receipt with its own entry, against cost of goods sold.
    """
    _non_negative(net=net, tax=tax)
    return _lines(
        ("sales_returns", net, ZERO),
        ("tax_output", tax, ZERO),
        ("receivables", ZERO, net + tax),
    )


def cash_difference(difference: Decimal) -> list[Line]:
    """What the till count found against what it should hold. Below zero means cash is missing.

    Short: Dr cash over and short, Cr cash. Over: Dr cash, Cr cash over and short.
    """
    amount = abs(difference)
    if difference < 0:
        return _lines(("cash_over_short", amount, ZERO), ("cash", ZERO, amount))
    return _lines(("cash", amount, ZERO), ("cash_over_short", ZERO, amount))


def stock_in(value: Decimal, contra: str) -> list[Line]:
    """Stock arrives without a supplier bill (opening stock, a count that found more).

    Dr inventory; Cr `contra`, for example opening equity or an adjustment account.
    """
    _non_negative(value=value)
    return _lines(("inventory", value, ZERO), (contra, ZERO, value))


def stock_out(cost: Decimal, contra: str) -> list[Line]:
    """Stock leaves without a sale (damage, own use, a count that found less).

    Dr `contra`, usually an inventory adjustments expense; Cr inventory at cost.
    """
    _non_negative(cost=cost)
    return _lines((contra, cost, ZERO), ("inventory", ZERO, cost))


def reversal(lines: Sequence[Line]) -> list[Line]:
    """The entry that cancels `lines`: every debit becomes a credit and the other way round.

    Posted entries are never edited or deleted; a mistake is undone by posting its reversal.
    """
    reversed_lines = [Line(line.account, line.credit, line.debit) for line in lines]
    validate_lines(reversed_lines)
    return reversed_lines
