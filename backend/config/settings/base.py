from pathlib import Path
from typing import Any

import environ
from celery.schedules import crontab
from csp.constants import NONCE, NONE, SELF
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS: list[str] = env.list("DJANGO_ALLOWED_HOSTS", default=[])
SITE_URL: str = env("SITE_URL")
CSRF_TRUSTED_ORIGINS: list[str] = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[SITE_URL])
ADMIN_URL: str = env("DJANGO_ADMIN_URL", default="admin/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "csp",
    "apps.platform",
    "apps.accounts",
    "apps.tenancy",
    "apps.accounting",
    "apps.inventory",
    "apps.purchasing",
    "apps.sales",
    "apps.reports",
    "apps.pos",
    "apps.assistant",
    "apps.hr",
    "apps.payroll",
    "apps.demo",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.platform.middleware.RequestIdMiddleware",
    "apps.platform.middleware.SecurityHeadersMiddleware",
    "csp.middleware.CSPMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.tenancy.middleware.TenantMiddleware",
    "apps.demo.guard.DemoGuardMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "csp.context_processors.nonce",
            ],
        },
    },
]

# READ COMMITTED keeps gap locks out of the way; correctness under concurrency comes from
# explicit select_for_update() in the services, not from REPEATABLE READ snapshots.
DATABASES = {
    "default": {
        **env.db("DATABASE_URL"),
        "CONN_MAX_AGE": env.int("DB_CONN_MAX_AGE", default=60),
        "CONN_HEALTH_CHECKS": True,
        "ATOMIC_REQUESTS": False,
        "OPTIONS": {
            "charset": "utf8mb4",
            "isolation_level": "read committed",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,"
            "ERROR_FOR_DIVISION_BY_ZERO,ONLY_FULL_GROUP_BY', innodb_lock_wait_timeout=10",
        },
        "TEST": {"CHARSET": "utf8mb4", "COLLATION": "utf8mb4_0900_ai_ci"},
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL: str = env("REDIS_URL")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "karobar",
    }
}

AUTH_USER_MODEL = "accounts.User"
PASSWORD_HASHERS = [
    "apps.accounts.hashers.Argon2WithBcryptFallback",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
SESSION_COOKIE_NAME = "kb_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 12
CSRF_COOKIE_NAME = "kb_csrftoken"
# The SPA reads this cookie to send X-CSRFToken, so it can't be HttpOnly.
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": [SELF],
        "script-src": [SELF, NONCE],
        "style-src": [SELF],
        "img-src": [SELF, "data:"],
        "font-src": [SELF],
        "connect-src": [SELF],
        "object-src": [NONE],
        "base-uri": [NONE],
        "form-action": [SELF],
        "frame-ancestors": [NONE],
    }
}

DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000
DATA_UPLOAD_MAX_NUMBER_FILES = 10
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024

REST_FRAMEWORK: dict[str, Any] = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_PAGINATION_CLASS": "apps.platform.pagination.DefaultPagination",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_ANON", default="60/min"),
        "user": env("THROTTLE_USER", default="600/min"),
        "auth": env("THROTTLE_AUTH", default="10/min"),
        "health": env("THROTTLE_HEALTH", default="120/min"),
        "session": env("THROTTLE_SESSION", default="120/min"),
        "tenancy": env("THROTTLE_TENANCY", default="300/min"),
        "assistant": env("THROTTLE_ASSISTANT", default="20/min"),
    },
    "EXCEPTION_HANDLER": "apps.platform.exceptions.exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "COERCE_DECIMAL_TO_STRING": True,
}
# The proxy in front of us sets X-Forwarded-For; DRF's throttles count the client IP from it,
# so only trust as many hops as we actually run.
NUM_PROXIES = env.int("NUM_PROXIES", default=1)
REST_FRAMEWORK["NUM_PROXIES"] = NUM_PROXIES

