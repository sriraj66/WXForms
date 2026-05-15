from django.urls import path

from . import views

app_name = "misc"

urlpatterns = [
    path("onboarding/", views.onboarding_view, name="onboarding"),
    path("survey/", views.survey_view, name="survey"),
]
