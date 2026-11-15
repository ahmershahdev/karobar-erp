import logging
from typing import Any

from django.core.exceptions import PermissionDenied, RequestDataTooBig
from django.db import OperationalError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .context import request_id_var
from .locking import RETRYABLE_LOCK_ERRORS

logger = logging.getLogger(__name__)


class BodyTooLarge(exceptions.APIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = "That is too much to send at once."
    default_code = "too_large"


class Busy(exceptions.APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Many people are saving at once. Nothing was saved; please try again."
    default_code = "busy"


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()
    elif isinstance(exc, RequestDataTooBig):
        # nginx refuses these first in production. Reached directly, Django raises while the
        # body is read, which would otherwise be logged and answered as a server error.
        exc = BodyTooLarge()
    elif isinstance(exc, OperationalError) and exc.args and exc.args[0] in RETRYABLE_LOCK_ERRORS:
        # Still waiting for a row lock after the retries. The transaction was rolled back, so
        # nothing was saved and trying again is safe: that is "busy", not "something broke".
        logger.warning("gave up waiting for a lock in %s", context.get("view"))
        exc = Busy()

    response = drf_exception_handler(exc, context)
    if response is None:
        # Anything unhandled is logged with its stack trace here and answered with a bare 500,
        # so SQL, paths and other tenants' ids never reach the client.
        logger.exception("unhandled error in %s", context.get("view"))
        return Response(
            {"detail": "Something went wrong.", "request_id": request_id_var.get()},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    if isinstance(response.data, dict):
        response.data["request_id"] = request_id_var.get()
        # A stable code next to the message lets the app react (show the reCAPTCHA checkbox)
        # without matching on English text.
        detail = getattr(exc, "detail", None)
        if isinstance(detail, exceptions.ErrorDetail):
            response.data["code"] = detail.code
    return response
