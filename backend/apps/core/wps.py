"""The UAE Wage Protection System salary file (SIF), which a WPS agent bank or exchange house
needs to pay salaries.

The layout follows the agents' published guide (Emirates Islamic, "Salary WPS File Creation
Guide"): comma-separated lines with no header, one EDR (employee detail record) per person and one
SCR (salary control record) as the last line, whose total must equal the sum of every EDR's fixed
and variable pay. The file is named after the employer's MOL ID and the moment it was made, and
that moment must match the SCR. The optional EVP line (a breakdown of variable pay) is not
written: payroll pays everything as the fixed component.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from .money import quantize_money

ZERO = Decimal(0)


class WpsError(ValueError):
    pass


@dataclass(frozen=True)
class Employer:
    # The 13-digit establishment ID from the Ministry of Labour (MOHRE).
    mol_id: str
    # The 9-digit routing code of the employer's bank, as the Central Bank assigns it.
    bank_code: str


@dataclass(frozen=True)
class Line:
    # The 14-character person ID from the labour card.
    person_id: str
    # The 9-digit routing code of the employee's bank or exchange house.
    agent_code: str
    # The account or salary card number at that agent, IBANs included.
    account: str
    starts: date
    ends: date
    fixed: Decimal
    variable: Decimal = ZERO
    unpaid_days: int = 0


def _digits(value: str, size: int, what: str, pad: bool) -> str:
    if not value.isascii() or not value.isdigit() or not 0 < len(value) <= size:
        raise WpsError(f"{what} is up to {size} digits")
    if not pad and len(value) != size:
        raise WpsError(f"{what} is exactly {size} digits")
    return value.zfill(size)


def check_employer(employer: Employer) -> None:
    _digits(employer.mol_id, 13, "the employer's MOL ID", pad=True)
    _digits(employer.bank_code, 9, "the employer's bank routing code", pad=False)


def check_line(line: Line) -> None:
    person = line.person_id
    if not person.isascii() or not person.isalnum() or not 0 < len(person) <= 14:
        raise WpsError("the person ID is up to 14 letters or digits")
    _digits(line.agent_code, 9, "the bank routing code", pad=False)
    # The guide allows 16 characters, from before UAE IBANs (23) became the usual account.
    account = line.account
    if not account.isascii() or not account.isalnum() or not 0 < len(account) <= 23:
        raise WpsError("the account is up to 23 letters or digits")
    if line.ends < line.starts:
        raise WpsError("the pay period ends before it starts")
    if line.fixed < 0 or line.variable < 0 or line.unpaid_days < 0:
        raise WpsError("amounts and unpaid days can't be negative")


def _amount(value: Decimal) -> str:
    return f"{quantize_money(value):.2f}"


def edr(line: Line) -> str:
    check_line(line)
    days = (line.ends - line.starts).days + 1
    fields = [
        "EDR",
        line.person_id.zfill(14),
        line.agent_code,
        line.account.upper(),
        line.starts.isoformat(),
        line.ends.isoformat(),
        str(days),
        _amount(line.fixed),
        _amount(line.variable),
        str(line.unpaid_days),
    ]
    return ",".join(fields)


def scr(employer: Employer, month: date, made: datetime, lines: Sequence[Line], ref: str) -> str:
    check_employer(employer)
    if not ref.isascii() or not all(c.isalnum() or c in "-_/" for c in ref) or len(ref) > 35:
        raise WpsError("the employer reference is up to 35 letters, digits, - _ or /")
    total = sum(
        (quantize_money(line.fixed) + quantize_money(line.variable) for line in lines), ZERO
    )
    fields = [
        "SCR",
        employer.mol_id.zfill(13),
        employer.bank_code,
        made.strftime("%Y-%m-%d"),
        made.strftime("%H%M"),
        month.strftime("%m%Y"),
        str(len(lines)),
        _amount(total),
        "AED",
        ref,
    ]
    return ",".join(fields)


def sif(
    employer: Employer, month: date, made: datetime, lines: Sequence[Line], ref: str
) -> tuple[str, str]:
    """The file name and the file's text for one month's salaries."""
    if not lines:
        raise WpsError("a salary file needs at least one person")
    body = [edr(line) for line in lines]
    body.append(scr(employer, month, made, lines, ref))
    name = f"{employer.mol_id.zfill(13)}{made:%y%m%d%H%M%S}.SIF"
    return name, "\r\n".join(body) + "\r\n"
