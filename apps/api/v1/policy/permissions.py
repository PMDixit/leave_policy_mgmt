"""
Custom permissions for policy management API.
"""

from rest_framework.permissions import BasePermission


class IsTenantUser(BasePermission):
    """
    Permission to ensure user belongs to the correct tenant.
    """

    def has_permission(self, request, view):
        # Check if tenant_id is provided in request
        tenant_id = getattr(request, 'tenant_id', None)
        if not tenant_id:
            return False
        return True


class IsHRAdmin(BasePermission):
    """
    Permission for HR administrators and above.
    """

    def has_permission(self, request, view):
        if not hasattr(request.user, 'is_hr'):
            return False
        return request.user.is_hr or request.user.is_admin


class IsPolicyManager(BasePermission):
    """
    Permission for users who can manage leave policies.
    """

    def has_permission(self, request, view):
        if not hasattr(request.user, 'is_hr'):
            return False
        # HR Managers and Admins can manage policies
        return request.user.is_hr or request.user.is_admin
