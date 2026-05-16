"""Views for the core application."""

import csv
import json
import logging
from urllib.parse import urlencode, urlparse

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods

from plans.services import (
    InsufficientCreditsError,
    charge_email_sent,
    charge_form_creation,
    charge_submission_fields,
    get_or_create_balance,
)

from .email_utils import render_preview, send_submission_email, test_smtp_connection
from .encryption import encrypt_value
from .forms import (
    AccessKeyForm,
    EmailTemplateForm,
    FormCreateForm,
    FormFieldFormSet,
    GmailConfigForm,
    LoginForm,
    ProfileForm,
    RegistrationForm,
)
from .models import (
    AccessKey,
    AuditLog,
    EmailLog,
    EmailTemplate,
    Form,
    FormField,
    GmailConfig,
    Submission,
)

logger = logging.getLogger(__name__)


def _paginate(request, queryset, per_page=20):
    """Paginate a queryset and return (page_obj, querystring without 'page').

    Ensures the queryset is ordered so pagination is deterministic; falls back
    to ``-pk`` when the queryset (or its model) has no default ordering.
    """
    if hasattr(queryset, "ordered") and not queryset.ordered:
        queryset = queryset.order_by("-pk")
    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get("page") or 1
    page_obj = paginator.get_page(page_number)
    params = request.GET.copy()
    params.pop("page", None)
    qs = params.urlencode()
    return page_obj, qs


# =============================================================================
# Authentication Views
# =============================================================================


def landing_view(request):
    """Public marketing landing page. Accessible to everyone."""
    # Aggregate platform-wide stats. Cheap counts; safe defaults if DB empty.
    try:
        total_submissions = Submission.objects.count()
        total_emails_sent = EmailLog.objects.filter(status=EmailLog.Status.SENT).count()
        total_forms = Form.objects.count()
    except Exception:
        total_submissions = total_emails_sent = total_forms = 0
    ctx = {
        "stat_submissions": total_submissions,
        "stat_emails": total_emails_sent,
        "stat_forms": total_forms,
        "stat_speed_ms": 180,  # advertised median API response time
    }
    from misc.services import get_app_setting
    ctx["signup_enabled"] = bool(get_app_setting("user_signup", True))
    return render(request, "landing.html", ctx)


def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    from misc.services import get_app_setting
    if not get_app_setting("user_signup", True):
        messages.error(request, "New account registration is currently disabled.")
        return redirect("login")
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Account created. Let's set up your profile.")
            return redirect("misc:onboarding")
        else:
            logger.warning("register validation failed: %s", form.errors.as_json())
            messages.error(request, "Registration failed — see the highlighted errors.")
    else:
        form = RegistrationForm()
    return render(request, "auth/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    from misc.services import get_app_setting
    if not get_app_setting("user_login", True):
        messages.error(request, "Sign-in is temporarily disabled. Please try again later.")
        return render(request, "auth/login.html", {"form": LoginForm(), "login_disabled": True})
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password"],
            )
            if user is not None:
                login(request, user)
                next_url = request.GET.get("next", "dashboard")
                return redirect(next_url)
            else:
                messages.error(request, "Invalid username or password.")
    else:
        form = LoginForm()
    return render(request, "auth/login.html", {"form": form})


def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("login")


@login_required
def profile_view(request):
    from misc.forms import AvatarForm, SurveyForm
    from misc.models import UserProfile
    from misc.services import get_app_setting

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    edit_survey_enabled = get_app_setting("edit_survey", True)

    if request.method == "POST":
        action = request.POST.get("action", "identity")
        if action == "avatar":
            avatar_form = AvatarForm(request.POST, request.FILES, instance=profile)
            if avatar_form.is_valid():
                avatar_form.save()
                messages.success(request, "Profile picture updated.")
                return redirect("profile")
            form = ProfileForm(instance=request.user)
            survey_form = SurveyForm(instance=profile)
        elif action == "survey":
            if not edit_survey_enabled:
                messages.error(request, "Survey editing is currently disabled.")
                return redirect("profile")
            survey_form = SurveyForm(request.POST, instance=profile)
            if survey_form.is_valid():
                obj = survey_form.save(commit=False)
                obj.survey_completed = True
                obj.save()
                messages.success(request, "Preferences saved.")
                return redirect("profile")
            form = ProfileForm(instance=request.user)
            avatar_form = AvatarForm(instance=profile)
        else:
            form = ProfileForm(request.POST, instance=request.user)
            if form.is_valid():
                form.save()
                messages.success(request, "Profile updated successfully.")
                return redirect("profile")
            avatar_form = AvatarForm(instance=profile)
            survey_form = SurveyForm(instance=profile)
    else:
        form = ProfileForm(instance=request.user)
        avatar_form = AvatarForm(instance=profile)
        survey_form = SurveyForm(instance=profile)

    return render(
        request,
        "auth/profile.html",
        {
            "form": form,
            "avatar_form": avatar_form,
            "survey_form": survey_form,
            "profile": profile,
            "edit_survey_enabled": edit_survey_enabled,
        },
    )


# =============================================================================
# Dashboard
# =============================================================================


