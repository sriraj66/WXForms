"""Auto-create credit wallets when users sign up."""

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def initialize_user_credits(sender, instance, created, **kwargs):
    if not created:
        return
    # Lazy import to avoid app-loading order issues
    from .services import get_or_create_balance

    try:
        get_or_create_balance(instance)
    except Exception:
        # Never break user creation because of credit setup; admin can fix later.
        pass
