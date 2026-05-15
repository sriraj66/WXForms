from django.apps import AppConfig


class PlansConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plans"
    # Keep the original DB table prefix / migration history so existing
    # `credits_*` tables stay valid after the directory rename.
    label = "credits"
    verbose_name = "Plans & Credits"

    def ready(self):
        # Ensure signal handlers are registered
        from . import signals  # noqa: F401