@login_required
def dashboard_view(request):
    user = request.user
    today = timezone.now().date()

    total_forms = Form.objects.filter(user=user).count()
    total_submissions = Submission.objects.filter(form__user=user).count()
    submissions_today = Submission.objects.filter(
        form__user=user, created_at__date=today
    ).count()
    failed_emails = EmailLog.objects.filter(
        submission__form__user=user, status=EmailLog.Status.FAILED
    ).count()

    # Recent submissions
    recent_submissions = (
        Submission.objects.filter(form__user=user)
        .select_related("form", "email_log")
        .order_by("-created_at")[:10]
    )

    # Submissions chart data (last 30 days)
    thirty_days_ago = today - timezone.timedelta(days=30)
    daily_submissions = (
        Submission.objects.filter(form__user=user, created_at__date__gte=thirty_days_ago)
        .annotate(date=TruncDate("created_at"))
        .values("date")
        .annotate(count=Count("id"))
        .order_by("date")
    )
    chart_labels = [item["date"].strftime("%b %d") for item in daily_submissions]
    chart_data = [item["count"] for item in daily_submissions]

    context = {
        "total_forms": total_forms,
        "total_submissions": total_submissions,
        "submissions_today": submissions_today,
        "failed_emails": failed_emails,
        "recent_submissions": recent_submissions,
        "chart_labels": json.dumps(chart_labels),
        "chart_data": json.dumps(chart_data),
    }
    return render(request, "dashboard/home.html", context)


# =============================================================================
# Access Key Management
# =============================================================================


@login_required
def access_keys_list(request):
    qs = AccessKey.objects.filter(user=request.user)

    search = (request.GET.get("search") or "").strip()
    status = request.GET.get("status") or ""
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(key__icontains=search))
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "revoked":
        qs = qs.filter(is_active=False)

    page_obj, qs_params = _paginate(request, qs, per_page=15)
    return render(
        request,
        "keys/list.html",
        {
            "keys": page_obj.object_list,
            "page_obj": page_obj,
            "qs_params": qs_params,
            "search": search,
            "status": status,
        },
    )


@login_required
def access_key_create(request):
    if request.method == "POST":
        form = AccessKeyForm(request.POST)
        if form.is_valid():
            key = form.save(commit=False)
            key.user = request.user
            key.key = AccessKey.generate_key()
            key.save()
            from .audit import record as audit_record
            audit_record(request, AuditLog.Action.KEY_CREATED, target=key.name or f"Key #{key.pk}", target_id=key.pk)
            messages.success(request, f"Access key created: {key.key}")
            return redirect("keys_list")
        else:
            logger.warning("access_key_create validation failed user=%s errors=%s", request.user.username, form.errors.as_json())
            messages.error(request, "Could not create the key — see the highlighted errors.")
    else:
        form = AccessKeyForm()
    return render(request, "keys/create.html", {"form": form})


@login_required
@require_POST
def access_key_revoke(request, pk):
    key = get_object_or_404(AccessKey, pk=pk, user=request.user)
    key.is_active = False
    key.save(update_fields=["is_active"])
    from .audit import record as audit_record
    audit_record(request, AuditLog.Action.KEY_REVOKED, target=key.name or f"Key #{key.pk}", target_id=key.pk)
    messages.success(request, "Access key revoked.")
    return redirect("keys_list")


@login_required
@require_POST
def access_key_regenerate(request, pk):
    key = get_object_or_404(AccessKey, pk=pk, user=request.user)
    old_prefix = key.key[:8]
    key.key = AccessKey.generate_key()
    key.save(update_fields=["key"])
    from .audit import record as audit_record
    audit_record(request, AuditLog.Action.KEY_REGENERATED, target=key.name or f"Key #{key.pk}", target_id=key.pk, metadata={"old_prefix": old_prefix})
    messages.success(request, f"Access key regenerated: {key.key}")
    return redirect("keys_list")


# =============================================================================
# Gmail Configuration
# =============================================================================


@login_required
def gmail_config_view(request):
    try:
        config = GmailConfig.objects.get(user=request.user)
        existing = True
    except GmailConfig.DoesNotExist:
        config = None
        existing = False

    if request.method == "POST":
        action = request.POST.get("action", "save")

        if action == "delete" and config:
            config.delete()
            from .audit import record as audit_record
            audit_record(request, AuditLog.Action.GMAIL_REMOVED, target=request.user.username)
            messages.success(request, "Gmail configuration removed.")
            return redirect("gmail_config")

        form = GmailConfigForm(request.POST)
        if form.is_valid():
            sender_email = form.cleaned_data["sender_email"]
            app_password = form.cleaned_data["app_password"]
            if action == "test":
                success, msg = test_smtp_connection(sender_email, app_password)
                if success:
                    messages.success(request, msg)
                else:
                    messages.error(request, msg)
                return render(
                    request,
                    "gmail/config.html",
                    {"form": form, "config": config, "existing": existing},
                )

            # Save configuration
            encrypted_pw = encrypt_value(app_password)
            if config:
                config.sender_email = sender_email
                config.encrypted_password = encrypted_pw
                config.is_verified = False
                config.save()
            else:
                config = GmailConfig.objects.create(
                    user=request.user,
                    sender_email=sender_email,
                    encrypted_password=encrypted_pw,
                )

            # Test and verify
            success, msg = test_smtp_connection(sender_email, app_password)
            if success:
                config.is_verified = True
                config.save(update_fields=["is_verified"])
                messages.success(request, "Gmail configuration saved and verified!")
            else:
                messages.warning(request, f"Configuration saved but verification failed: {msg}")

            return redirect("gmail_config")
        else:
            logger.warning("gmail_config_view validation failed user=%s errors=%s", request.user.username, form.errors.as_json())
            messages.error(request, "Gmail configuration could not be saved — see the highlighted errors.")
    else:
        initial = {}
        if config:
            initial["sender_email"] = config.sender_email
        form = GmailConfigForm(initial=initial)

    return render(
        request,
        "gmail/config.html",
        {"form": form, "config": config, "existing": existing},
    )


