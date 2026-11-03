"""Small HTTPS calls to third parties (reCAPTCHA, OAuth providers) without a client library.

Only https URLs are allowed, every call has a timeout, and responses must be JSON objects. Any
failure raises OutboundError, so callers decide once whether to fail open or closed.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

TIMEOUT_SECONDS = 8
MAX_BYTES = 256 * 1024


class OutboundError(Exception):
    pass


def _send(request: urllib.request.Request) -> dict[str, Any]:
    if urllib.parse.urlsplit(request.full_url).scheme != "https":
        raise OutboundError("only https is allowed")
    try:
        # The scheme is checked above, so file: and other handlers can't be reached.
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            body = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        body = exc.read(MAX_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OutboundError(str(exc)) from exc
    if len(body) > MAX_BYTES:
        raise OutboundError("response too large")
    try:
        data = json.loads(body)
    except ValueError as exc:
        raise OutboundError("response is not JSON") from exc
    if not isinstance(data, dict):
        raise OutboundError("response is not a JSON object")
    return data


def post_form(url: str, fields: dict[str, str]) -> dict[str, Any]:
    payload = urllib.parse.urlencode(fields).encode()
    request = urllib.request.Request(  # noqa: S310
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    return _send(request)


def get_json(url: str, bearer: str | None = None) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    return _send(urllib.request.Request(url, headers=headers))  # noqa: S310
