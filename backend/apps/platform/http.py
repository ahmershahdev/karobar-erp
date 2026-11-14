"""Small HTTPS calls to third parties (reCAPTCHA, OAuth providers) without a client library.

Only https URLs are allowed, redirects are never followed, every call has a timeout, and responses
must be JSON objects. Any failure raises OutboundError, so callers decide once whether to fail open
or closed.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

TIMEOUT_SECONDS = 8
MAX_BYTES = 256 * 1024


class OutboundError(Exception):
    """`status` and `code` are set when the other side answered with an HTTP error and the
    caller asked for those to raise (see post_json)."""

    def __init__(self, message: str, status: int | None = None, code: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.code = code


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    # urllib would resend the request, bearer token included, wherever a redirect points, without
    # the https check. The endpoints we call don't redirect, so one is treated as a failure.
    def redirect_request(self, *args: Any, **kwargs: Any) -> urllib.request.Request | None:
        return None


OPENER = urllib.request.build_opener(_NoRedirects)


def _error_code(body: bytes) -> str:
    """The short machine-readable code in an error body, such as "rate_limit_exceeded". Only
    that goes in a log: the message beside it can repeat what was sent."""
    try:
        error = json.loads(body).get("error")
        code = error.get("code") or error.get("type") if isinstance(error, dict) else error
    except (ValueError, AttributeError):
        return ""
    return code[:80] if isinstance(code, str) else ""


def _send(
    request: urllib.request.Request, timeout: int = TIMEOUT_SECONDS, raise_errors: bool = False
) -> dict[str, Any]:
    if urllib.parse.urlsplit(request.full_url).scheme != "https":
        raise OutboundError("only https is allowed")
    try:
        # The scheme is checked above, so file: and other handlers can't be reached.
        with OPENER.open(request, timeout=timeout) as response:
            body = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            raise OutboundError("redirects are not followed") from exc
        body = exc.read(MAX_BYTES + 1)
        if raise_errors:
            raise OutboundError(
                f"status {exc.code}", status=exc.code, code=_error_code(body)
            ) from exc
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


def post_json(
    url: str, payload: dict[str, Any], bearer: str, timeout: int = TIMEOUT_SECONDS
) -> dict[str, Any]:
    """Unlike the form and GET helpers, an HTTP error raises here, with its status and code: an
    API's error body is not an answer, and the caller logs why the call failed."""
    request = urllib.request.Request(  # noqa: S310
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {bearer}",
            # Groq's edge refuses the default Python client name.
            "User-Agent": "karobar-erp",
        },
    )
    return _send(request, timeout, raise_errors=True)


def get_json(url: str, bearer: str | None = None) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    return _send(urllib.request.Request(url, headers=headers))  # noqa: S310
