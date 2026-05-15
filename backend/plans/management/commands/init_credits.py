"""Bootstrap the credits app: default plan, admin group, user wallets."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from plans.services import (
    ensure_admin_group,
    get_default_plan,
    get_or_create_balance,
)


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
