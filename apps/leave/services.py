"""
Business logic services for leave management.
"""

import logging
from datetime import date, timedelta
from django.utils import timezone
from django.db import transaction

from .models import LeaveApplication, LeaveBalance, ApprovalWorkflow
from apps.policy.models import Policy
from .models import LeaveCategory

logger = logging.getLogger(__name__)


class LeaveValidationService:
    """Service for validating leave applications against policies."""

    @staticmethod
    def select_policy_for_leave_application(leave_category_id, tenant_id, employee_role=None):
        """
        Select the active and approved policy for a given leave category and employee.

        The policy selection considers both applies_to and excludes fields:
        - If applies_to is empty, policy applies to everyone (except those in excludes)
        - If applies_to has values, only those roles can use the policy
        - If excludes has values, those roles cannot use the policy

        Args:
            leave_category_id: Leave category ID
            tenant_id: Tenant ID
            employee_role: Employee role/designation to check against policy's applies_to and excludes

        Returns:
            Policy object or None if no suitable policy found
        """
        try:
            # Get the leave category to ensure it exists
            leave_category = LeaveCategory.objects.get(
                id=leave_category_id,
                tenant_id=tenant_id,
                is_active=True
            )

            # Find active and approved policies for this tenant
            policies = Policy.objects.filter(
                tenant_id=tenant_id,
                policy_type='leave_time_off',  # Focus on leave policies
                is_active=True,
                is_approved=True
            ).order_by('-created_at')

            # Filter policies based on applies_to and excludes criteria
            suitable_policies = []
            for policy in policies:
                applies_to_list = policy.applies_to or []
                excludes_list = policy.excludes or []

                # Check if employee is excluded
                if employee_role and excludes_list and employee_role in excludes_list:
                    continue  # Skip this policy if employee role is in excludes

                # Check if employee is included
                if not applies_to_list:
                    # If applies_to is empty, policy applies to everyone (not excluded)
                    suitable_policies.append(policy)
                elif employee_role and employee_role in applies_to_list:
                    # If employee_role is provided and matches applies_to
                    suitable_policies.append(policy)
                # If no employee_role provided but applies_to has values, skip this policy
                # (we can't determine if it applies without knowing the employee role)

            # Return the most recent suitable policy
            return suitable_policies[0] if suitable_policies else None

        except LeaveCategory.DoesNotExist:
            logger.warning(f"Leave category {leave_category_id} not found for tenant {tenant_id}")
            return None
        except Exception as e:
            logger.error(f"Error selecting policy for leave application: {str(e)}")
            return None

    @staticmethod
    def validate_leave_application(application_data, tenant_id, employee_id, employee_role=None, employee_department=None):
        """
        Validate leave application against all policy rules and select appropriate policy.

        Implements comprehensive leave policy checks including:
        - Documentation requirements based on leave type and duration
        - Balance validation for annual leave
        - Employment type restrictions
        - Monthly limits and blackout periods
        - Notice period requirements

        Args:
            application_data: Dict containing leave application data
            tenant_id: Tenant ID
            employee_id: Employee ID
            employee_role: Employee role/designation for policy applicability check
            employee_department: Employee department for additional checks

        Returns:
            dict: Validation results with policy and errors if any
        """
        errors = {}
        warnings = []
        actions_required = []

        leave_category_id = application_data.get('leave_category_id')
        start_date = application_data.get('start_date')
        end_date = application_data.get('end_date')
        total_days = application_data.get('total_days', 1)

        if not all([leave_category_id, start_date, end_date]):
            errors['required_fields'] = 'Missing required fields'
            return {'valid': False, 'errors': errors, 'warnings': warnings, 'policy': None, 'actions_required': actions_required}

        # Get leave category details
        try:
            leave_category = LeaveCategory.objects.get(
                id=leave_category_id,
                tenant_id=tenant_id,
                is_active=True
            )
            leave_type = leave_category.name.lower()
        except LeaveCategory.DoesNotExist:
            errors['category'] = 'Invalid leave category'
            return {'valid': False, 'errors': errors, 'warnings': warnings, 'policy': None, 'actions_required': actions_required}

        # Select appropriate policy
        policy = LeaveValidationService.select_policy_for_leave_application(leave_category_id, tenant_id, employee_role)
        if not policy:
            errors['policy'] = 'No active and approved policy found for the selected leave category and employee role'
            return {'valid': False, 'errors': errors, 'warnings': warnings, 'policy': None, 'actions_required': actions_required}

        # 1. Check documentation requirements
        doc_check = LeaveValidationService._check_documentation_requirements(
            leave_type, total_days, policy, application_data
        )
        if doc_check['required'] and not application_data.get('document_url'):
            errors['documentation'] = doc_check['message']
            actions_required.append('require_attachment')

        # 2. Check balance validation (for Annual leave)
        if leave_type == 'annual':
            balance_check = LeaveValidationService._check_leave_balance(
                tenant_id, employee_id, leave_category_id, total_days
            )
            if not balance_check['valid']:
                errors.update(balance_check['errors'])

        # 3. Check overlapping leaves
        overlap_check = LeaveValidationService._check_overlapping_leaves(
            tenant_id, employee_id, start_date, end_date
        )
        if not overlap_check['valid']:
            errors.update(overlap_check['errors'])

        # 4. Check monthly limits
        monthly_limit_check = LeaveValidationService._check_monthly_limits(
            tenant_id, employee_id, leave_category_id, start_date, end_date, policy
        )
        if not monthly_limit_check['valid']:
            errors.update(monthly_limit_check['errors'])

        # 5. Check notice period requirements
        notice_check = LeaveValidationService._check_notice_period(
            start_date, policy, application_data
        )
        if not notice_check['valid']:
            errors.update(notice_check['errors'])

        # 6. Check blackout periods (simplified - would need holiday calendar integration)
        blackout_check = LeaveValidationService._check_blackout_periods(
            start_date, end_date, leave_type
        )
        if not blackout_check['valid']:
            warnings.extend(blackout_check['warnings'])

        # 7. Check employment-based restrictions (simplified - would need employee data)
        employment_check = LeaveValidationService._check_employment_restrictions(
            employee_role, leave_type
        )
        if not employment_check['valid']:
            errors.update(employment_check['errors'])

        # 8. Determine required actions
        if leave_type == 'sick' and total_days > 3:
            actions_required.append('require_medical_certificate')
        elif leave_type in ['maternity', 'paternity']:
            actions_required.append('require_birth_certificate')
        elif total_days > 14:
            actions_required.append('require_fitness_certificate')

        # Set approval routing
        if policy.approval_route:
            actions_required.append('route_to_approvers')

        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'policy': policy,
            'actions_required': actions_required,
            'leave_type': leave_type
        }

    @staticmethod
    def _check_documentation_requirements(leave_type, total_days, policy, application_data):
        """Check if documentation is required based on leave type and duration."""
        required = False
        message = ""

        # Check policy-level document requirement
        if policy.document_required:
            required = True
            message = "Documentation required by policy"

        # Check leave type specific rules
        if leave_type == 'sick' and total_days > 3:
            required = True
            message = f"Sick leave exceeding {3} days requires medical certificate"

        # Check category-level documentation threshold
        try:
            leave_category = LeaveCategory.objects.get(
                name__iexact=leave_type,
                tenant_id=policy.tenant_id
            )
            if leave_category.requires_documentation and total_days >= leave_category.documentation_threshold_days:
                required = True
                message = f"{leave_type.title()} leave exceeding {leave_category.documentation_threshold_days} days requires documentation"
        except LeaveCategory.DoesNotExist:
            pass

        return {'required': required, 'message': message}

    @staticmethod
    def _check_leave_balance(tenant_id, employee_id, leave_category_id, requested_days):
        """Check if employee has sufficient leave balance."""
        try:
            balance = LeaveBalance.objects.get(
                tenant_id=tenant_id,
                employee_id=employee_id,
                leave_category_id=leave_category_id,
                year=timezone.now().year
            )

            if requested_days > balance.balance:
                return {
                    'valid': False,
                    'errors': {
                        'insufficient_balance': f'Insufficient leave balance. Requested: {requested_days} days, Available: {balance.balance} days'
                    }
                }
        except LeaveBalance.DoesNotExist:
            return {
                'valid': False,
                'errors': {'balance_not_found': 'Leave balance not found for current year'}
            }

        return {'valid': True, 'errors': {}}

    @staticmethod
    def _check_monthly_limits(tenant_id, employee_id, leave_category_id, start_date, end_date, policy):
        """Check monthly leave limits."""
        if not policy.limit_per_month:
            return {'valid': True, 'errors': {}}

        # Count applications in the same month
        month_start = start_date.replace(day=1)
        next_month = month_start.replace(month=month_start.month % 12 + 1, year=month_start.year + (month_start.month // 12))
        month_end = next_month - timedelta(days=1)

        monthly_count = LeaveApplication.objects.filter(
            tenant_id=tenant_id,
            employee_id=employee_id,
            leave_category_id=leave_category_id,
            start_date__gte=month_start,
            start_date__lte=month_end,
            status__in=['pending', 'approved']
        ).count()

        if monthly_count >= policy.limit_per_month:
            return {
                'valid': False,
                'errors': {
                    'monthly_limit_exceeded': f'Monthly limit of {policy.limit_per_month} applications exceeded for this leave type'
                }
            }

        return {'valid': True, 'errors': {}}

    @staticmethod
    def _check_notice_period(start_date, policy, application_data):
        """Check notice period requirements."""
        if not policy.notice_period:
            return {'valid': True, 'errors': {}}

        today = timezone.now().date()
        days_notice = (start_date - today).days

        if days_notice < policy.notice_period:
            return {
                'valid': False,
                'errors': {
                    'insufficient_notice': f'Leave must be applied at least {policy.notice_period} days in advance. Current notice: {days_notice} days'
                }
            }

        return {'valid': True, 'errors': {}}

    @staticmethod
    def _check_blackout_periods(start_date, end_date, leave_type):
        """Check for blackout periods (simplified - would need holiday calendar)."""
        warnings = []

        # For Annual leave, check for common blackout periods (simplified)
        if leave_type == 'annual':
            # Check if leave spans year-end (common blackout period)
            if start_date.year != end_date.year:
                warnings.append('Leave spans year-end - may be subject to blackout restrictions')

            # Check for peak season (December) - simplified example
            if start_date.month == 12 or end_date.month == 12:
                warnings.append('December is typically a blackout period for annual leave')

        return {'valid': True, 'warnings': warnings}

    @staticmethod
    def _check_employment_restrictions(employee_role, leave_type):
        """Check employment-based restrictions."""
        errors = {}

        # Probation restrictions (simplified - would need employment status from employee data)
        if employee_role and 'intern' in employee_role.lower():
            if leave_type in ['annual', 'casual']:
                errors['probation_restriction'] = f'Employees on probation cannot apply for {leave_type} leave'

        # Role-based restrictions
        if employee_role and leave_type == 'sabbatical':
            if not any(role in employee_role.lower() for role in ['manager', 'senior', 'lead']):
                errors['role_restriction'] = 'Sabbatical leave is typically reserved for senior roles'

        return {'valid': len(errors) == 0, 'errors': errors}

    @staticmethod
    def _check_overlapping_leaves(tenant_id, employee_id, start_date, end_date):
        """Check for overlapping leave applications."""
        queryset = LeaveApplication.objects.filter(
            tenant_id=tenant_id,
            employee_id=employee_id,
            start_date__lte=end_date,
            end_date__gte=start_date,
            status__in=['pending', 'approved']
        )

        if queryset.exists():
            return {
                'valid': False,
                'errors': {'overlap': 'Leave dates overlap with existing applications'}
            }

        return {'valid': True, 'errors': {}}

    @staticmethod
    def _get_default_approval_route(employee_role, employee_department, leave_type):
        """Get default approval route based on employee details and leave type."""
        approval_route = []

        # Default: Manager approval
        approval_route.append({
            'level': 1,
            'approver_role': 'Manager',
            'approver_name': 'Direct Manager'
        })

        # TODO: Get all role from the the other microservice.
        # For senior roles or special leave types, add additional approvals
        if employee_role and any(role in employee_role.lower() for role in ['senior', 'lead', 'manager', 'director']):
            approval_route.append({
                'level': 2,
                'approver_role': 'Department Head', 
                'approver_name': 'Department Head'
            })

        # Special leave types may require HR approval
        if leave_type in ['maternity', 'paternity', 'sabbatical']:
            approval_route.append({
                'level': len(approval_route) + 1,
                'approver_role': 'HR Manager',
                'approver_name': 'HR Manager'
            })

        # High-value annual leave may require CFO approval for encashment
        if leave_type == 'annual':
            approval_route.append({
                'level': len(approval_route) + 1,
                'approver_role': 'CFO',
                'approver_name': 'Chief Financial Officer'
            })

        return approval_route


class LeaveApprovalService:
    """Service for handling leave approval workflows."""

    @staticmethod
    def create_approval_workflow(application, approval_route):
        """
        Create approval workflow based on organizational hierarchy.

        Args:
            application: LeaveApplication instance
            approval_route: List of approval levels from policy
        """
        workflow_steps = []

        if approval_route:
            for level, approver_config in enumerate(approval_route, 1):
                workflow_steps.append({
                    'level': level,
                    'approver_id': approver_config.get('approver_id'),
                    'approver_name': approver_config.get('approver_name', ''),
                    'approver_role': approver_config.get('approver_role', ''),
                })
        else:
            # Default workflow: Immediate manager
            workflow_steps.append({
                'level': 1,
                'approver_id': None,  # To be set from org chart
                'approver_name': 'Manager',
                'approver_role': 'Manager',
            })

        with transaction.atomic():
            for step in workflow_steps:
                ApprovalWorkflow.objects.create(
                    tenant_id=application.tenant_id,
                    leave_application=application,
                    **step
                )

    @staticmethod
    def process_approval(application, approver_id, action, comments=None):
        """
        Process approval/rejection of leave application.

        Args:
            application: LeaveApplication instance
            approver_id: ID of the approver
            action: 'approve' or 'reject'
            comments: Optional comments

        Returns:
            dict: Result of the approval process
        """
        try:
            workflow = ApprovalWorkflow.objects.get(
                leave_application=application,
                approver_id=approver_id,
                status='pending'
            )
        except ApprovalWorkflow.DoesNotExist:
            return {
                'success': False,
                'error': 'No pending approval found for this application'
            }

        with transaction.atomic():
            if action == 'approve':
                workflow.status = 'approved'
                workflow.comments = comments or ''
                workflow.approved_at = timezone.now()
                workflow.save()

                # Check if all approvals are complete (excluding the one we just approved)
                pending_workflows = ApprovalWorkflow.objects.filter(
                    leave_application=application,
                    status='pending'
                ).exclude(pk=workflow.pk).exists()

                if not pending_workflows:
                    application.status = 'approved'
                    application.save()

                    # Update leave balance
                    LeaveApprovalService._update_leave_balance(application)

            elif action == 'reject':
                workflow.status = 'rejected'
                workflow.comments = comments or ''
                workflow.approved_at = timezone.now()
                workflow.save()

                application.status = 'rejected'
                application.save()

        return {'success': True, 'status': application.status}

    @staticmethod
    def _update_leave_balance(application):
        """Update employee's leave balance after approval."""
        balance, created = LeaveBalance.objects.get_or_create(
            tenant_id=application.tenant_id,
            employee_id=application.employee_id,
            leave_category_id=application.leave_category_id,
            year=timezone.now().year,
            defaults={
                'opening_balance': 0,
                'accrued': 0,
                'used': 0,
                'carried_forward': 0,
                'encashed': 0
            }
        )

        balance.used += application.total_days
        balance.save()
