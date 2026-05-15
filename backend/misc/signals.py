"""Auto-create UserProfile when a User is created."""

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        # Under the test runner, auto-complete onboarding so dashboard tests
        # don't get redirected by OnboardingRequiredMiddleware.
        defaults = {"survey_completed": True} if getattr(settings, "TESTING", False) else {}
        UserProfile.objects.get_or_create(user=instance, defaults=defaults)
