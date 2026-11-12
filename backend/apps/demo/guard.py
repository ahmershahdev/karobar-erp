"""Keep the shared demo account usable for everyone.

Anyone can sign in as the demo owner, so the account itself must not change, and it must not
reach outside the demo: no new email or password, no deleting it, no inviting people (that
sends email), no joining or handing over businesses, no new businesses, and no chat (each
question costs a paid model call). Everything inside the demo businesses stays open, because the
nightly reset puts it back.
"""

from collections.abc import Callable
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.urls import Resolver404, resolve

MESSAGE = "The demo account can't do this. Sign up for your own account to try it."

# URL names whose changes are refused for the demo account. Reading them stays allowed.
BLOCKED = frozenset(
    {
        "me",
        "password-change",
        "email-change",
        "email-change-confirm",
        "account-delete",
        "my-tenants",
        "member-owner",
        "invitation-list",
        "invitation-accept",
        "assistant-ask",
        "assistant-confirm",
    }
)
SAFE = frozenset({"GET", "HEAD", "OPTIONS"})


def is_demo_email(email: str) -> bool:
    return bool(settings.DEMO_MODE) and email.lower() == settings.DEMO_EMAIL.lower()


def is_demo_user(user: Any) -> bool:
    return bool(getattr(user, "is_authenticated", False)) and is_demo_email(user.email)


class DemoGuardMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.method not in SAFE and is_demo_user(getattr(request, "user", None)):
            try:
                name = resolve(request.path_info).url_name
            except Resolver404:
                name = None
            if name in BLOCKED:
                return JsonResponse({"detail": MESSAGE, "code": "demo_account"}, status=403)
        return self.get_response(request)
