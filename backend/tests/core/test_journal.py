from decimal import Decimal

import pytest

from apps.core.journal import Line, UnbalancedEntryError, validate_lines

D = Decimal


def test_balanced_entry_passes() -> None:
    validate_lines([Line("cash", debit=D("100.00")), Line("sales", credit=D("100.00"))])


def test_rounding_happens_before_comparison() -> None:
    validate_lines(
        [
            Line("cash", debit=D("33.333")),
            Line("cash", debit=D("66.667")),
            Line("sales", credit=D("100.00")),
        ]
    )


@pytest.mark.parametrize(
    ("lines", "message"),
    [
        ([Line("cash", debit=D(1))], "at least two"),
        ([Line("cash", debit=D(-1)), Line("sales", credit=D(-1))], "negative"),
        ([Line("cash", debit=D(1), credit=D(1)), Line("sales", credit=D(0))], "exactly one"),
        ([Line("cash"), Line("sales", credit=D(1))], "exactly one"),
        ([Line("cash", debit=D(10)), Line("sales", credit=D(9))], "do not equal"),
    ],
)
def test_invalid_entries_are_rejected(lines: list[Line], message: str) -> None:
    with pytest.raises(UnbalancedEntryError, match=message):
        validate_lines(lines)
