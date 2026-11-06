from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import (
    EMAIL_BACKEND,
    RECAPTCHA_V2_SECRET_KEY,
    RECAPTCHA_V2_SITE_KEY,
    RECAPTCHA_V3_SECRET_KEY,
    RECAPTCHA_V3_SITE_KEY,
    env,
)

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_REDIRECT_EXEMPT = [r"^api/health/$"]
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_NAME = "__Host-kb_session"
CSRF_COOKIE_NAME = "__Host-kb_csrftoken"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Production never prints mail to a log or runs forms without a bot check.
if EMAIL_BACKEND.endswith("console.EmailBackend"):
    raise ImproperlyConfigured("Set RESEND_API_KEY, or EMAIL_BACKEND and the EMAIL_* settings.")
if not all(
    (
        RECAPTCHA_V3_SITE_KEY,
        RECAPTCHA_V3_SECRET_KEY,
        RECAPTCHA_V2_SITE_KEY,
        RECAPTCHA_V2_SECRET_KEY,
    )
):
    raise ImproperlyConfigured("Set the RECAPTCHA_V3_* and RECAPTCHA_V2_* keys.")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")
