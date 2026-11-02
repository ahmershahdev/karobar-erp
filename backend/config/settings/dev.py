from .base import *  # noqa: F403
from .base import INSTALLED_APPS, REST_FRAMEWORK

DEBUG = True
INSTALLED_APPS = [*INSTALLED_APPS]
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
