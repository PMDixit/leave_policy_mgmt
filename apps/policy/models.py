import uuid
from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.leave.models import LeaveCategory


class Policy(models.Model):
    """Main policy model with versioning for various HR policies"""

    POLICY_TYPES = [
        ('leave_time_off', 'Leave & Time Off'),
        ('attendance_timesheet', 'Attendance & Timesheet'),
        ('compensation_payroll', 'Compensation & Payroll'),
        ('performance_management', 'Performance Management'),
        ('recruitment_onboarding', 'Recruitment & Onboarding'),
        ('training_development', 'Training & Development'),
        ('health_safety', 'Health & Safety'),
        ('compliance_legal', 'Compliance & Legal'),
        ('benefits_wellness', 'Benefits & Wellness'),
        ('other', 'Other'),
    ]

    RESET_CHOICES = [
        ('beginning_year', 'At Beginning of Year'),
        ('employment_anniversary', 'On Employment Anniversary'),
        ('no', 'No'),
    ]


    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('under_review', 'Under Review'),
        ('active', 'Active'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(help_text="Tenant/Organization ID")

    # Basic Information
    policy_name = models.CharField(max_length=200)
    version = models.CharField(max_length=20, default='v1.0')
    policy_type = models.CharField(max_length=50, choices=POLICY_TYPES, default='leave_time_off')
    description = models.TextField(max_length=500, blank=True)
    location = models.CharField(max_length=100, blank=True)

    # Document attachments
    document_url = models.URLField(blank=True, help_text="URL to uploaded policy document")
    document_name = models.CharField(max_length=255, blank=True, help_text="Original name of uploaded document")

    # Eligibility
    applies_to = models.JSONField(default=list, help_text="List of roles/departments that apply")
    excludes = models.JSONField(default=list, help_text="List of roles/departments excluded")
    entitlement = models.JSONField(default=list, help_text="Employment types: Permanent, Probation")
    employment_duration_years = models.PositiveIntegerField(default=0, help_text="Employment duration in years")
    employment_duration_months = models.PositiveIntegerField(default=0, help_text="Employment duration in months")
    employment_duration_days = models.PositiveIntegerField(default=0, help_text="Employment duration in days")
    coverage = models.CharField(max_length=100, blank=True, help_text="Coverage details for the policy")

    # Leave Configuration
    leave_category = models.ForeignKey(LeaveCategory, on_delete=models.CASCADE, related_name='policies', null=True, blank=True)
    reset_leave_counter = models.CharField(max_length=30, choices=RESET_CHOICES, default='beginning_year')
    carry_forward = models.PositiveIntegerField(default=0)
    carry_forward_priority = models.BooleanField(default=False)
    encashment = models.PositiveIntegerField(default=0)
    encashment_priority = models.BooleanField(default=False)
    calculation_base = models.CharField(max_length=100, blank=True)

    # Restrictions
    notice_period = models.PositiveIntegerField(default=3)
    limit_per_month = models.PositiveIntegerField(default=2)
    can_apply_previous_date = models.BooleanField(default=False)
    document_required = models.BooleanField(default=False)
    allow_multiple_day = models.BooleanField(default=True)
    allow_half_day = models.BooleanField(default=True)
    allow_comment = models.BooleanField(default=True)
    request_on_notice_period = models.BooleanField(default=False)

    # Approval Workflow
    approval_route = models.JSONField(default=list, help_text="Sequential approval hierarchy")

    # Status and Versioning
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', help_text="Policy status")
    is_active = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)
    approved_by = models.UUIDField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    parent_policy_id = models.UUIDField(null=True, blank=True, help_text="Parent policy ID for versioning")

    # Audit
    created_by = models.UUIDField()
    updated_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'policy'
        db_table = 'policies'
        unique_together = ['tenant_id', 'policy_name', 'version']

    def __str__(self):
        return f"{self.policy_name} {self.version} - {self.tenant_id}"

    def clean(self):
        if self.carry_forward > 365:
            raise ValidationError(_('Carry forward cannot exceed 365 days'))
        if self.encashment > self.carry_forward:
            raise ValidationError(_('Encashment cannot exceed carry forward limit'))


class PolicyApproval(models.Model):
    """Approval workflow for policy changes"""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('escalated', 'Escalated'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(help_text="Tenant/Organization ID")
    policy = models.ForeignKey(Policy, on_delete=models.CASCADE, related_name='approvals')
    approver_id = models.UUIDField(help_text="Employee ID of approver")
    approver_role = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    comments = models.TextField(blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'policy'
        db_table = 'policy_approvals'
        unique_together = ['policy', 'approver_id']

    def __str__(self):
        return f"Approval for {self.policy.policy_name} by {self.approver_id}"
