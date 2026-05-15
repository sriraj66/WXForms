"""Forms for the misc app."""

import re

from django import forms

from .models import UserProfile

INPUT_CLASSES = "v-input"
SELECT_CLASSES = "v-select"


# A small built-in country list. Easy to extend later.
COUNTRY_CHOICES = [
    ("", "Select country"),
    ("IN", "India"),
    ("US", "United States"),
    ("GB", "United Kingdom"),
    ("CA", "Canada"),
    ("AU", "Australia"),
    ("DE", "Germany"),
    ("FR", "France"),
    ("ES", "Spain"),
    ("IT", "Italy"),
    ("NL", "Netherlands"),
    ("SE", "Sweden"),
    ("SG", "Singapore"),
    ("AE", "United Arab Emirates"),
    ("JP", "Japan"),
    ("BR", "Brazil"),
    ("ZA", "South Africa"),
    ("OTHER", "Other"),
]


class SurveyForm(forms.ModelForm):
    """Onboarding form — choices only for survey, plus contact + company info."""

    country = forms.ChoiceField(
        choices=COUNTRY_CHOICES,
        widget=forms.Select(attrs={"class": SELECT_CLASSES}),
    )

    class Meta:
        model = UserProfile
        fields = [
            # Survey
            "why_using",
            "where_heard",
            "business_type",
            # Contact
            "mobile_number",
            "country",
            "pincode",
            # Company (optional)
            "company_name",
            "company_business_type",
        ]
        widgets = {
            "why_using": forms.Select(attrs={"class": SELECT_CLASSES}),
            "where_heard": forms.Select(attrs={"class": SELECT_CLASSES}),
            "business_type": forms.Select(attrs={"class": SELECT_CLASSES}),
            "mobile_number": forms.TextInput(
                attrs={"class": INPUT_CLASSES, "placeholder": "+1 555 123 4567", "inputmode": "tel"}
            ),
            "pincode": forms.TextInput(
                attrs={"class": INPUT_CLASSES, "placeholder": "Postal / ZIP code"}
            ),
            "company_name": forms.TextInput(
                attrs={"class": INPUT_CLASSES, "placeholder": "Acme Inc. (optional)"}
            ),
            "company_business_type": forms.Select(attrs={"class": SELECT_CLASSES}),
        }
        labels = {
            "why_using": "Why are you using this?",
            "where_heard": "Where did you hear about us?",
            "business_type": "I am a / part of",
            "mobile_number": "Mobile number",
            "country": "Country",
            "pincode": "Pincode / ZIP",
            "company_name": "Company name",
            "company_business_type": "Company type",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Required fields
        for name in ("why_using", "where_heard", "business_type", "mobile_number", "country", "pincode"):
            self.fields[name].required = True
        # Optional fields
        for name in ("company_name", "company_business_type"):
            self.fields[name].required = False

    def clean_mobile_number(self):
        value = (self.cleaned_data.get("mobile_number") or "").strip()
        # Allow +, digits, spaces, dashes; require at least 7 digits.
        if not re.fullmatch(r"[+0-9 \-()]{7,24}", value):
            raise forms.ValidationError("Enter a valid mobile number (digits, spaces, +, -, () allowed).")
        digit_count = sum(1 for c in value if c.isdigit())
        if digit_count < 7:
            raise forms.ValidationError("Mobile number looks too short.")
        return value

    def clean_pincode(self):
        value = (self.cleaned_data.get("pincode") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9 \-]{3,16}", value):
            raise forms.ValidationError("Enter a valid pincode / ZIP.")
        return value


class AvatarForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ["avatar"]
        widgets = {
            "avatar": forms.ClearableFileInput(attrs={"class": "v-input", "accept": "image/*"}),
        }
