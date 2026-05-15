"""URL configuration for backend project."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core import urls as core_urls

urlpatterns = [
    # Native Django admin, themed via django-unfold.
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
    path("dashboard/misc/", include("misc.urls", namespace="misc")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
