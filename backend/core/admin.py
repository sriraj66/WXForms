"""Admin configuration for the core application."""

from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.forms import (
    AdminPasswordChangeForm,
    UserChangeForm,
    UserCreationForm,
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


@admin.register(AccessKey)
class AccessKeyAdmin(ModelAdmin):
    list_display = ["name", "user", "key_preview", "is_active", "usage_count", "last_used_at", "created_at"]
    list_filter = ["is_active", "created_at"]
    search_fields = ["name", "key", "user__username"]
    autocomplete_fields = ["user"]
    readonly_fields = ["key", "usage_count", "last_used_at", "created_at"]

    def key_preview(self, obj):
        return f"{obj.key[:8]}..."
    key_preview.short_description = "Key"


@admin.register(GmailConfig)
class GmailConfigAdmin(ModelAdmin):
    list_display = ["user", "sender_email", "is_verified", "is_enabled", "created_at"]
    list_filter = ["is_verified", "is_enabled"]
    search_fields = ["user__username", "sender_email"]
    autocomplete_fields = ["user"]
    readonly_fields = ["created_at", "updated_at"]


class FormFieldInline(TabularInline):
    model = FormField
    extra = 0


@admin.register(Form)
class FormAdmin(ModelAdmin):
    list_display = ["name", "user", "email_to", "is_active", "created_at"]
    list_filter = ["is_active", "created_at"]
    search_fields = ["name", "user__username", "email_to"]
    autocomplete_fields = ["user", "access_key"]
    inlines = [FormFieldInline]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(EmailTemplate)
class EmailTemplateAdmin(ModelAdmin):
    list_display = ["name", "user", "subject", "is_default", "updated_at"]
    list_filter = ["is_default"]
    search_fields = ["name", "user__username", "subject"]
    autocomplete_fields = ["user"]


class EmailLogInline(StackedInline):
    model = EmailLog
    extra = 0
    readonly_fields = ["status", "error_message", "sent_at", "created_at"]


@admin.register(Submission)
class SubmissionAdmin(ModelAdmin):
    list_display = ["id", "form", "ip_address", "email_status", "created_at"]
    list_filter = ["created_at", "form"]
    search_fields = ["ip_address", "form__name"]
    autocomplete_fields = ["form"]
    inlines = [EmailLogInline]
    readonly_fields = ["created_at"]

    def email_status(self, obj):
        try:
            return obj.email_log.status
        except EmailLog.DoesNotExist:
            return "-"
    email_status.short_description = "Email"


@admin.register(EmailLog)
class EmailLogAdmin(ModelAdmin):
    list_display = ["submission", "status", "sent_at", "created_at"]
    list_filter = ["status"]
    readonly_fields = ["created_at"]


@admin.register(AuditLog)
class AuditLogAdmin(ModelAdmin):
    list_display = ["created_at", "user", "action", "target", "ip_address"]
    list_filter = ["action", "created_at"]
    search_fields = ["user__username", "target", "ip_address"]
    readonly_fields = [
        "user", "action", "target", "target_id",
        "ip_address", "user_agent", "metadata", "created_at",
    ]
    ordering = ["-created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# Re-register auth models so they pick up the Unfold styling
# ---------------------------------------------------------------------------
admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass
