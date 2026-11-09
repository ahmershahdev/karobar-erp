from datetime import date, datetime
from decimal import Decimal

import pytest

from apps.core.wps import Employer, Line, WpsError, edr, scr, sif

D = Decimal
BOSS = Employer("965625", "302620122")
MADE = datetime(2026, 3, 10, 16, 30, 0)
ONE = Line(
    "12345678",
    "703420114",
    "ae020340000221234567001",
    date(2026, 3, 1),
    date(2026, 3, 31),
    D("100"),
    D("30"),
)


def test_the_guide_sample_comes_out_line_for_line() -> None:
    name, text = sif(BOSS, date(2026, 3, 1), MADE, [ONE], "PAY-000001")
    assert name == "0000000965625260310163000.SIF"
    assert text.split("\r\n") == [
        "EDR,00000012345678,703420114,AE020340000221234567001,2026-03-01,2026-03-31,31,"
        "100.00,30.00,0",
        "SCR,0000000965625,302620122,2026-03-10,1630,032026,1,130.00,AED,PAY-000001",
        "",
    ]


def test_part_of_a_month_and_unpaid_days() -> None:
    line = Line(
        "1", "703420114", "1234", date(2026, 3, 16), date(2026, 3, 31), D("50"), unpaid_days=2
    )
    assert edr(line).split(",")[6:] == ["16", "50.00", "0.00", "2"]


def test_the_total_is_the_sum_of_every_line() -> None:
    other = Line("2", "703420114", "99", date(2026, 3, 1), date(2026, 3, 31), D("0.005"))
    assert scr(BOSS, date(2026, 3, 1), MADE, [ONE, other], "R").split(",")[6:8] == [
        "2",
        "130.01",
    ]


@pytest.mark.parametrize(
    "line",
    [
        Line("", "703420114", "1", date(2026, 3, 1), date(2026, 3, 31), D(1)),
        Line("123456789012345", "703420114", "1", date(2026, 3, 1), date(2026, 3, 31), D(1)),
        Line("12-3", "703420114", "1", date(2026, 3, 1), date(2026, 3, 31), D(1)),
        Line("1", "70342011", "1", date(2026, 3, 1), date(2026, 3, 31), D(1)),
        Line("1", "70342011X", "1", date(2026, 3, 1), date(2026, 3, 31), D(1)),
        Line("1", "703420114", "", date(2026, 3, 1), date(2026, 3, 31), D(1)),
        Line("1", "703420114", "=SUM(A1)", date(2026, 3, 1), date(2026, 3, 31), D(1)),
        Line("1", "703420114", "A" * 24, date(2026, 3, 1), date(2026, 3, 31), D(1)),
        Line("1", "703420114", "1", date(2026, 3, 31), date(2026, 3, 1), D(1)),
        Line("1", "703420114", "1", date(2026, 3, 1), date(2026, 3, 31), D(-1)),
        Line("1", "703420114", "1", date(2026, 3, 1), date(2026, 3, 31), D(1), unpaid_days=-1),
    ],
)
def test_bad_lines_are_refused(line: Line) -> None:
    with pytest.raises(WpsError):
        edr(line)


@pytest.mark.parametrize(
    ("employer", "ref"),
    [
        (Employer("", "302620122"), "R"),
        (Employer("12345678901234", "302620122"), "R"),
        (Employer("965625", "3026201"), "R"),
        (BOSS, "has a comma,"),
        (BOSS, "R" * 36),
    ],
)
def test_bad_employers_and_references_are_refused(employer: Employer, ref: str) -> None:
    with pytest.raises(WpsError):
        scr(employer, date(2026, 3, 1), MADE, [ONE], ref)


def test_a_file_needs_someone_in_it() -> None:
    with pytest.raises(WpsError):
        sif(BOSS, date(2026, 3, 1), MADE, [], "R")
