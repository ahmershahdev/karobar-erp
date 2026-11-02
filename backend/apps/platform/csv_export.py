import codecs
import csv
import io
from collections.abc import Iterable, Sequence
from decimal import Decimal

from django.http import HttpResponse
from django.utils.http import content_disposition_header

# A cell that starts with one of these is run as a formula by Excel and LibreOffice. Account names
# and memos are typed by users, so an attacker could plant "=HYPERLINK(...)" in one and wait for
# an accountant to open the export (OWASP "CSV Injection").
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
UTF8_BOM = codecs.BOM_UTF8.decode("utf-8")


def safe_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal | int):
        return str(value)
    text = str(value)
    return f"'{text}" if text.startswith(FORMULA_START) else text


def csv_response(
    filename: str, header: Sequence[str], rows: Iterable[Sequence[object]]
) -> HttpResponse:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([safe_cell(cell) for cell in header])
    for row in rows:
        writer.writerow([safe_cell(cell) for cell in row])
    # The byte order mark makes Excel read the file as UTF-8, so Urdu and Arabic names survive.
    response = HttpResponse(UTF8_BOM + buffer.getvalue(), content_type="text/csv; charset=utf-8")
    # Filenames can carry user-typed account codes; Django's helper quotes and encodes them.
    response["Content-Disposition"] = content_disposition_header(True, filename) or "attachment"
    return response
