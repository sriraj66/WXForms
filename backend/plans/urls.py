"""User-facing routes (any authenticated user).

Exposed under the ``/credits/`` URL prefix. Admin / management views
live in ``plans/admin_urls.py`` and mount under ``/manage/``.
"""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.my_credits, name="my_credits"),
]
