from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from . import services
from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ["-date_joined"]
    list_display = ["email", "full_name", "whatsapp_number", "status", "is_staff", "date_joined"]
    list_filter = ["status", "is_staff", "is_active"]
    search_fields = ["email", "full_name", "whatsapp_number"]
    readonly_fields = ["status_changed_at", "status_changed_by", "last_login", "date_joined"]
    fieldsets = [
        (None, {"fields": ["email", "password"]}),
        ("Profil", {"fields": ["full_name", "whatsapp_number"]}),
        ("Status member", {"fields": ["status", "status_changed_at", "status_changed_by"]}),
        (
            "Hak akses",
            {"fields": ["is_active", "is_staff", "is_superuser", "groups", "user_permissions"]},
        ),
        ("Waktu", {"fields": ["last_login", "date_joined"]}),
    ]
    add_fieldsets = [
        (
            None,
            {
                "classes": ["wide"],
                "fields": ["email", "full_name", "password1", "password2"],
            },
        )
    ]
    actions = ["approve", "reject", "suspend"]

    def _apply(self, request, queryset, func, label):
        for user in queryset:
            func(user, by=request.user)
        self.message_user(request, f"{queryset.count()} pengguna {label}.", messages.SUCCESS)

    @admin.action(description="Setujui member terpilih")
    def approve(self, request, queryset):
        self._apply(request, queryset, services.approve_member, "disetujui")

    @admin.action(description="Tolak member terpilih")
    def reject(self, request, queryset):
        self._apply(
            request, queryset.exclude(pk=request.user.pk), services.reject_member, "ditolak"
        )

    @admin.action(description="Nonaktifkan member terpilih")
    def suspend(self, request, queryset):
        self._apply(
            request, queryset.exclude(pk=request.user.pk), services.suspend_member, "dinonaktifkan"
        )
