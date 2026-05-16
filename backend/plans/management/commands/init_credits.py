"""Bootstrap the credits app: default plan, admin group, user wallets."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from plans.models import CreditPlan
from plans.services import (
    ensure_admin_group,
    get_default_plan,
    get_or_create_balance,
)


def _ensure_legend_plan(base: CreditPlan) -> CreditPlan:
    """Create or refresh the 'Legend' plan with 2x the base benefits."""
    defaults = {
        "name": "Legend",
        "description": (
            "Premium tier with 2x the free monthly credits, 2x the rate limits, "
            "and half the per-action cost of the base plan."
        ),
        "monthly_credits": base.monthly_credits * 2,
        "form_creation_cost": max(1, base.form_creation_cost // 2),
        "per_field_cost": max(1, base.per_field_cost // 2),
        "per_email_cost": max(1, base.per_email_cost // 2),
        "reset_period_days": base.reset_period_days,
        "submit_rate_per_minute": (base.submit_rate_per_minute or 60) * 2,
        "submit_rate_per_hour": (base.submit_rate_per_hour or 1000) * 2,
        "is_default": False,
        "is_active": True,
    }
    plan, created = CreditPlan.objects.update_or_create(
        slug="legend", defaults=defaults
    )
    return plan


class Command(BaseCommand):
    help = "Create the default credit plan, admin role group, and wallets for existing users."

    def add_arguments(self, parser):
        parser.add_argument(
            "--promote",
            metavar="USERNAME",
            help="Add this user to the 'admin' role group.",
        )

    def handle(self, *args, **options):
        plan = get_default_plan()
        self.stdout.write(self.style.SUCCESS(f"Default plan: {plan.name}"))

        legend = _ensure_legend_plan(plan)
        self.stdout.write(
            self.style.SUCCESS(
                f"Legend plan: {legend.name} "
                f"({legend.monthly_credits} cr/mo, {legend.submit_rate_per_minute}/min)"
            )
        )

        group = ensure_admin_group()
        self.stdout.write(self.style.SUCCESS(f"Admin role group: {group.name}"))

        User = get_user_model()
        created = 0
        for user in User.objects.all():
            balance = get_or_create_balance(user)
            created += 1
            self.stdout.write(f"  · {user.username}: {balance.balance} credits")
        self.stdout.write(self.style.SUCCESS(f"Initialised wallets for {created} user(s)."))

        promote = options.get("promote")
        if promote:
            try:
                u = User.objects.get(username=promote)
            except User.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"User '{promote}' not found."))
                return
            u.groups.add(group)
            self.stdout.write(
                self.style.SUCCESS(f"Granted admin role to '{u.username}'.")
            )