SPECTACULAR_SETTINGS = {
    "TITLE": "Karobar ERP API",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAdminUser"],
    # The app's languages appear in more than one field; one name keeps one type in the frontend.
    "ENUM_NAME_OVERRIDES": {
        "LocaleEnum": ["en", "ur", "ar"],
        "ComponentKindEnum": "apps.hr.models.SalaryComponent.Kind",
        "ContractKindEnum": "apps.hr.models.Contract.Kind",
        "LeaveStatusEnum": "apps.hr.models.LeaveRequest.Status",
        "AttendanceStatusEnum": "apps.hr.models.Attendance.Status",
        "CountryEnum": "apps.hr.time_off.COUNTRIES",
        "PayrollStatusEnum": "apps.payroll.models.PayrollRun.Status",
        "ProvinceEnum": "apps.hr.models.Province",
        "ContributionSchemeEnum": "apps.payroll.models.ContributionRate.Scheme",
        "StatusEnum": "apps.accounting.models.JournalEntry.Status",
    },
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = None
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 240
# 02:00 UTC is 07:00 in Pakistan and 05:00 to 06:00 in the Gulf: before the shops open.
CELERY_BEAT_SCHEDULE = {
    "stock-alerts": {
        "task": "apps.inventory.tasks.send_stock_alerts",
        "schedule": crontab(hour=2, minute=0),
    },
    "daily-summaries": {
        "task": "apps.reports.tasks.send_daily_summaries",
        "schedule": crontab(hour=2, minute=5),
    },
    "former-employee-details": {
        "task": "apps.hr.tasks.clear_former_employee_details",
        "schedule": crontab(hour=2, minute=20),
    },
    "old-chats": {
        "task": "apps.assistant.tasks.clear_old_chats",
        "schedule": crontab(hour=2, minute=35),
    },
}

# Demo businesses (apps/demo). The seed command and the nightly reset refuse to run unless
# DEMO_MODE is on, so a real installation never gets invented data.
DEMO_MODE: bool = env.bool("DEMO_MODE", default=False)
DEMO_EMAIL: str = env("DEMO_EMAIL", default="demo@example.com")
DEMO_PASSWORD: str = env("DEMO_PASSWORD", default="")
DEMO_DAYS: int = env.int("DEMO_DAYS", default=365)
if DEMO_MODE:
    # The demo is put back every night, so visitors always find it as it was.
    CELERY_BEAT_SCHEDULE["demo-reset"] = {
        "task": "apps.demo.tasks.reset_demo",
        "schedule": crontab(hour=3, minute=30),
    }

# How long chat messages are kept before the nightly job removes them (maintainer's decision).
CHAT_KEEP_DAYS: int = env.int("CHAT_KEEP_DAYS", default=90)
if CHAT_KEEP_DAYS < 1:
    # Zero or less would make the nightly job remove today's messages too.
    raise ImproperlyConfigured("CHAT_KEEP_DAYS must be at least 1.")

LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("ur", "Urdu"), ("ar", "Arabic")]
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Karobar ERP <no-reply@localhost>")

# Email goes out through Resend's SMTP relay when RESEND_API_KEY is set (the API key is the SMTP
# password, the user is literally "resend"), so no SDK is needed. Any other SMTP provider works
# through the EMAIL_* variables instead. Without either, mail is printed to the console.
# The business chat. Without a key it stays switched off. Its signing key is separate so it can be
# kept when SECRET_KEY rotates: a new key can't verify the chats signed before it.
GROQ_API_KEY: str = env("GROQ_API_KEY", default="")
GROQ_MODEL: str = env("GROQ_MODEL", default="openai/gpt-oss-120b")
CHAT_SIGNING_KEY: str = env("CHAT_SIGNING_KEY", default="") or SECRET_KEY

RESEND_API_KEY: str = env("RESEND_API_KEY", default="")
if RESEND_API_KEY:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = "smtp.resend.com"
    EMAIL_PORT = 587
    EMAIL_HOST_USER = "resend"
    EMAIL_HOST_PASSWORD = RESEND_API_KEY
    EMAIL_USE_TLS = True
else:
    EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
    EMAIL_HOST = env("EMAIL_HOST", default="localhost")
    EMAIL_PORT = env.int("EMAIL_PORT", default=587)
    EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
    EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_TIMEOUT = 10

# Bot checks on the sign-in, sign-up and password-reset forms. v3 scores every submission
# invisibly; a score under RECAPTCHA_V3_MIN_SCORE asks for the v2 checkbox instead. Leaving the
# keys empty turns the check off (local development and tests); production refuses to start
# without them. The honeypot field works either way.
RECAPTCHA_V3_SITE_KEY: str = env("RECAPTCHA_V3_SITE_KEY", default="")
RECAPTCHA_V3_SECRET_KEY: str = env("RECAPTCHA_V3_SECRET_KEY", default="")
RECAPTCHA_V2_SITE_KEY: str = env("RECAPTCHA_V2_SITE_KEY", default="")
RECAPTCHA_V2_SECRET_KEY: str = env("RECAPTCHA_V2_SECRET_KEY", default="")
RECAPTCHA_V3_MIN_SCORE: float = env.float("RECAPTCHA_V3_MIN_SCORE", default=0.5)

# Sign in with Google and Facebook. A provider shows up on the sign-in page only when both its
# id and secret are set. Redirect URIs to register with each provider:
#   {SITE_URL}/api/accounts/oauth/google/callback/
#   {SITE_URL}/api/accounts/oauth/facebook/callback/
GOOGLE_OAUTH_CLIENT_ID: str = env("GOOGLE_OAUTH_CLIENT_ID", default="")
GOOGLE_OAUTH_CLIENT_SECRET: str = env("GOOGLE_OAUTH_CLIENT_SECRET", default="")
FACEBOOK_SIGN_IN: bool = env.bool("FACEBOOK_SIGN_IN", default=False)
FACEBOOK_APP_ID: str = env("FACEBOOK_APP_ID", default="")
FACEBOOK_APP_SECRET: str = env("FACEBOOK_APP_SECRET", default="")

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "apps.platform.logging.RequestIdFilter"}},
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"}
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "plain",
            "filters": ["request_id"],
        }
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}
