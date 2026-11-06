"""A chain of signed records, so an edited, removed or inserted record can be noticed.

Each signature covers the record and the signature before it. Changing any record breaks its own
signature; removing or inserting one breaks the next. Only someone holding the key can sign, so
this shows a log has not been altered since the server wrote it. It says nothing about who was
at the keyboard, and it is not a legal electronic signature.
"""

import hashlib
import hmac
import json
from collections.abc import Sequence


def sign(key: bytes, fields: dict[str, str], previous: str) -> str:
    payload = json.dumps(
        {"fields": fields, "previous": previous},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()


def first_break(key: bytes, records: Sequence[tuple[dict[str, str], str]]) -> int | None:
    """The position of the first record that doesn't check out, or None when all of them do."""
    previous = ""
    for position, (fields, signature) in enumerate(records):
        if not hmac.compare_digest(sign(key, fields, previous), signature):
            return position
        previous = signature
    return None
