import logging
from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .context import request_id_var

logger = logging.getLogger(__name__)


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()

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
    return response
