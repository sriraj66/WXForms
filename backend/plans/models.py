"""Credit system models.

Designed to be flexible and scalable. The pricing of every chargeable
operation lives in `CreditPlan`, so admins can change the rules without
deploying code. Future plans (e.g. paid tiers) just add new `CreditPlan`
rows and assign them to users.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class CreditPlan(models.Model):
    """A configurable pricing tier (Free, Pro, Enterprise, etc.).

    All consumption rules are stored here so they can be tweaked from the
    admin panel.  A plan flagged `is_default=True` is auto-assigned to
    new users.
    """

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True, default="")

    # Monthly free credits granted on signup / monthly reset
    monthly_credits = models.PositiveIntegerField(
        default=10000,
        help_text="Free credits granted at the start of each billing cycle.",
    )

    # Pricing rules (all expressed in credits)
    form_creation_cost = models.PositiveIntegerField(
        default=10, help_text="Credits charged when a user creates a new form."
    )
    per_field_cost = models.PositiveIntegerField(
        default=2,
        help_text="Credits charged per non-empty field in each submission payload.",
    )
    per_email_cost = models.PositiveIntegerField(
        default=10, help_text="Credits charged for every notification email sent."
    )

    # Reset behaviour
    reset_period_days = models.PositiveIntegerField(
        default=30,
        help_text="Number of days between automatic free-credit refills (0 disables).",
    )

    # Rate limits for the public submit API (per access key, sliding window).
    submit_rate_per_minute = models.PositiveIntegerField(
        default=60,
        help_text="Max form submissions accepted per minute per access key.",
    )
    submit_rate_per_hour = models.PositiveIntegerField(
        default=1000,
        help_text="Max form submissions accepted per hour per access key (0 disables).",
    )

    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_default", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Only one default plan
        if self.is_default:
            CreditPlan.objects.exclude(pk=self.pk).filter(is_default=True).update(
                is_default=False
            )
        super().save(*args, **kwargs)


class UserCreditBalance(models.Model):
    """Per-user credit wallet."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="credit_balance",
    )
    plan = models.ForeignKey(
        CreditPlan,
        on_delete=models.PROTECT,
        related_name="users",
    )
    balance = models.IntegerField(default=0)
    monthly_credits_used = models.PositiveIntegerField(default=0)
    last_reset_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}: {self.balance} credits ({self.plan.name})"


class CreditTransaction(models.Model):
    """Audit log of every credit movement (consumption or refill)."""

    class Kind(models.TextChoices):
        FORM_CREATION = "form_creation", "Form creation"
        SUBMISSION_FIELDS = "submission_fields", "Submission fields"
        EMAIL_SENT = "email_sent", "Email sent"
        REFILL = "refill", "Monthly refill"
        ADMIN_ADJUSTMENT = "admin_adjustment", "Admin adjustment"
        SIGNUP_BONUS = "signup_bonus", "Signup bonus"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="credit_transactions",
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    # Negative for consumption, positive for refills/bonuses
    amount = models.IntegerField()
    balance_after = models.IntegerField()
    description = models.CharField(max_length=255, blank=True, default="")
    # Optional generic reference to the originating object (form id, submission id, etc.)
    reference = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["kind", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.user.username} {self.kind} {self.amount:+d}"
