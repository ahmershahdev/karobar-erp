"""The end-to-end tests (e2e/) run a real server against a real database, but nothing leaves the
machine: mail goes to files the tests read, jobs run in the request, and the bot check, the chat
model and social sign-in are off whatever the developer's .env holds."""

from .base import REST_FRAMEWORK, env
from .dev import *  # noqa: F403

CELERY_TASK_ALWAYS_EAGER = True

EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
EMAIL_FILE_PATH = env("E2E_MAIL_DIR")

RECAPTCHA_V3_SITE_KEY = RECAPTCHA_V3_SECRET_KEY = ""
RECAPTCHA_V2_SITE_KEY = RECAPTCHA_V2_SECRET_KEY = ""
GROQ_API_KEY = ""
GOOGLE_OAUTH_CLIENT_ID = GOOGLE_OAUTH_CLIENT_SECRET = ""
FACEBOOK_SIGN_IN = False

# Every test signs in, from one address. The real limits are checked by the load tests, against
# the production stack.
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
    **REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
    "anon": "6000/min",
    "user": "6000/min",
    "auth": "600/min",
}

# Errors must look as they do in production, so the tests can check nothing leaks.
DEBUG = False
