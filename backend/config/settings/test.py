from .base import *  # noqa: F403
from .base import MIDDLEWARE, REST_FRAMEWORK

# Argon2 is deliberately slow; tests hash hundreds of passwords.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CELERY_TASK_ALWAYS_EAGER = True
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
    **REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
    "anon": "10000/min",
    "user": "10000/min",
}

MIDDLEWARE = [m for m in MIDDLEWARE if not m.startswith("whitenoise.")]
