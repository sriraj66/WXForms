"""Views for the misc app."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import SurveyForm
from .models import UserProfile


@login_required
def onboarding_view(request):
    """Multi-step onboarding wizard. Required after registration."""
    from .services import get_app_setting
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    # If onboarding/survey editing is disabled and user has already completed it, send them home.
    if profile.survey_completed and not get_app_setting("edit_survey", True):
        messages.info(request, "Survey editing is currently disabled.")
        return redirect("dashboard")
    if request.method == "POST":
        form = SurveyForm(request.POST, instance=profile)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.survey_completed = True
            obj.save()
            messages.success(request, "Welcome aboard! Your profile is all set.")
            next_url = request.GET.get("next") or "dashboard"
            return redirect(next_url)
        else:
            messages.error(request, "Please review the highlighted fields.")
    else:
        form = SurveyForm(instance=profile)
    return render(request, "misc/onboarding.html", {"form": form, "profile": profile})


# Backwards-compat alias used by the older /survey/ URL.
survey_view = onboarding_view
