from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _seed_defaults(sender, **kwargs):
    if sender.name != "misc":
        return
    from .services import load_default_app_settings
    try:
        load_default_app_settings()
    except Exception:
        # Don't block app startup if the file is malformed or DB is unavailable.
        pass


class MiscConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "misc"
    verbose_name = "App Settings"

    def ready(self):
        from . import signals  # noqa: F401
        post_migrate.connect(_seed_defaults, sender=self)
