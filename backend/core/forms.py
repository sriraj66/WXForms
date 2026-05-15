"""Django forms for the core application."""

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import AccessKey, EmailTemplate, Form, FormField, GmailConfig

# --- Tailwind CSS classes for consistent Vercel-style inputs ---
INPUT_CLASSES = "v-input"
CHECKBOX_CLASSES = (
    "h-4 w-4 rounded border-ink-300 text-ink-900 focus:ring-1 focus:ring-ink-900 "
    "dark:bg-ink-900 dark:border-ink-700 dark:text-white dark:focus:ring-white"
)
SELECT_CLASSES = "v-select"
TEXTAREA_CLASSES = "v-textarea min-h-[100px]"


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs["class"] = INPUT_CLASSES
            field.widget.attrs["placeholder"] = field.label or field_name.replace("_", " ").title()


class LoginForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Username"}),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASSES, "placeholder": "Password"}),
    )


class ProfileForm(forms.ModelForm):
    """User profile — username and email are read-only by design."""

    class Meta:
        model = User
        fields = ["first_name", "last_name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = INPUT_CLASSES


class AccessKeyForm(forms.ModelForm):
    class Meta:
        model = AccessKey
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": INPUT_CLASSES, "placeholder": "Key name (e.g., My Website)"}
            ),
        }


class GmailConfigForm(forms.Form):
    sender_email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={"class": INPUT_CLASSES, "placeholder": "your-email@gmail.com"}
        ),
    )
    app_password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": INPUT_CLASSES, "placeholder": "Gmail App Password"}
        ),
        help_text="Generate an App Password from your Google Account settings.",
    )

    def clean_sender_email(self):
        email = self.cleaned_data["sender_email"]
        if not email.endswith("@gmail.com") and not email.endswith("@googlemail.com"):
            raise forms.ValidationError("Please use a Gmail address.")
        return email


class FormCreateForm(forms.ModelForm):
    class Meta:
        model = Form
        fields = ["name", "access_key", "email_to", "allowed_domains", "redirect_url", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Form name"}),
            "email_to": forms.EmailInput(
                attrs={"class": INPUT_CLASSES, "placeholder": "Where to receive submissions"}
            ),
            "allowed_domains": forms.TextInput(
                attrs={
                    "class": INPUT_CLASSES,
                    "placeholder": "example.com, mysite.org (leave empty for all)",
                }
            ),
            "redirect_url": forms.URLInput(
                attrs={
                    "class": INPUT_CLASSES,
                    "placeholder": "https://yoursite.com/thank-you (optional)",
                }
            ),
            "is_active": forms.CheckboxInput(attrs={"class": CHECKBOX_CLASSES}),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["access_key"].queryset = AccessKey.objects.filter(user=user, is_active=True)
        self.fields["access_key"].widget.attrs["class"] = SELECT_CLASSES
        self.fields["access_key"].empty_label = "Select an access key"


class FormFieldForm(forms.ModelForm):
    class Meta:
        model = FormField
        fields = ["name", "field_type", "required", "placeholder", "default_value", "order"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Field name"}),
            "field_type": forms.Select(attrs={"class": SELECT_CLASSES}),
            "required": forms.CheckboxInput(attrs={"class": CHECKBOX_CLASSES}),
            "placeholder": forms.TextInput(
                attrs={"class": INPUT_CLASSES, "placeholder": "Placeholder text"}
            ),
            "default_value": forms.TextInput(
                attrs={"class": INPUT_CLASSES, "placeholder": "Default value"}
            ),
            "order": forms.NumberInput(attrs={"class": INPUT_CLASSES, "placeholder": "0"}),
        }


FormFieldFormSet = forms.inlineformset_factory(
    Form,
    FormField,
    form=FormFieldForm,
    extra=1,
    can_delete=True,
)


class EmailTemplateForm(forms.ModelForm):
    class Meta:
        model = EmailTemplate
        fields = ["name", "subject", "body_html", "body_text", "is_default"]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": INPUT_CLASSES, "placeholder": "Template name"}
            ),
            "subject": forms.TextInput(
                attrs={"class": INPUT_CLASSES, "placeholder": "Email subject"}
            ),
            "body_html": forms.Textarea(
                attrs={
                    "class": TEXTAREA_CLASSES,
                    "rows": 12,
                    "placeholder": "HTML body with {{placeholders}}",
                }
            ),
            "body_text": forms.Textarea(
                attrs={
                    "class": TEXTAREA_CLASSES,
                    "rows": 8,
                    "placeholder": "Plain text body (optional)",
                }
            ),
            "is_default": forms.CheckboxInput(attrs={"class": CHECKBOX_CLASSES}),
        }