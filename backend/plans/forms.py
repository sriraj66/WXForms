"""Forms for credit-system admin pages."""

from django import forms
from django.contrib.auth import get_user_model

from .models import CreditPlan

User = get_user_model()


class CreditPlanForm(forms.ModelForm):
    class Meta:
        model = CreditPlan
        fields = [
            "name",
            "slug",
            "description",
            "monthly_credits",
            "form_creation_cost",
            "per_field_cost",
            "per_email_cost",
            "reset_period_days",
            "is_default",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "v-input"}),
            "slug": forms.TextInput(attrs={"class": "v-input"}),
            "description": forms.Textarea(attrs={"class": "v-textarea", "rows": 3}),
            "monthly_credits": forms.NumberInput(attrs={"class": "v-input", "min": 0}),
            "form_creation_cost": forms.NumberInput(attrs={"class": "v-input", "min": 0}),
            "per_field_cost": forms.NumberInput(attrs={"class": "v-input", "min": 0}),
            "per_email_cost": forms.NumberInput(attrs={"class": "v-input", "min": 0}),
            "reset_period_days": forms.NumberInput(attrs={"class": "v-input", "min": 0}),
        }


class CreditAdjustmentForm(forms.Form):
    amount = forms.IntegerField(
        label="Adjustment amount",
        help_text="Positive to grant credits, negative to deduct.",
        widget=forms.NumberInput(attrs={"class": "v-input"}),
    )
    description = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "v-input", "placeholder": "Reason for adjustment"}
        ),
    )


class AssignPlanForm(forms.Form):
    plan = forms.ModelChoiceField(
        queryset=CreditPlan.objects.filter(is_active=True),
        widget=forms.Select(attrs={"class": "v-select"}),
    )