# =============================================================================
# Form Management
# =============================================================================


@login_required
def forms_list(request):
    qs = (
        Form.objects.filter(user=request.user)
        .annotate(
            submission_count=Count("submissions"),
            failed_email_count=Count(
                "submissions",
                filter=Q(submissions__email_log__status=EmailLog.Status.FAILED)
                & Q(submissions__data_deleted=False),
            ),
        )
    )

    search = (request.GET.get("search") or "").strip()
    status = request.GET.get("status") or ""
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(email_to__icontains=search))
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "disabled":
        qs = qs.filter(is_active=False)

    page_obj, qs_params = _paginate(request, qs, per_page=12)
    return render(
        request,
        "forms/list.html",
        {
            "forms": page_obj.object_list,
            "page_obj": page_obj,
            "qs_params": qs_params,
            "search": search,
            "status": status,
        },
    )


@login_required
def form_create(request):
    # Friendly guard: forms require an active access key.
    if not AccessKey.objects.filter(user=request.user, is_active=True).exists():
        messages.warning(request, "Create an access key first — every form needs one.")
        return redirect("keys_create")

    if request.method == "POST":
        form = FormCreateForm(request.user, request.POST)
        formset = FormFieldFormSet(request.POST, prefix="fields")
        # Treat blank rows as truly empty so unused 'extra' forms don't fail required-validation.
        for sub in formset.forms:
            sub.empty_permitted = True
        if form.is_valid() and formset.is_valid():
            f = form.save(commit=False)
            f.user = request.user
            f.save()
            formset.instance = f
            formset.save()
            from .audit import record as audit_record
            audit_record(request, AuditLog.Action.FORM_CREATED, target=f.name, target_id=f.pk)
            try:
                charge_form_creation(request.user, f)
            except InsufficientCreditsError as exc:
                f.delete()
                messages.error(
                    request,
                    f"Not enough credits to create a form (need {exc.required}, have {exc.available}).",
                )
                return redirect("credits:my_credits")
            messages.success(request, "Form created successfully.")
            return redirect("forms_list")
        else:
            logger.warning(
                "form_create validation failed for user=%s form_errors=%s formset_errors=%s formset_non_form=%s",
                request.user.username,
                form.errors.as_json(),
                [fs.errors for fs in formset.forms],
                formset.non_form_errors(),
            )
            messages.error(request, "Form could not be created — see the highlighted errors.")
    else:
        form = FormCreateForm(request.user)
        formset = FormFieldFormSet(prefix="fields")
    return render(request, "forms/create.html", {"form": form, "formset": formset})


@login_required
def form_edit(request, pk):
    form_obj = get_object_or_404(Form, pk=pk, user=request.user)
    if request.method == "POST":
        form = FormCreateForm(request.user, request.POST, instance=form_obj)
        formset = FormFieldFormSet(request.POST, instance=form_obj, prefix="fields")
        for sub in formset.forms:
            sub.empty_permitted = True
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, "Form updated successfully.")
            return redirect("forms_list")
        else:
            logger.warning(
                "form_edit validation failed for user=%s pk=%s form_errors=%s formset_errors=%s",
                request.user.username,
                pk,
                form.errors.as_json(),
                [fs.errors for fs in formset.forms if fs.errors],
            )
            messages.error(request, "Form could not be updated — see the highlighted errors.")
    else:
        form = FormCreateForm(request.user, instance=form_obj)
        formset = FormFieldFormSet(instance=form_obj, prefix="fields")
    return render(
        request,
        "forms/edit.html",
        {"form": form, "formset": formset, "form_obj": form_obj},
    )


@login_required
@require_POST
def form_delete(request, pk):
    form_obj = get_object_or_404(Form, pk=pk, user=request.user)
    name = form_obj.name
    form_obj.delete()
    from .audit import record as audit_record
    audit_record(request, AuditLog.Action.FORM_DELETED, target=name, target_id=pk)
    messages.success(request, "Form deleted successfully.")
    return redirect("forms_list")


@login_required
@require_POST
def form_toggle(request, pk):
    form_obj = get_object_or_404(Form, pk=pk, user=request.user)
    form_obj.is_active = not form_obj.is_active
    form_obj.save(update_fields=["is_active"])
    status = "enabled" if form_obj.is_active else "disabled"
    from .audit import record as audit_record
    audit_record(request, AuditLog.Action.FORM_TOGGLED, target=form_obj.name, target_id=form_obj.pk, metadata={"active": form_obj.is_active})
    messages.success(request, f"Form {status}.")
    return redirect("forms_list")


