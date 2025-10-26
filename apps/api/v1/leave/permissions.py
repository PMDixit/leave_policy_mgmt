"""
Custom permissions for leave management API.
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


class IsEmployeeOwner(BasePermission):
    """
    Permission to ensure users can only access their own data.
    """

    def has_object_permission(self, request, view, obj):
        # Allow HR and admins to access all records
        if hasattr(request.user, 'is_hr') and (request.user.is_hr or request.user.is_admin):
            return True

        # For leave applications, check if user is the employee
        if hasattr(obj, 'employee_id'):
            return str(obj.employee_id) == str(request.user.id)

        # For leave balances, check if user owns the balance
        if hasattr(obj, 'employee_id'):
            return str(obj.employee_id) == str(request.user.id)

        return False
