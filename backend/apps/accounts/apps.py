from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    label = "accounts"

    def ready(self) -> None:
        from django.contrib.auth.signals import user_logged_in  # noqa: PLC0415

        from .signals import record_last_login  # noqa: PLC0415

        # Swap Django's last_login receiver for one that never waits on a locked row.
        user_logged_in.disconnect(dispatch_uid="update_last_login")
        user_logged_in.connect(record_last_login, dispatch_uid="update_last_login")
