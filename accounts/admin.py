from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import EmailVerificationCode, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("商户信息", {"fields": ("display_name", "phone", "is_merchant", "email_verified", "email_verified_at")}),
    )
    list_display = ("username", "email", "display_name", "email_verified", "is_staff", "is_merchant")
    search_fields = ("username", "email", "display_name", "phone")


@admin.register(EmailVerificationCode)
class EmailVerificationCodeAdmin(admin.ModelAdmin):
    list_display = ("email", "purpose", "code", "created_at", "expires_at", "consumed_at")
    list_filter = ("purpose", "consumed_at")
    search_fields = ("email", "code")
