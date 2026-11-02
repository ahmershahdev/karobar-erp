from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):  # type: ignore[type-arg]
    ordering = ("email",)
    list_display = ("email", "full_name", "is_staff", "is_active")
    search_fields = ("email", "full_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("full_name", "email_verified_at")}),
        ("Access", {"fields": ("is_active", "is_staff", "is_superuser", "groups")}),
    )
    add_fieldsets = ((None, {"fields": ("email", "password1", "password2")}),)
    readonly_fields = ("email_verified_at",)
