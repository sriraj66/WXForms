"""Credit operations: balance access, consumption, refills.

All credit changes go through `consume()` or `grant()` so the
`CreditTransaction` audit log stays consistent.
"""

from datetime import timedelta

from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone

from .models import CreditPlan, CreditTransaction, UserCreditBalance

ADMIN_GROUP_NAME = "admin"


class InsufficientCreditsError(Exception):
    """Raised when a charge would take a balance below zero."""

    def __init__(self, required, available):
        self.required = required
        self.available = available
        super().__init__(
            f"Insufficient credits: need {required}, have {available}."
        )


def get_default_plan():
    """Return the default plan, creating a sensible one on first call."""
    plan = CreditPlan.objects.filter(is_default=True, is_active=True).first()
    if plan:
        return plan
    plan, _ = CreditPlan.objects.get_or_create(
        slug="free",
        defaults={
            "name": "Free",
            "description": "Default plan for new accounts.",
            "is_default": True,
        },
    )
    return plan


def get_or_create_balance(user):
    """Get the user's wallet, creating it (with signup bonus) if missing.

    Also performs an automatic monthly reset when the configured period
    has elapsed.
    """
    balance = UserCreditBalance.objects.filter(user=user).first()
    if balance is None:
        plan = get_default_plan()
        with transaction.atomic():
            balance = UserCreditBalance.objects.create(
                user=user,
                plan=plan,
                balance=plan.monthly_credits,
                last_reset_at=timezone.now(),
            )
            CreditTransaction.objects.create(
                user=user,
                kind=CreditTransaction.Kind.SIGNUP_BONUS,
                amount=plan.monthly_credits,
                balance_after=balance.balance,
                description=f"Initial credits from plan '{plan.name}'.",
            )
        return balance

    # Auto-refill if reset period elapsed
    plan = balance.plan
    if plan.reset_period_days and balance.last_reset_at:
        next_reset = balance.last_reset_at + timedelta(days=plan.reset_period_days)
        if timezone.now() >= next_reset:
            refill(user, plan.monthly_credits, description="Automatic monthly refill.")
            balance.refresh_from_db()

    return balance


@transaction.atomic
def consume(user, amount, kind, description="", reference=""):
    """Atomically deduct credits and log a transaction.

    Raises `InsufficientCreditsError` when the balance would go negative.
    """
    if amount <= 0:
        return get_or_create_balance(user)

    # Ensure wallet exists / monthly reset processed
    get_or_create_balance(user)

    # Lock the row to avoid race conditions on concurrent submissions
    balance = UserCreditBalance.objects.select_for_update().get(user=user)
    if balance.balance < amount:
        raise InsufficientCreditsError(required=amount, available=balance.balance)

    balance.balance -= amount
    balance.monthly_credits_used += amount
    balance.save(update_fields=["balance", "monthly_credits_used", "updated_at"])

    CreditTransaction.objects.create(
        user=user,
        kind=kind,
        amount=-amount,
        balance_after=balance.balance,
        description=description,
        reference=str(reference) if reference else "",
    )
    return balance


@transaction.atomic
def grant(
    user,
    amount,
    kind=CreditTransaction.Kind.ADMIN_ADJUSTMENT,
    description="",
    reference="",
):
    """Add credits to a user's wallet."""
    get_or_create_balance(user)
    balance = UserCreditBalance.objects.select_for_update().get(user=user)
    balance.balance += amount
    balance.save(update_fields=["balance", "updated_at"])

    CreditTransaction.objects.create(
        user=user,
        kind=kind,
        amount=amount,
        balance_after=balance.balance,
        description=description,
        reference=str(reference) if reference else "",
    )
    return balance


@transaction.atomic
def refill(user, amount, description="Monthly refill"):
    """Reset the monthly counter and top up to `amount` (not additive)."""
    get_or_create_balance(user)
    balance = UserCreditBalance.objects.select_for_update().get(user=user)
    balance.balance = max(balance.balance, 0) + amount
    balance.monthly_credits_used = 0
    balance.last_reset_at = timezone.now()
    balance.save(
        update_fields=[
            "balance",
            "monthly_credits_used",
            "last_reset_at",
            "updated_at",
        ]
    )
    CreditTransaction.objects.create(
        user=user,
        kind=CreditTransaction.Kind.REFILL,
        amount=amount,
        balance_after=balance.balance,
        description=description,
    )
    return balance


# ---------------------------------------------------------------------------
# Convenience charge helpers — used by the rest of the app
# ---------------------------------------------------------------------------


def charge_form_creation(user, form):
    plan = get_or_create_balance(user).plan
    return consume(
        user,
        plan.form_creation_cost,
        CreditTransaction.Kind.FORM_CREATION,
        description=f"Form created: {form.name}",
        reference=f"form:{form.pk}",
    )


def charge_submission_fields(user, submission, field_count):
    plan = get_or_create_balance(user).plan
    cost = plan.per_field_cost * field_count
    if cost <= 0:
        return None
    return consume(
        user,
        cost,
        CreditTransaction.Kind.SUBMISSION_FIELDS,
        description=f"Submission #{submission.pk}: {field_count} fields",
        reference=f"submission:{submission.pk}",
    )


def charge_email_sent(user, submission):
    plan = get_or_create_balance(user).plan
    return consume(
        user,
        plan.per_email_cost,
        CreditTransaction.Kind.EMAIL_SENT,
        description=f"Notification email for submission #{submission.pk}",
        reference=f"submission:{submission.pk}",
    )


# ---------------------------------------------------------------------------
# Role helpers
# ---------------------------------------------------------------------------


def is_admin_role(user):
    """Custom 'admin' role check — distinct from `is_superuser`.

    A user is considered an admin if they are an active member of the
    `admin` Django group.  Superusers also pass for convenience.
    """
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=ADMIN_GROUP_NAME).exists()


def ensure_admin_group():
    """Idempotently create the 'admin' group."""
    group, _ = Group.objects.get_or_create(name=ADMIN_GROUP_NAME)
    return group
