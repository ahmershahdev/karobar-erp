from urllib.parse import urlencode

from django.conf import settings

from apps.platform.tasks import send_email

from .models import User
from .tokens import make_email_token, make_reset_token


def app_link(path: str, **params: str) -> str:
    return f"{settings.SITE_URL.rstrip('/')}/{path}?{urlencode(params)}"


def send_verification(user: User) -> None:
    link = app_link("verify-email", token=make_email_token(user))
    send_email.delay(
        user.email,
        "Confirm your email for Karobar ERP",
        f"Confirm your email address by opening this link within 3 days:\n\n{link}\n\n"
        "If you didn't create a Karobar account, ignore this email.",
    )


def send_already_registered(email: str) -> None:
    send_email.delay(
        email,
        "Someone tried to sign up with your email",
        "A sign-up was attempted with this address, which already has a Karobar account. "
        f"If it was you, sign in or reset your password here:\n\n{app_link('forgot-password')}",
    )


def send_password_reset(user: User) -> None:
    uid, token = make_reset_token(user)
    link = app_link("reset-password", uid=uid, token=token)
    send_email.delay(
        user.email,
        "Reset your Karobar ERP password",
        f"Choose a new password here:\n\n{link}\n\n"
        "The link works once. If you didn't ask for it, ignore this email.",
    )
