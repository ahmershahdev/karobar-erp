from django.apps import AppConfig


class AccountingConfig(AppConfig):
    name = "apps.accounting"
    label = "accounting"

    def ready(self) -> None:
        from . import receivers  # noqa: F401, PLC0415
