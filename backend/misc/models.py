"""Models for the misc app: user profile (survey + avatar), app settings, dynamic UI hints."""

from django.conf import settings
from django.db import models


def avatar_upload_to(instance, filename):
    return f"avatars/user_{instance.user_id}/{filename}"


class UserProfile(models.Model):
    """Extended profile data + onboarding survey answers."""

    class WhyUsing(models.TextChoices):
        BUSINESS_FORMS = "business_forms", "Business contact forms"
        FEEDBACK = "feedback", "Customer feedback"
        LEAD_GEN = "lead_gen", "Lead generation"
        EVENT = "event", "Event / RSVP"
        SURVEYS = "surveys", "Surveys & research"
        PERSONAL = "personal", "Personal project"
        OTHER = "other", "Other"

    class WhereHeard(models.TextChoices):
        SEARCH = "search", "Search engine (Google, Bing, ...)"
        SOCIAL = "social", "Social media"
        FRIEND = "friend", "Friend or colleague"
        BLOG = "blog", "Blog / article"
        YOUTUBE = "youtube", "YouTube"
        GITHUB = "github", "GitHub"
        OTHER = "other", "Other"

    class BusinessType(models.TextChoices):
        INDIVIDUAL = "individual", "Individual / Freelancer"
        STARTUP = "startup", "Startup"
        SMB = "smb", "Small / medium business"
        ENTERPRISE = "enterprise", "Enterprise"
        AGENCY = "agency", "Agency"
        NONPROFIT = "nonprofit", "Non-profit"
        EDUCATION = "education", "Education"
        OTHER = "other", "Other"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="misc_profile"
    )
    avatar = models.ImageField(upload_to=avatar_upload_to, null=True, blank=True)

    # Onboarding survey
    why_using = models.CharField(
        max_length=32, choices=WhyUsing.choices, blank=True, default=""
    )
    where_heard = models.CharField(
        max_length=32, choices=WhereHeard.choices, blank=True, default=""
    )
    business_type = models.CharField(
        max_length=32, choices=BusinessType.choices, blank=True, default=""
    )

    # Contact / company
    mobile_number = models.CharField(max_length=24, blank=True, default="")
    country = models.CharField(max_length=2, blank=True, default="", help_text="ISO 3166-1 alpha-2")
    pincode = models.CharField(max_length=16, blank=True, default="")
    company_name = models.CharField(max_length=120, blank=True, default="")
    company_business_type = models.CharField(
        max_length=32, choices=BusinessType.choices, blank=True, default=""
    )

    survey_completed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile<{self.user_id}>"

    @property
    def avatar_url(self):
        try:
            return self.avatar.url if self.avatar else ""
        except Exception:
            return ""


class AppSetting(models.Model):
    """Generic key/value store for global app settings (admin-managed)."""

    class Kind(models.TextChoices):
        STRING = "string", "String"
        BOOL = "bool", "Boolean"
        INT = "int", "Integer"
        JSON = "json", "JSON"

    key = models.CharField(max_length=120, unique=True, db_index=True)
    value = models.TextField(blank=True, default="")
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.STRING)
    description = models.CharField(max_length=255, blank=True, default="")
    is_public = models.BooleanField(
        default=False, help_text="If true, value is exposed to the dashboard UI."
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return self.key


class UIConfig(models.Model):
    """Dynamic UI hints / banners / announcements (placeholder for future)."""

    slug = models.SlugField(max_length=80, unique=True)
    title = models.CharField(max_length=200, blank=True, default="")
    body = models.TextField(blank=True, default="")
    payload_json = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["slug"]

    def __str__(self):
        return self.slug