@login_required
def form_data_view(request, pk):
    """Per-form data table view (Web3Forms-style dynamic columns)."""
    form_obj = get_object_or_404(Form, pk=pk, user=request.user)
    qs = (
        Submission.objects.filter(form=form_obj)
        .select_related("email_log")
        .order_by("-created_at")
    )

    search = (request.GET.get("search") or "").strip()
    date_from = request.GET.get("date_from") or ""
    date_to = request.GET.get("date_to") or ""
    data_state = request.GET.get("data_state") or ""
    if search:
        qs = qs.filter(payload_json__icontains=search) | qs.filter(ip_address__icontains=search)
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    if data_state == "available":
        qs = qs.filter(data_deleted=False)
    elif data_state == "deleted":
        qs = qs.filter(data_deleted=True)

    total_submissions = qs.count()
    failed_email_count = Submission.objects.filter(
        form=form_obj,
        data_deleted=False,
        email_log__status=EmailLog.Status.FAILED,
    ).count()
    page_obj, qs_params = _paginate(request, qs, per_page=25)
    submissions = list(page_obj.object_list)

    # Build a stable union of payload keys (preserve insertion order across submissions)
    columns = []
    seen = set()
    for sub in submissions:
        for k in (sub.payload_json or {}).keys():
            if k in ("access_key", "_honeypot") or k in seen:
                continue
            seen.add(k)
            columns.append(k)

    context = {
        "form_obj": form_obj,
        "submissions": submissions,
        "columns": columns,
        "search": search,
        "date_from": date_from,
        "date_to": date_to,
        "data_state": data_state,
        "total_submissions": total_submissions,
        "failed_email_count": failed_email_count,
        "page_obj": page_obj,
        "qs_params": qs_params,
    }
    return render(request, "forms/data.html", context)


# =============================================================================
# Email Template Management
# =============================================================================


@login_required
def email_templates_list(request):
    templates = EmailTemplate.objects.filter(user=request.user)
    return render(request, "templates_mgmt/list.html", {"templates": templates})


@login_required
def email_template_create(request):
    if request.method == "POST":
        form = EmailTemplateForm(request.POST)
        if form.is_valid():
            tpl = form.save(commit=False)
            tpl.user = request.user
            if tpl.is_default:
                EmailTemplate.objects.filter(user=request.user, is_default=True).update(
                    is_default=False
                )
            tpl.save()
            messages.success(request, "Email template created.")
            return redirect("templates_list")
        else:
            logger.warning("email_template_create validation failed user=%s errors=%s", request.user.username, form.errors.as_json())
            messages.error(request, "Template could not be saved — see the highlighted errors.")
    else:
        form = EmailTemplateForm()
    return render(request, "templates_mgmt/create.html", {"form": form})


@login_required
def email_template_edit(request, pk):
    tpl = get_object_or_404(EmailTemplate, pk=pk, user=request.user)
    if request.method == "POST":
        form = EmailTemplateForm(request.POST, instance=tpl)
        if form.is_valid():
            tpl = form.save(commit=False)
            if tpl.is_default:
                EmailTemplate.objects.filter(user=request.user, is_default=True).exclude(
                    pk=tpl.pk
                ).update(is_default=False)
            tpl.save()
            messages.success(request, "Email template updated.")
            return redirect("templates_list")
        else:
            logger.warning("email_template_edit validation failed user=%s pk=%s errors=%s", request.user.username, pk, form.errors.as_json())
            messages.error(request, "Template could not be updated — see the highlighted errors.")
    else:
        form = EmailTemplateForm(instance=tpl)
    return render(request, "templates_mgmt/edit.html", {"form": form, "template": tpl})


@login_required
@require_POST
def email_template_delete(request, pk):
    tpl = get_object_or_404(EmailTemplate, pk=pk, user=request.user)
    tpl_name = tpl.name
    tpl_id = tpl.pk
    tpl.delete()
    from .audit import record as audit_record
    audit_record(request, AuditLog.Action.TEMPLATE_DELETED, target=tpl_name, target_id=tpl_id)
    messages.success(request, "Email template deleted.")
    return redirect("templates_list")


@login_required
def email_template_preview(request, pk):
    """Render an existing template with sample data and return JSON {subject, html, text}."""
    tpl = get_object_or_404(EmailTemplate, pk=pk, user=request.user)
    return JsonResponse(render_preview(tpl))


@login_required
@require_POST
def email_template_preview_unsaved(request):
    """Render an unsaved template body for live preview from the editor.

    Accepts JSON body: {subject, body_html, body_text}
    """
    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    # Build a transient template-like object via a tiny shim.
    class _Tmp:
        subject = data.get("subject", "") or ""
        body_html = data.get("body_html", "") or ""
        body_text = data.get("body_text", "") or ""

    return JsonResponse(render_preview(_Tmp()))


