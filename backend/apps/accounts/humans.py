"""Checks that a public form was sent by a person: a honeypot field and Google reCAPTCHA.

v3 runs invisibly and scores the request. When the score is too low, or v3 can't be verified,
the API answers 400 with code "captcha_v2_required" and the form shows the v2 checkbox; the
next submission carries a v2 token instead. Tokens are verified server side against Google's
siteverify endpoint, and the v3 action must match the form, so a token minted for one form
can't be replayed on another.
"""

from typing import Any

from django.conf import settings
from rest_framework import serializers, status
from rest_framework.exceptions import APIException

from apps.platform.http import OutboundError, post_form

VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"
HONEYPOT_FIELD = "website"


class CaptchaRequired(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Please confirm you're not a robot."
    default_code = "captcha_v2_required"


class CaptchaUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "We couldn't check the form just now. Try again in a moment."
    default_code = "captcha_unavailable"


class HumanFields(serializers.Serializer[None]):
    """Fields every protected form accepts; mixed into the form serializers."""

    website = serializers.CharField(required=False, allow_blank=True, max_length=200)
    captcha_v3 = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    captcha_v2 = serializers.CharField(required=False, allow_blank=True, max_length=4000)


def is_bot(data: dict[str, Any]) -> bool:
    """True when the hidden honeypot field was filled in, which people never see to do."""
    return bool(str(data.get(HONEYPOT_FIELD) or "").strip())


def enabled() -> bool:
    return bool(settings.RECAPTCHA_V3_SECRET_KEY or settings.RECAPTCHA_V2_SECRET_KEY)


def _verify(secret: str, token: str, remote_ip: str | None) -> dict[str, Any]:
    fields = {"secret": secret, "response": token}
    if remote_ip:
        fields["remoteip"] = remote_ip
    try:
        return post_form(VERIFY_URL, fields)
    except OutboundError as exc:
        raise CaptchaUnavailable from exc


def _v3_passes(token: str, action: str, remote_ip: str | None) -> bool:
    result = _verify(settings.RECAPTCHA_V3_SECRET_KEY, token, remote_ip)
    score = result.get("score")
    return (
        result.get("success") is True
        and result.get("action") == action
        and isinstance(score, int | float)
        and score >= settings.RECAPTCHA_V3_MIN_SCORE
    )


def check(data: dict[str, Any], action: str, remote_ip: str | None) -> None:
    """Raise unless the request passes the configured reCAPTCHA checks."""
    if not enabled():
        return
    v2_token = str(data.get("captcha_v2") or "")
    if v2_token and settings.RECAPTCHA_V2_SECRET_KEY:
        if _verify(settings.RECAPTCHA_V2_SECRET_KEY, v2_token, remote_ip).get("success") is True:
            return
        raise CaptchaRequired
    v3_token = str(data.get("captcha_v3") or "")
    if v3_token and settings.RECAPTCHA_V3_SECRET_KEY and _v3_passes(v3_token, action, remote_ip):
        return
    raise CaptchaRequired
