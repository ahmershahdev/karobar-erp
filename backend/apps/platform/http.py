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
    pass


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    # urllib would resend the request, bearer token included, wherever a redirect points, without
    # the https check. The endpoints we call don't redirect, so one is treated as a failure.
    def redirect_request(self, *args: Any, **kwargs: Any) -> urllib.request.Request | None:
        return None


OPENER = urllib.request.build_opener(_NoRedirects)


def _send(request: urllib.request.Request) -> dict[str, Any]:
    if urllib.parse.urlsplit(request.full_url).scheme != "https":
        raise OutboundError("only https is allowed")
    try:
        # The scheme is checked above, so file: and other handlers can't be reached.
        with OPENER.open(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            raise OutboundError("redirects are not followed") from exc
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