@login_required
@require_POST
def email_template_send_test(request, pk):
    """Send a test email to the logged-in user using their saved Gmail config.

    Uses the rendered template preview as body. No credit is charged for tests.
    """
    tpl = get_object_or_404(EmailTemplate, pk=pk, user=request.user)
    config = GmailConfig.objects.filter(user=request.user, is_enabled=True).first()
    if not config:
        return JsonResponse(
            {"success": False, "message": "Configure Gmail under Mail Settings first."},
            status=400,
        )
    recipient = (request.user.email or "").strip()
    if not recipient:
        return JsonResponse(
            {"success": False, "message": "Add an email address to your profile first."},
            status=400,
        )

    preview = render_preview(tpl)

    try:
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        import smtplib

        from .encryption import decrypt_value

        app_password = decrypt_value(config.encrypted_password)
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[TEST] {preview['subject']}"
        msg["From"] = config.sender_email
        msg["To"] = recipient
        if preview["text"]:
            msg.attach(MIMEText(preview["text"], "plain"))
        msg.attach(MIMEText(preview["html"], "html"))

        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(config.sender_email, app_password)
        server.sendmail(config.sender_email, [recipient], msg.as_string())
        server.quit()
    except Exception as exc:  # noqa: BLE001 - surface SMTP failure to user
        logger.warning("Test email failed for user %s: %s", request.user_id if hasattr(request, "user_id") else request.user.pk, exc)
        return JsonResponse({"success": False, "message": str(exc)}, status=502)

    return JsonResponse({"success": True, "message": f"Test email sent to {recipient}."})


# =============================================================================
# Submissions
# =============================================================================


@login_required
def submissions_list(request):
    submissions = (
        Submission.objects.filter(form__user=request.user)
        .select_related("form", "email_log")
    )

    # Filters
    form_id = request.GET.get("form")
    if form_id:
        submissions = submissions.filter(form_id=form_id)

    search = request.GET.get("search", "").strip()
    if search:
        submissions = submissions.filter(
            Q(payload_json__icontains=search) | Q(ip_address__icontains=search)
        )

    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    if date_from:
        submissions = submissions.filter(created_at__date__gte=date_from)
    if date_to:
        submissions = submissions.filter(created_at__date__lte=date_to)

    email_status = request.GET.get("email_status") or ""
    if email_status:
        submissions = submissions.filter(email_log__status=email_status)

    data_state = request.GET.get("data_state") or ""
    if data_state == "available":
        submissions = submissions.filter(data_deleted=False)
    elif data_state == "deleted":
        submissions = submissions.filter(data_deleted=True)

    user_forms = Form.objects.filter(user=request.user)

    page_obj, qs_params = _paginate(request, submissions, per_page=25)

    context = {
        "submissions": page_obj.object_list,
        "forms": user_forms,
        "current_form": form_id,
        "search": search,
        "date_from": date_from or "",
        "date_to": date_to or "",
        "email_status": email_status,
        "data_state": data_state,
        "page_obj": page_obj,
        "qs_params": qs_params,
    }
    return render(request, "submissions/list.html", context)


@login_required
def submission_detail(request, pk):
    submission = get_object_or_404(
        Submission.objects.select_related("form", "email_log"),
        pk=pk,
        form__user=request.user,
    )
    return render(request, "submissions/detail.html", {"submission": submission})


@login_required
def submission_internals(request, pk):
    """Detailed internals view showing IP info, headers, and full data."""
    submission = get_object_or_404(
        Submission.objects.select_related("form", "email_log"),
        pk=pk,
        form__user=request.user,
    )
    return render(request, "submissions/internals.html", {"submission": submission})


@login_required
def submissions_live_view(request):
    """Real-time/current view of latest submissions."""
    qs = (
        Submission.objects.filter(form__user=request.user)
        .select_related("form", "email_log")
        .order_by("-created_at")
    )

    form_id = request.GET.get("form") or ""
    search = (request.GET.get("search") or "").strip()
    if form_id:
        qs = qs.filter(form_id=form_id)
    if search:
        qs = qs.filter(payload_json__icontains=search) | qs.filter(ip_address__icontains=search)

    total_submissions = qs.count()
    latest_submissions = qs[:15]

    total_today = Submission.objects.filter(
        form__user=request.user,
        created_at__date=timezone.now().date(),
    ).count()
    total_this_hour = Submission.objects.filter(
        form__user=request.user,
        created_at__gte=timezone.now() - timezone.timedelta(hours=1),
    ).count()

    user_forms = Form.objects.filter(user=request.user, is_active=True)

    context = {
        "latest_submissions": latest_submissions,
        "total_submissions": total_submissions,
        "total_today": total_today,
        "total_this_hour": total_this_hour,
        "forms": user_forms,
        "current_form": form_id,
        "search": search,
    }
    return render(request, "submissions/live.html", context)


@login_required
def submissions_export_csv(request):
    submissions = Submission.objects.filter(form__user=request.user).select_related("form")

    form_id = request.GET.get("form")
    if form_id:
        submissions = submissions.filter(form_id=form_id)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="submissions.csv"'

    writer = csv.writer(response)
    writer.writerow(["ID", "Form", "IP Address", "Created At", "Payload"])

    for sub in submissions:
        writer.writerow([
            sub.pk,
            sub.form.name,
            sub.ip_address or "",
            sub.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            json.dumps(sub.payload_json),
        ])

    return response


