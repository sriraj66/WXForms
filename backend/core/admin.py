"""Admin configuration for the core application."""

from django.contrib import admin

from .models import (
    AccessKey,
    EmailLog,
    EmailTemplate,
    Form,
    FormField,
    GmailConfig,
    Submission,
)


@admin.register(AccessKey)
class AccessKeyAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "key_preview", "is_active", "usage_count", "last_used_at", "created_at"]
    list_filter = ["is_active", "created_at"]
    search_fields = ["name", "key", "user__username"]
    readonly_fields = ["key", "usage_count", "last_used_at", "created_at"]

    def key_preview(self, obj):
        return f"{obj.key[:8]}..."
    key_preview.short_description = "Key"


@admin.register(GmailConfig)
class GmailConfigAdmin(admin.ModelAdmin):
    list_display = ["user", "sender_email", "is_verified", "is_enabled", "created_at"]
    list_filter = ["is_verified", "is_enabled"]
    search_fields = ["user__username", "sender_email"]
    readonly_fields = ["created_at", "updated_at"]


class FormFieldInline(admin.TabularInline):
    model = FormField
    extra = 0


@admin.register(Form)
class FormAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "email_to", "is_active", "created_at"]
    list_filter = ["is_active", "created_at"]
    search_fields = ["name", "user__username", "email_to"]
    inlines = [FormFieldInline]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "subject", "is_default", "updated_at"]
    list_filter = ["is_default"]
    search_fields = ["name", "user__username", "subject"]


class EmailLogInline(admin.StackedInline):
    model = EmailLog
    extra = 0
    readonly_fields = ["status", "error_message", "sent_at", "created_at"]


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ["id", "form", "ip_address", "email_status", "created_at"]
    list_filter = ["created_at", "form"]
    search_fields = ["ip_address", "form__name"]
    inlines = [EmailLogInline]
    readonly_fields = ["created_at"]

    def email_status(self, obj):
        try:
            return obj.email_log.status
        except EmailLog.DoesNotExist:
            return "-"
    email_status.short_description = "Email"


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ["submission", "status", "sent_at", "created_at"]
    list_filter = ["status"]
    readonly_fields = ["created_at"]