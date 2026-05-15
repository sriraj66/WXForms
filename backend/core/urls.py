"""URL configuration for the core application.

URLs are grouped so they can be mounted under different prefixes from
``backend/urls.py``:

  * ``auth_urlpatterns``      – mounted at ``/`` (register/login/logout)
  * ``api_urlpatterns``       – mounted at ``/api/v1/`` (public endpoints)
  * ``dashboard_urlpatterns`` – mounted at ``/dashboard/`` (everything user-facing)

URL ``name=`` values are unchanged, so existing ``{% url %}`` references
keep resolving.
"""

from django.urls import path

from . import views

# Public auth pages — sit at the site root.
auth_urlpatterns = [
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
]

# Public API.
api_urlpatterns = [
    path("submit/", views.submit_form_api, name="submit_api"),
]

# Authenticated user dashboard area.
dashboard_urlpatterns = [
    # Overview lives at /dashboard/
    path("", views.dashboard_view, name="dashboard"),
    path("profile/", views.profile_view, name="profile"),
    # Access Keys
    path("keys/", views.access_keys_list, name="keys_list"),
    path("keys/create/", views.access_key_create, name="keys_create"),
    path("keys/<int:pk>/revoke/", views.access_key_revoke, name="keys_revoke"),
    path("keys/<int:pk>/regenerate/", views.access_key_regenerate, name="keys_regenerate"),
    # Gmail Config
    path("mail/settings/", views.gmail_config_view, name="gmail_config"),
    # Forms
    path("forms/", views.forms_list, name="forms_list"),
    path("forms/create/", views.form_create, name="forms_create"),
    path("forms/<int:pk>/edit/", views.form_edit, name="forms_edit"),
    path("forms/<int:pk>/delete/", views.form_delete, name="forms_delete"),
    path("forms/<int:pk>/toggle/", views.form_toggle, name="forms_toggle"),
    path("forms/<int:pk>/data/", views.form_data_view, name="forms_data"),
    # Email Templates
    path("templates/", views.email_templates_list, name="templates_list"),
    path("templates/create/", views.email_template_create, name="templates_create"),
    path("templates/<int:pk>/edit/", views.email_template_edit, name="templates_edit"),
    path("templates/<int:pk>/delete/", views.email_template_delete, name="templates_delete"),
    # Submissions
    path("submissions/", views.submissions_list, name="submissions_list"),
    path("submissions/<int:pk>/", views.submission_detail, name="submissions_detail"),
    path("submissions/<int:pk>/internals/", views.submission_internals, name="submissions_internals"),
    path("submissions/export/", views.submissions_export_csv, name="submissions_export"),
    path("submissions/live/", views.submissions_live_view, name="submissions_live"),
    # Analytics
    path("analytics/", views.analytics_view, name="analytics"),
]

# Backward-compat: a flat list (auth + api at root + dashboard at root) is
# intentionally NOT exported — backend/urls.py composes the prefixes.
urlpatterns: list = []
