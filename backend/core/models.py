import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class AccessKey(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="access_keys"
    )
    key = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=100, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    usage_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name or 'Key'} ({self.key[:8]}...)"

    @staticmethod
    def generate_key():
        return uuid.uuid4().hex


class GmailConfig(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="gmail_config"
    )
    sender_email = models.EmailField()
    encrypted_password = models.TextField(help_text="Fernet-encrypted Gmail app password")
    is_verified = models.BooleanField(default=False)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.sender_email} ({'verified' if self.is_verified else 'unverified'})"


class Form(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="forms"
    )
    name = models.CharField(max_length=200)
    access_key = models.ForeignKey(
        AccessKey, on_delete=models.SET_NULL, null=True, blank=True, related_name="forms"
    )
    email_to = models.EmailField(help_text="Where to send form submissions")
    email_template = models.ForeignKey(
        "EmailTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="forms",
        help_text="Template used for this form's notification emails. Falls back to user default.",
    )
    allowed_domains = models.TextField(
        blank=True, default="", help_text="Comma-separated list of allowed domains (empty = all)"
    )
    redirect_url = models.URLField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def get_allowed_domains_list(self):
        if not self.allowed_domains:
            return []
        return [d.strip() for d in self.allowed_domains.split(",") if d.strip()]


FIELD_TYPE_CHOICES = [
    ("text", "Text"),
    ("email", "Email"),
    ("number", "Number"),
    ("textarea", "Textarea"),
    ("checkbox", "Checkbox"),
    ("radio", "Radio"),
    ("select", "Select"),
]


class FormField(models.Model):
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name="fields")
    name = models.CharField(max_length=100)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPE_CHOICES, default="text")
    required = models.BooleanField(default=False)
    placeholder = models.CharField(max_length=200, blank=True, default="")
    default_value = models.CharField(max_length=200, blank=True, default="")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.name} ({self.field_type})"


class EmailTemplate(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="email_templates"
    )
    name = models.CharField(max_length=200, default="Default Template")
    subject = models.CharField(max_length=300, default="New Form Submission - {{form_name}}")
    body_html = models.TextField(
        default=(
            "<h2>New Form Submission</h2>\n"
            "<p><strong>Form:</strong> {{form_name}}</p>\n"
            "<p><strong>Submitted at:</strong> {{submission_time}}</p>\n"
            "<p><strong>IP Address:</strong> {{ip_address}}</p>\n"
            "<hr>\n"
            "{{fields_html}}"
        )
    )
    body_text = models.TextField(
        blank=True,
        default=(
            "New Form Submission\n\n"
            "Form: {{form_name}}\n"
            "Submitted at: {{submission_time}}\n"
            "IP Address: {{ip_address}}\n\n"
            "{{fields_text}}"
        ),
    )
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class Submission(models.Model):
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name="submissions")
    payload_json = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    headers = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    data_deleted = models.BooleanField(default=False)
    data_deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Submission #{self.pk} for {self.form.name}"

    def purge_data(self):
        """Wipe payload + headers but keep the trace row (id, time, IP, form)."""
        self.payload_json = {}
        self.headers = {}
        self.data_deleted = True
        self.data_deleted_at = timezone.now()
        self.save(update_fields=["payload_json", "headers", "data_deleted", "data_deleted_at"])


class EmailLog(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    submission = models.OneToOneField(
        Submission, on_delete=models.CASCADE, related_name="email_log"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True, default="")
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Email for submission #{self.submission_id} - {self.status}"

    def mark_sent(self):
        self.status = self.Status.SENT
        self.sent_at = timezone.now()
        self.save(update_fields=["status", "sent_at"])

    def mark_failed(self, error):
        self.status = self.Status.FAILED
        self.error_message = str(error)
        self.save(update_fields=["status", "error_message"])

class AuditLog(models.Model):
    """Tamper-evident audit trail of sensitive actions."""

    class Action(models.TextChoices):
        FORM_CREATED = "form.created", "Form created"
        FORM_DELETED = "form.deleted", "Form deleted"
        FORM_TOGGLED = "form.toggled", "Form toggled"
        KEY_CREATED = "key.created", "Access key created"
        KEY_REVOKED = "key.revoked", "Access key revoked"
        KEY_REGENERATED = "key.regenerated", "Access key regenerated"
        TEMPLATE_DELETED = "template.deleted", "Email template deleted"
        SUBMISSION_PURGED = "submission.purged", "Submission data purged"
        GMAIL_REMOVED = "gmail.removed", "Gmail config removed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
    )
    action = models.CharField(max_length=64, choices=Action.choices)
    target = models.CharField(max_length=200, blank=True, default="", help_text="Human-readable target reference (e.g. 'Form #4: Contact').")
    target_id = models.PositiveIntegerField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"]), models.Index(fields=["action", "-created_at"])]

    def __str__(self):
        who = self.user.username if self.user_id else "anonymous"
        return f"{who} :: {self.action} :: {self.target or self.target_id or ''}"