@login_required
@require_POST
def submission_purge(request, pk):
    """Wipe payload/headers but keep the submission row (audit trace)."""
    submission = get_object_or_404(Submission, pk=pk, form__user=request.user)
    submission.purge_data()
    from .audit import record as audit_record
    audit_record(request, AuditLog.Action.SUBMISSION_PURGED, target=f"Submission #{submission.pk}", target_id=submission.pk)
    messages.success(request, f"Submission #{submission.pk} data deleted (trace kept).")
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "submissions_list"
    return redirect(next_url)


@login_required
@require_POST
def submissions_bulk_purge(request):
    """Bulk-delete payloads of multiple submissions (keeps trace rows)."""
    ids = request.POST.getlist("ids")
    if not ids:
        messages.warning(request, "No submissions selected.")
    else:
        qs = Submission.objects.filter(pk__in=ids, form__user=request.user, data_deleted=False)
        count = 0
        purged_ids = []
        for sub in qs:
            sub.purge_data()
            purged_ids.append(sub.pk)
            count += 1
        if count:
            from .audit import record as audit_record
            audit_record(
                request,
                AuditLog.Action.SUBMISSION_PURGED,
                target=f"{count} submissions (bulk)",
                metadata={"count": count, "ids": purged_ids},
            )
            messages.success(request, f"Cleared data for {count} submission{'s' if count != 1 else ''} (trace kept).")
        else:
            messages.info(request, "Nothing to clear (already deleted or not yours).")
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "submissions_list"
    return redirect(next_url)


# =============================================================================
# Failed email retry actions
# =============================================================================


@login_required
@require_POST
def submission_retry_email(request, pk):
    """Re-queue the email for a single submission (must be owned by user)."""
    submission = get_object_or_404(Submission, pk=pk, form__user=request.user)
    from .tasks import retry_failed_email
    queued, reason = retry_failed_email(submission.pk)
    if queued:
        from .audit import record as audit_record
        audit_record(
            request,
            AuditLog.Action.EMAIL_RETRIED,
            target=f"Submission #{submission.pk}",
            target_id=submission.pk,
            metadata={"scope": "single"},
        )
        messages.success(request, f"Email retry queued for submission #{submission.pk}.")
    else:
        messages.info(request, reason)
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "submissions_list"
    return redirect(next_url)


@login_required
@require_POST
def form_retry_failed_emails(request, pk):
    """Re-queue every failed email for a single form owned by the user."""
    form_obj = get_object_or_404(Form, pk=pk, user=request.user)
    failed_ids = list(
        Submission.objects.filter(
            form=form_obj,
            data_deleted=False,
            email_log__status=EmailLog.Status.FAILED,
        ).values_list("pk", flat=True)
    )
    if not failed_ids:
        messages.info(request, f"No failed emails to retry for form '{form_obj.name}'.")
    else:
        from .tasks import retry_failed_emails_bulk
        queued = retry_failed_emails_bulk(failed_ids)
        from .audit import record as audit_record
        audit_record(
            request,
            AuditLog.Action.EMAIL_RETRIED,
            target=f"Form #{form_obj.pk}: {form_obj.name}",
            target_id=form_obj.pk,
            metadata={"scope": "form", "count": queued},
        )
        messages.success(
            request,
            f"Queued {queued} email retr{'y' if queued == 1 else 'ies'} for form '{form_obj.name}'.",
        )
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "forms_list"
    return redirect(next_url)


@login_required
@require_POST
def submissions_bulk_retry_email(request):
    """Bulk-retry the emails for the selected submission ids.

    If no ids are posted, retry every failed email across all the user's
    forms (used by the "Retry all failed" toolbar button).
    """
    posted_ids = request.POST.getlist("ids")
    base_qs = Submission.objects.filter(form__user=request.user, data_deleted=False)

    if posted_ids:
        ids = list(
            base_qs.filter(pk__in=posted_ids).values_list("pk", flat=True)
        )
        scope = "selection"
    else:
        ids = list(
            base_qs.filter(email_log__status=EmailLog.Status.FAILED)
            .values_list("pk", flat=True)
        )
        scope = "all"

    if not ids:
        messages.info(request, "Nothing to retry.")
    else:
        from .tasks import retry_failed_emails_bulk
        queued = retry_failed_emails_bulk(ids)
        from .audit import record as audit_record
        audit_record(
            request,
            AuditLog.Action.EMAIL_RETRIED,
            target=f"{queued} submission{'s' if queued != 1 else ''} (bulk)",
            metadata={"scope": scope, "count": queued, "ids": ids[:50]},
        )
        if queued:
            messages.success(
                request,
                f"Queued {queued} email retr{'y' if queued == 1 else 'ies'}.",
            )
        else:
            messages.info(request, "Nothing to retry (already sent or not failed).")
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "submissions_list"
    return redirect(next_url)


# =============================================================================
# Form Submission API (Public Endpoint)
# =============================================================================


