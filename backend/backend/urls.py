"""URL configuration for backend project."""

from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from core import urls as core_urls

urlpatterns = [
    # Native Django admin, themed via django-unfold.
    # Plan / credit / user-balance management lives entirely under /admin/
    # — the previous /manage/ section has been retired.
    path("admin/", admin.site.urls),

    # Public auth pages at the site root.
    path("", include(core_urls.auth_urlpatterns)),

    # Public submission API.
    path("api/v1/", include(core_urls.api_urlpatterns)),

    # Authenticated user dashboard area.
    path("dashboard/", include(core_urls.dashboard_urlpatterns)),
    path(
        "dashboard/credits/",
        include(("plans.urls", "plans"), namespace="credits"),
    ),

    # Root → dashboard.
    path("", RedirectView.as_view(url="/dashboard/", permanent=False)),
]
