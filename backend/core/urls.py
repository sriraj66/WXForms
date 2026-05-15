"""URL configuration for the core application.

URLs are grouped so they can be mounted under different prefixes from
``backend/urls.py``:

  * ``auth_urlpatterns``      – mounted at ``/`` (register/login/logout)
  * ``api_urlpatterns``       – mounted at ``/api/v1/`` (public endpoints)
  * ``dashboard_urlpatterns`` – mounted at ``/dashboard/`` (everything user-facing)

URL ``name=`` values are unchanged, so existing ``{% url %}`` references
keep resolving.
"""

from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

# Public auth pages — sit at the site root.
auth_urlpatterns = [
    path("", views.landing_view, name="landing"),
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

    # Password reset (Django built-in, themed templates).
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="auth/password_reset.html",
            email_template_name="auth/password_reset_email.txt",
            subject_template_name="auth/password_reset_subject.txt",
            success_url=reverse_lazy("password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(template_name="auth/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="auth/password_reset_confirm.html",
            success_url=reverse_lazy("password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(template_name="auth/password_reset_complete.html"),
        name="password_reset_complete",
    ),
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
    # Change password (Django built-in)
    path(
        "profile/password/",
        auth_views.PasswordChangeView.as_view(
            template_name="auth/password_change.html",
            success_url=reverse_lazy("password_change_done"),
        ),
        name="password_change",
    ),
    path(
        "profile/password/done/",
        auth_views.PasswordChangeDoneView.as_view(template_name="auth/password_change_done.html"),
        name="password_change_done",
    ),
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
    path("templates/<int:pk>/preview/", views.email_template_preview, name="templates_preview"),
    path("templates/<int:pk>/send-test/", views.email_template_send_test, name="templates_send_test"),
    path("templates/preview/new/", views.email_template_preview_unsaved, name="templates_preview_unsaved"),
    # Submissions
    path("submissions/", views.submissions_list, name="submissions_list"),
    path("submissions/<int:pk>/", views.submission_detail, name="submissions_detail"),
    path("submissions/<int:pk>/internals/", views.submission_internals, name="submissions_internals"),
    path("submissions/<int:pk>/purge/", views.submission_purge, name="submissions_purge"),
    path("submissions/bulk-purge/", views.submissions_bulk_purge, name="submissions_bulk_purge"),
    path("submissions/export/", views.submissions_export_csv, name="submissions_export"),
    path("submissions/live/", views.submissions_live_view, name="submissions_live"),
    # Analytics
    path("analytics/", views.analytics_view, name="analytics"),
]

# Backward-compat: a flat list (auth + api at root + dashboard at root) is
# intentionally NOT exported — backend/urls.py composes the prefixes.
urlpatterns: list = []
