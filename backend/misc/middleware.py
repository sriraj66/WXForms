"""Middleware to ensure onboarding is completed before using the dashboard."""

from django.shortcuts import redirect
from django.urls import resolve, reverse


# Paths/url-names that are always allowed without onboarding.
_ALLOWED_NAMES = {
    "misc:onboarding",
    "landing",
    "logout",
    "login",
    "register",
    "profile",
}

_ALLOWED_PREFIXES = (
    "/admin/",
    "/static/",
    "/media/",
    "/api/",
    "/dashboard/misc/onboarding",
)


class OnboardingRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            path = request.path or ""
            if not any(path.startswith(p) for p in _ALLOWED_PREFIXES):
                try:
                    match = resolve(path)
                    name = f"{match.namespace}:{match.url_name}" if match.namespace else match.url_name
                except Exception:
                    name = ""
                if name not in _ALLOWED_NAMES:
                    profile = getattr(user, "misc_profile", None)
                    if profile is not None and not profile.survey_completed:
                        return redirect(reverse("misc:onboarding"))
        return self.get_response(request)
