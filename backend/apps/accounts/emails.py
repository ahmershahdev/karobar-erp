from urllib.parse import urlencode

from django.conf import settings

from apps.platform.mail import send_message

from .models import User
from .tokens import make_email_token, make_reset_token


def app_link(path: str, **params: str) -> str:
    return f"{settings.SITE_URL.rstrip('/')}/{path}?{urlencode(params)}"


def send_verification(user: User) -> None:
    link = app_link("verify-email", token=make_email_token(user))
    send_message(
        user.email,
        "Confirm your email for Karobar ERP",
        "Confirm your email",
        ["Open this link within 3 days to finish setting up your account."],
        ("Confirm my email", link),
        "If you didn't create a Karobar account, ignore this email.",
    )


def send_already_registered(email: str) -> None:
    send_message(
        email,
        "Someone tried to sign up with your email",
        "You already have an account",
        [
            "A sign-up was attempted with this address, which already has a Karobar account.",
            "If it was you, sign in, or choose a new password here.",
        ],
        ("Choose a new password", app_link("forgot-password")),
        "If it wasn't you, nothing has changed and you can ignore this email.",
    )


def send_password_reset(user: User) -> None:
    uid, token = make_reset_token(user)
    link = app_link("reset-password", uid=uid, token=token)
    send_message(
        user.email,
        "Reset your Karobar ERP password",
        "Choose a new password",
        ["Use this link to choose a new password. It works once."],
        ("Choose a new password", link),
        "If you didn't ask for this, ignore this email and your account stays as it is.",
    )
