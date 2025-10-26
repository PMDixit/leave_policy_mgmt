import uuid
from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


class LeaveCategory(models.Model):
    """Leave categories: Annual, Sick, Casual"""

    CATEGORY_CHOICES = [
        ('annual', 'Annual Leave'),
        ('sick', 'Sick Leave'),
        ('casual', 'Casual Leave'),
        ('maternity', 'Maternity Leave'),
        ('paternity', 'Paternity Leave'),
        ('sabbatical', 'Sabbatical'),
        ('unpaid', 'Unpaid Leave'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(help_text="Tenant/Organization ID")
    name = models.CharField(max_length=100, choices=CATEGORY_CHOICES)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    # Policy parameters (tenant-configurable)
    default_entitlement_days = models.PositiveIntegerField(default=0)
    max_carry_forward = models.PositiveIntegerField(default=0, help_text="Max days that can be carried forward")
    max_encashment_days = models.PositiveIntegerField(default=0, help_text="Max days eligible for encashment")
    requires_documentation = models.BooleanField(default=False)
    documentation_threshold_days = models.PositiveIntegerField(default=3)
    notice_period_days = models.PositiveIntegerField(default=1, help_text="Days notice required")
    monthly_limit = models.PositiveIntegerField(default=2, help_text="Max applications per month")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'leave'
        db_table = 'leave_categories'
        unique_together = ['tenant_id', 'name']

    def __str__(self):
        return f"{self.name} - {self.tenant_id}"


class LeaveApplication(models.Model):
    """Employee leave applications"""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('approved_unpaid', 'Approved (unpaid)'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
        ('partially_approved', 'Partially Approved'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField()
    application_id = models.CharField(max_length=50, unique=True, blank=True)

    # Employee Information
    employee_id = models.UUIDField()
    employee_name = models.CharField(max_length=200)
    employee_email = models.EmailField()
    department = models.CharField(max_length=100, blank=True)
    position = models.CharField(max_length=100, blank=True)

    # Leave Details
    leave_category_id = models.UUIDField()
    leave_policy_id = models.UUIDField()
    start_date = models.DateField()
    end_date = models.DateField()
    total_days = models.DecimalField(max_digits=5, decimal_places=1, default=1)
    is_half_day = models.BooleanField(default=False)
    reason = models.TextField()

    # Status and Workflow
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    current_approver_id = models.UUIDField(null=True, blank=True)
    approval_level = models.PositiveIntegerField(default=1)
    is_cancelled_by_employee = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Supporting Documents
    document_required = models.BooleanField(default=False)
    document_provided = models.BooleanField(default=False)
    document_url = models.URLField(blank=True)

    # Audit
    applied_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'leave'
        db_table = 'leave_applications'
        ordering = ['-applied_at']

    def __str__(self):
        return f"Leave Application {self.application_id} - {self.employee_name}"

    def clean(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError(_('Start date cannot be after end date'))


class ApprovalWorkflow(models.Model):
    """Approval routing for leave applications"""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('escalated', 'Escalated'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField()
    leave_application = models.ForeignKey(LeaveApplication, on_delete=models.CASCADE, related_name='approvals')

    level = models.PositiveIntegerField()
    approver_id = models.UUIDField()
    approver_name = models.CharField(max_length=200)
    approver_role = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    comments = models.TextField(blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    escalated_to = models.UUIDField(null=True, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'leave'
        db_table = 'approval_workflows'
        unique_together = ['leave_application', 'level']

    def __str__(self):
        return f"Approval Level {self.level} for {self.leave_application.application_id}"


class LeaveBalance(models.Model):
    """Employee leave balances"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField()
    employee_id = models.UUIDField()
    leave_category_id = models.UUIDField()

    # Balance Information
    opening_balance = models.DecimalField(max_digits=8, decimal_places=1, default=0)
    accrued = models.DecimalField(max_digits=8, decimal_places=1, default=0)
    used = models.DecimalField(max_digits=8, decimal_places=1, default=0)
    carried_forward = models.DecimalField(max_digits=8, decimal_places=1, default=0)
    encashed = models.DecimalField(max_digits=8, decimal_places=1, default=0)
    balance = models.DecimalField(max_digits=8, decimal_places=1, default=0)

    # Period
    year = models.PositiveIntegerField()
    month = models.PositiveIntegerField(null=True, blank=True)

    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'leave'
        db_table = 'leave_balances'
        unique_together = ['tenant_id', 'employee_id', 'leave_category_id', 'year', 'month']

    def __str__(self):
        return f"Balance for {self.employee_id} - {self.leave_category_id} ({self.year})"

    def save(self, *args, **kwargs):
        self.balance = (self.opening_balance + self.accrued + self.carried_forward) - (self.used + self.encashed)
        super().save(*args, **kwargs)


class LeaveComment(models.Model):
    """Comments and replies on leave applications"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField()
    leave_application = models.ForeignKey(LeaveApplication, on_delete=models.CASCADE, related_name='comments')

    comment = models.TextField()
    comment_by_id = models.UUIDField()
    comment_by_name = models.CharField(max_length=200)
    comment_by_role = models.CharField(max_length=100)

    # For replies
    parent_comment = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='replies')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'leave'
        db_table = 'leave_comments'
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.comment_by_name} on {self.leave_application.application_id}"