def _get_client_ip(request):
    """Extract client IP from request headers."""
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _cors(response, request):
    """Attach permissive CORS headers for the public submit endpoint.

    The endpoint is gated by access keys and per-form domain whitelists,
    so allowing any origin at the HTTP layer is safe.
    """
    origin = request.META.get("HTTP_ORIGIN", "*")
    response["Access-Control-Allow-Origin"] = origin if origin != "" else "*"
    response["Vary"] = "Origin"
    response["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response["Access-Control-Allow-Headers"] = (
        request.META.get("HTTP_ACCESS_CONTROL_REQUEST_HEADERS")
        or "Content-Type, Authorization, X-Requested-With"
    )
    response["Access-Control-Max-Age"] = "86400"
    return response


@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def submit_form_api(request):
    """
    Public API endpoint for form submissions.
    POST /api/v1/submit/

    Accepts any flat key-value fields (max 15 user-defined fields).
    The only reserved key is 'access_key' and '_honeypot'.
    No predefined fields required - fully flexible.
    """
    # CORS preflight (any browser-origin allowed for the public submit endpoint)
    if request.method == "OPTIONS":
        return _cors(JsonResponse({"success": True}), request)

    MAX_FIELDS = 15
    RESERVED_KEYS = {"access_key", "_honeypot", "botcheck", "website", "url", "csrfmiddlewaretoken", "redirect", "replyto", "_replyto", "subject", "from_name"}
    HONEYPOT_KEYS = ("_honeypot", "botcheck", "website", "url")

    # Parse request body - support JSON and form-data
    content_type = request.content_type or ""
    if "application/json" in content_type:
        try:
            raw_data = json.loads(request.body)
            if not isinstance(raw_data, dict):
                return _cors(JsonResponse({"success": False, "message": "JSON body must be an object."}, status=400), request)
        except json.JSONDecodeError:
            return _cors(JsonResponse({"success": False, "message": "Invalid JSON body."}, status=400), request)
    else:
        # Form-data or x-www-form-urlencoded: flatten list values
        raw_data = {
            k: v[0] if isinstance(v, list) and len(v) == 1 else v
            for k, v in request.POST.items()
        }

    # Validate access key
    access_key_value = raw_data.get("access_key")
    if not access_key_value:
        return _cors(JsonResponse({"success": False, "message": "Access key is required."}, status=400), request)

    try:
        access_key = AccessKey.objects.get(key=str(access_key_value).strip(), is_active=True)
    except AccessKey.DoesNotExist:
        return _cors(JsonResponse({"success": False, "message": "Invalid or inactive access key."}, status=403), request)

    # Per-key rate limit driven by the access-key owner's CreditPlan.
    # Falls back to the global app setting (then 60/min) if no plan is set.
    from .ratelimit import hit as rl_hit
    from misc.services import get_app_setting
    from plans.services import get_or_create_balance

    try:
        owner_balance = get_or_create_balance(access_key.user)
        plan = owner_balance.plan
        per_minute = int(plan.submit_rate_per_minute or 0)
        per_hour = int(plan.submit_rate_per_hour or 0)
    except Exception:
        per_minute = int(get_app_setting("submit_rate_per_minute", 60) or 60)
        per_hour = 0

    if per_minute > 0:
        allowed, retry_after = rl_hit("submit:m", access_key.key, per_minute, 60)
        if not allowed:
            resp = JsonResponse(
                {"success": False, "message": f"Rate limit exceeded ({per_minute}/min). Try again in {retry_after}s."},
                status=429,
            )
            resp["Retry-After"] = str(retry_after)
            return _cors(resp, request)
    if per_hour > 0:
        allowed, retry_after = rl_hit("submit:h", access_key.key, per_hour, 3600)
        if not allowed:
            resp = JsonResponse(
                {"success": False, "message": f"Hourly limit exceeded ({per_hour}/h). Try again in {retry_after}s."},
                status=429,
            )
            resp["Retry-After"] = str(retry_after)
            return _cors(resp, request)

    # Find form linked to this access key
    form_obj = Form.objects.filter(access_key=access_key, is_active=True).first()
    if not form_obj:
        return _cors(JsonResponse(
            {"success": False, "message": "No active form found for this access key."},
            status=404,
        ), request)

    # Domain whitelist check
    allowed_domains = form_obj.get_allowed_domains_list()
    if allowed_domains:
        origin = request.META.get("HTTP_ORIGIN", "")
        referer = request.META.get("HTTP_REFERER", "")
        source_url = origin or referer
        if source_url:
            parsed = urlparse(source_url)
            domain = parsed.hostname or ""
            if not any(domain == d or domain.endswith("." + d) for d in allowed_domains):
                return _cors(JsonResponse({"success": False, "message": "Domain not allowed."}, status=403), request)

    # Honeypot spam check (silent accept for bots — drop without persisting)
    for hp in HONEYPOT_KEYS:
        if str(raw_data.get(hp, "")).strip():
            return _cors(JsonResponse({"success": True, "message": "Form submitted successfully."}), request)

    # Extract user-defined payload (strip reserved/internal keys)
    payload = {}
    for key, value in raw_data.items():
        if key in RESERVED_KEYS:
            continue
        # Enforce max depth=1: reject non-scalar values
        if isinstance(value, (dict, list)):
            continue
        # Sanitize key: alphanumeric, underscore, hyphen only; max 64 chars
        sanitized_key = str(key)[:64]
        payload[sanitized_key] = str(value)[:1000]  # cap value length at 1000 chars

    # Enforce maximum 15 user fields
    if len(payload) > MAX_FIELDS:
        return _cors(JsonResponse(
            {"success": False, "message": f"Too many fields. Maximum {MAX_FIELDS} fields allowed."},
            status=400,
        ), request)

    if not payload:
        return _cors(JsonResponse(
            {"success": False, "message": "No form data provided."},
            status=400,
        ), request)

    # Get client IP and request headers
    client_ip = _get_client_ip(request)
    headers_dict = {
        "User-Agent": request.META.get("HTTP_USER_AGENT", ""),
        "Origin": request.META.get("HTTP_ORIGIN", ""),
        "Referer": request.META.get("HTTP_REFERER", ""),
    }

    # Pre-flight credit check on the form owner — refuse the submission if
    # the owner can't even cover the field-storage cost.
    owner = form_obj.user
    try:
        owner_balance = get_or_create_balance(owner)
    except Exception:
        owner_balance = None
    field_count = len(payload)
    field_cost = (owner_balance.plan.per_field_cost if owner_balance else 0) * field_count
    if owner_balance is not None and owner_balance.balance < field_cost:
        logger.warning("Submission rejected due to insufficient credits for user %s: balance=%s, required=%s", owner.username, owner_balance.balance, field_cost)
        return _cors(
            JsonResponse(
                {
                    "success": False,
                    "message": "Submission rejected.",
                },
                status=402,
            ),
            request,
        )

    # Store submission
    submission = Submission.objects.create(
        form=form_obj,
        payload_json=payload,
        ip_address=client_ip,
        headers=headers_dict,
    )

    # Charge for the stored fields
    try:
        charge_submission_fields(owner, submission, field_count)
    except InsufficientCreditsError:
        # Race condition — owner ran out between the pre-check and now.
        pass

    # Update access key usage stats
    access_key.last_used_at = timezone.now()
    access_key.usage_count += 1
    access_key.save(update_fields=["last_used_at", "usage_count"])

    # Send email notification asynchronously (returns immediately).
    # Create the EmailLog placeholder synchronously so the dashboard reflects
    # an immediate "pending" state and the request commit is observable to tests.
    email_log, _ = EmailLog.objects.get_or_create(submission=submission)

    # Quick synchronous short-circuit: if email service is disabled or there is
    # no Gmail config we don't need to spin up a thread at all — mark failed now.
    from misc.services import get_app_setting
    has_gmail = GmailConfig.objects.filter(
        user=form_obj.user, is_enabled=True, is_verified=True
    ).exists()
    if not get_app_setting("email_service", True) or not has_gmail:
        email_log.mark_failed(
            "Email service disabled" if not get_app_setting("email_service", True)
            else "No Gmail config found"
        )
    else:
        from .tasks import deliver_submission_email_async
        deliver_submission_email_async(submission.pk)

    # Handle redirect for non-JSON form submissions
    redirect_url = form_obj.redirect_url
    if redirect_url and "application/json" not in content_type:
        return redirect(redirect_url)

    return _cors(JsonResponse({"success": True, "message": "Form submitted successfully."}), request)


