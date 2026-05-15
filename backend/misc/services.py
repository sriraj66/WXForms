"""Helpers to access AppSetting/UIConfig values with caching."""

from pathlib import Path
from typing import Any

from django.conf import settings as dj_settings

from .models import AppSetting, UIConfig


def get_app_setting(key: str, default: Any = None) -> Any:
    try:
        s = AppSetting.objects.get(key=key)
    except AppSetting.DoesNotExist:
        return default
    if s.kind == AppSetting.Kind.BOOL:
        return s.value.lower() in ("1", "true", "yes", "on")
    if s.kind == AppSetting.Kind.INT:
        try:
            return int(s.value)
        except (TypeError, ValueError):
            return default
    if s.kind == AppSetting.Kind.JSON:
        import json
        try:
            return json.loads(s.value or "null")
        except json.JSONDecodeError:
            return default
    return s.value


def get_ui_config(slug: str):
    return UIConfig.objects.filter(slug=slug, is_active=True).first()


# ---------------------------------------------------------------------------
# Default settings loader
# ---------------------------------------------------------------------------

# Inferred kind for known keys. Anything else falls back to STRING.
_DEFAULT_KINDS = {
    "edit_survey": AppSetting.Kind.BOOL,
    "user_signup": AppSetting.Kind.BOOL,
    "user_login": AppSetting.Kind.BOOL,
    "email_service": AppSetting.Kind.BOOL,
}

_DEFAULT_DESCRIPTIONS = {
    "edit_survey": "Allow users to edit their onboarding survey from the profile page.",
    "user_signup": "Allow new users to register an account.",
    "user_login": "Allow existing users to log in.",
    "email_service": "Globally enable outbound email delivery for form submissions.",
}


def _default_settings_path() -> Path:
    return Path(dj_settings.BASE_DIR) / "default.settings"


def _parse_default_settings_file(path: Path) -> dict[str, str]:
    """Parse simple key=value lines, ignoring blank lines and `#` comments."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key:
            out[key] = value
    return out


def load_default_app_settings() -> dict[str, str]:
    """Load default.settings into AppSetting rows that don't already exist.

    Existing rows are left untouched (admin-managed values win).
    Returns a dict of newly created {key: value}.
    """
    path = _default_settings_path()
    desired = _parse_default_settings_file(path)
    if not desired:
        return {}

    existing = set(AppSetting.objects.filter(key__in=desired.keys()).values_list("key", flat=True))
    created: dict[str, str] = {}
    for key, value in desired.items():
        if key in existing:
            continue
        AppSetting.objects.create(
            key=key,
            value=value,
            kind=_DEFAULT_KINDS.get(key, AppSetting.Kind.STRING),
            description=_DEFAULT_DESCRIPTIONS.get(key, ""),
            is_public=False,
        )
        created[key] = value
    return created

