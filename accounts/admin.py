from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from tickets.admin.enhancements import AdminEnhancementsMixin

User = get_user_model()

admin.site.unregister(User)


@admin.register(User)
class UserAdmin(AdminEnhancementsMixin, DjangoUserAdmin):
    """
    Django's user admin, with the privilege-escalation paths closed for
    anyone who isn't a superuser: they can manage staff accounts and assign
    roles, but can't create superusers, hand out individual permissions or
    edit a superuser's account (including its password).
    """

    list_display = ["username", "full_name", "email", "role", "is_active", "last_login"]
    list_filter = ["groups", "is_active", "is_staff"]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("groups")

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            readonly += ["is_superuser", "user_permissions", "last_login", "date_joined"]
        return readonly

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.is_superuser and not request.user.is_superuser:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_superuser and not request.user.is_superuser:
            return False
        return super().has_delete_permission(request, obj)

    @admin.display(description="Name", ordering="first_name")
    def full_name(self, obj):
        return obj.get_full_name()

    @admin.display(description="Role")
    def role(self, obj):
        if obj.is_superuser:
            return "Superuser"
        return ", ".join(group.name for group in obj.groups.all()) or "-"
