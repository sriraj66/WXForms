from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import action

from .forms import CreditAdjustmentForm
from .models import CreditPlan, CreditTransaction, UserCreditBalance
from .services import grant


@admin.register(CreditPlan)
class CreditPlanAdmin(ModelAdmin):
    list_display = (
        "name",
        "monthly_credits",
        "form_creation_cost",
        "per_field_cost",
        "per_email_cost",
        "is_default",
        "is_active",
    )
    list_filter = ("is_default", "is_active")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    fieldsets = (
        (None, {"fields": ("name", "slug", "description", "is_active", "is_default")}),
        (
            "Pricing rules (credits)",
            {
                "fields": (
                    "monthly_credits",
                    "form_creation_cost",
                    "per_field_cost",
                    "per_email_cost",
                    "reset_period_days",
                )
            },
        ),
    )


@admin.register(UserCreditBalance)
class UserCreditBalanceAdmin(ModelAdmin):
    list_display = ("user", "plan", "balance_display", "monthly_credits_used", "last_reset_at")
    list_filter = ("plan",)
    search_fields = ("user__username", "user__email")
    autocomplete_fields = ("user", "plan")
    readonly_fields = ("created_at", "updated_at", "last_reset_at")
    actions_detail = ["adjust_credits"]

    @admin.display(description="Balance", ordering="balance")
    def balance_display(self, obj):
        color = "#dc2626" if obj.balance <= 0 else "inherit"
        return format_html('<span style="color:{};font-weight:600">{}</span>', color, obj.balance)

    @action(
        description="Adjust credits",
        url_path="adjust-credits",
        permissions=["change"],
    )
    def adjust_credits(self, request, object_id):
        balance = self.get_object(request, object_id)
        if balance is None:
            messages.error(request, "Balance not found.")
            return HttpResponseRedirect(reverse("admin:credits_usercreditbalance_changelist"))

        if request.method == "POST":
            form = CreditAdjustmentForm(request.POST)
            if form.is_valid():
                amount = form.cleaned_data["amount"]
                description = (
                    form.cleaned_data["description"]
                    or f"Admin adjustment by {request.user.username}"
                )
                grant(
                    balance.user,
                    amount,
                    kind=CreditTransaction.Kind.ADMIN_ADJUSTMENT,
                    description=description,
                )
                messages.success(
                    request, f"Adjusted {balance.user.username} by {amount:+d}."
                )
                return HttpResponseRedirect(
                    reverse(
                        "admin:credits_usercreditbalance_change",
                        args=[balance.pk],
                    )
                )
        else:
            form = CreditAdjustmentForm()

        return render(
            request,
            "admin/credits/adjust_credits.html",
            {
                **self.admin_site.each_context(request),
                "title": f"Adjust credits — {balance.user.username}",
                "balance": balance,
                "form": form,
                "opts": self.model._meta,
            },
        )


@admin.register(CreditTransaction)
class CreditTransactionAdmin(ModelAdmin):
    list_display = ("created_at", "user", "kind", "amount_display", "balance_after", "description")
    list_filter = ("kind",)
    search_fields = ("user__username", "description", "reference")
    autocomplete_fields = ("user",)
    date_hierarchy = "created_at"
    readonly_fields = (
        "user",
        "kind",
        "amount",
        "balance_after",
        "description",
        "reference",
        "created_at",
    )

    @admin.display(description="Amount", ordering="amount")
    def amount_display(self, obj):
        color = "#dc2626" if obj.amount < 0 else "#16a34a"
        return format_html(
            '<span style="color:{};font-weight:600;font-variant-numeric:tabular-nums">{}</span>',
            color,
            f"{obj.amount:+d}",
        )

    def has_add_permission(self, request):
        # Transactions are an audit log — never created manually
        return False
