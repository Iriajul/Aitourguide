# apps/users/permissions.py
from rest_framework.permissions import BasePermission

class IsRegisteredOrPremium(BasePermission):
    """
    Allow only users whose role is registered or premium.
    """
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.role in ("registered", "premium"))

class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.role == "admin")