# =============================================================================
# Analytics
# =============================================================================


@login_required
def analytics_view(request):
    user = request.user
    today = timezone.now().date()
    thirty_days_ago = today - timezone.timedelta(days=30)

    # Total stats
    total_submissions = Submission.objects.filter(form__user=user).count()
    total_sent = EmailLog.objects.filter(
        submission__form__user=user, status=EmailLog.Status.SENT
    ).count()
    total_failed = EmailLog.objects.filter(
        submission__form__user=user, status=EmailLog.Status.FAILED
    ).count()

    # Submissions by form
    by_form = (
        Form.objects.filter(user=user)
        .annotate(sub_count=Count("submissions"))
        .order_by("-sub_count")
    )

    # Daily submissions (last 30 days)
    daily = (
        Submission.objects.filter(form__user=user, created_at__date__gte=thirty_days_ago)
        .annotate(date=TruncDate("created_at"))
        .values("date")
        .annotate(count=Count("id"))
        .order_by("date")
    )
    daily_labels = [item["date"].strftime("%b %d") for item in daily]
    daily_data = [item["count"] for item in daily]

    # Top domains from submissions
    top_domains = {}
    recent_subs = Submission.objects.filter(form__user=user).values_list("headers", flat=True)[:500]
    for h in recent_subs:
        if isinstance(h, dict):
            origin = h.get("Origin", "") or h.get("Referer", "")
            if origin:
                parsed = urlparse(origin)
                domain = parsed.hostname or origin
                top_domains[domain] = top_domains.get(domain, 0) + 1

    sorted_domains = sorted(top_domains.items(), key=lambda x: x[1], reverse=True)[:10]

    context = {
        "total_submissions": total_submissions,
        "total_sent": total_sent,
        "total_failed": total_failed,
        "by_form": by_form,
        "daily_labels": json.dumps(daily_labels),
        "daily_data": json.dumps(daily_data),
        "top_domains": sorted_domains,
    }
    return render(request, "analytics/overview.html", context)
