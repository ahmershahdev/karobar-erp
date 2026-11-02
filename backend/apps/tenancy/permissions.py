from typing import Any

from django.http import HttpRequest
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

SAFE_ACTIONS = {"GET": "view", "HEAD": "view", "OPTIONS": "view"}
WRITE_ACTIONS = {"POST": "create", "PUT": "update", "PATCH": "update", "DELETE": "delete"}


def membership_of(request: Request | HttpRequest) -> Any:
    return getattr(request, "membership", None) or getattr(
        getattr(request, "_request", None), "membership", None
    )


class IsTenantMember(BasePermission):
    def has_permission(self, request: Request, view: APIView) -> bool:
        return membership_of(request) is not None


class HasModulePermission(IsTenantMember):
    """Grants access when the member's role allows `view.module` for the request's action.

    Views can set `required_action` to name a custom action such as "post".
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        membership = membership_of(request)
        if membership is None:
            return False
        if membership.is_owner:
            return True
        module = getattr(view, "module", None)
        if module is None:
            return False
        method = request.method or "GET"
        action = getattr(view, "required_action", None) or SAFE_ACTIONS.get(
            method, WRITE_ACTIONS.get(method, "")
        )
        role = membership.role
        return role is not None and action in role.permissions.get(module, [])
