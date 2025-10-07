# apps/users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User

# class UserAdmin(BaseUserAdmin):
#     model = User
#     list_display = ("username", "email", "role", "is_staff", "is_superuser")
#     list_filter = ("role", "is_staff", "is_superuser")
#     fieldsets = (
#         (None, {"fields": ("username", "email", "password", "role")}),
#         ("Permissions", {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")}),
#         ("Important dates", {"fields": ("last_login", "date_joined")}),
#     )
#     add_fieldsets = (
#         (None, {
#             "classes": ("wide",),
#             "fields": ("username", "email", "password1", "password2", "role", "is_staff", "is_superuser"),
#         }),
#     )
#     search_fields = ("email", "username")
#     ordering = ("email",)

# admin.site.register(User, UserAdmin)
admin.site.register(User)