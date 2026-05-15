from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import AppSetting, UIConfig, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(ModelAdmin):
    list_display = ("user", "business_type", "why_using", "where_heard", "survey_completed", "updated_at")
    list_filter = ("business_type", "why_using", "where_heard", "survey_completed")
    search_fields = ("user__username", "user__email")
    autocomplete_fields = ("user",)


@admin.register(AppSetting)
class AppSettingAdmin(ModelAdmin):
    list_display = ("key", "kind", "is_public", "updated_at")
    list_filter = ("kind", "is_public")
    search_fields = ("key", "description")


@admin.register(UIConfig)
class UIConfigAdmin(ModelAdmin):
    list_display = ("slug", "title", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("slug", "title")
