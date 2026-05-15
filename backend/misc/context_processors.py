"""Inject misc settings + profile into templates."""

from .models import AppSetting, UserProfile
from .services import get_app_setting


# Bool flags exposed to every template, with safe defaults.
_FLAG_DEFAULTS = {
    "edit_survey": True,
    "user_signup": True,
    "user_login": True,
    "email_service": True,
}


def misc_context(request):
    user = getattr(request, "user", None)
    ctx = {}
    if user and user.is_authenticated:
        try:
            profile, _ = UserProfile.objects.get_or_create(user=user)
        except Exception:
            profile = None
        ctx["misc_profile"] = profile
        ctx["needs_survey"] = bool(profile and not profile.survey_completed)
    # App-wide feature flags
    flags = {}
    for key, default in _FLAG_DEFAULTS.items():
        try:
            flags[key] = bool(get_app_setting(key, default))
        except Exception:
            flags[key] = default
    ctx["app_flags"] = flags
    # Public app settings (lazy)
    try:
        public_settings = {s.key: s.value for s in AppSetting.objects.filter(is_public=True)}
    except Exception:
        public_settings = {}
    ctx["public_settings"] = public_settings
    return ctx
