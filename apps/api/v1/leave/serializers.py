from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema_field

from apps.leave.models import LeaveApplication, ApprovalWorkflow, LeaveBalance, LeaveComment, LeaveCategory


class LeaveCategorySerializer(serializers.ModelSerializer):
    """Serializer for Leave Categories"""

    class Meta:
        model = LeaveCategory
        fields = [
            'id', 'name', 'description', 'is_active',
            'default_entitlement_days', 'max_carry_forward',
            'max_encashment_days', 'requires_documentation',
            'documentation_threshold_days', 'notice_period_days',
            'monthly_limit', 'created_at', 'updated_at', 'tenant_id'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_name(self, value):
        """Validate that category name is unique within tenant."""
        request = self.context.get('request')
        tenant_id = None

        if request and hasattr(request, 'tenant_id'):
            tenant_id = request.tenant_id
        else:
            # Fallback: get from django-multitenant context
            from django_multitenant.utils import get_current_tenant
            tenant_id = get_current_tenant()

        # Check for existing categories with this name, excluding current instance if updating
        queryset = LeaveCategory.objects.filter(tenant_id=tenant_id, name=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)

        if tenant_id and queryset.exists():
            raise serializers.ValidationError("A category with this name already exists.")

        return value


class LeaveApplicationSerializer(serializers.ModelSerializer):
    """Serializer for Leave Applications"""

    leave_dates = serializers.SerializerMethodField(help_text="Leave date range")
    leaves_docs = serializers.SerializerMethodField(help_text="Leave document URL")
    comment_replies = serializers.SerializerMethodField(help_text="Leave application comments")

    class Meta:
        model = LeaveApplication
        fields = [
            'id', 'application_id', 'employee_id', 'employee_name',
            'employee_email', 'department', 'position', 'leave_category_id',
            'leave_policy_id', 'start_date', 'end_date', 'total_days',
            'is_half_day', 'reason', 'status', 'current_approver_id',
            'approval_level', 'is_cancelled_by_employee', 'cancelled_at',
            'document_required', 'document_provided', 'document_url',
            'applied_at', 'updated_at', 'leave_dates', 'leaves_docs',
            'comment_replies'
        ]
        read_only_fields = ['id', 'tenant_id', 'status', 'application_id', 'applied_at', 'updated_at', 'leave_category_id', 'leave_policy_id', 'is_cancelled_by_employee', 'cancelled_at']

    @extend_schema_field(serializers.CharField())
    def get_leave_dates(self, obj):
        return f"{obj.start_date} to {obj.end_date}"

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_leaves_docs(self, obj):
        return obj.document_url if obj.document_url else None

    def get_comment_replies(self, obj):
        comments = obj.comments.all()
        return LeaveCommentSerializer(comments, many=True).data


class LeaveApplicationCreateSerializer(LeaveApplicationSerializer):
    """Serializer for creating leave applications"""

    class Meta:
        model = LeaveApplication
        fields = [
            'leave_category_id', 'start_date', 'end_date',
            'total_days', 'is_half_day', 'reason', 'document_url'
        ]
        read_only_fields = ['tenant_id', 'application_id', 'leave_policy_id', 'applied_at', 'updated_at']

    def create(self, validated_data):
        # Auto-generate application ID
        import uuid

        # Get tenant_id from request context or from django-multitenant
        request = self.context.get('request')
        if request and hasattr(request, 'tenant_id'):
            validated_data['tenant_id'] = request.tenant_id
        else:
            # Fallback: get from django-multitenant context
            from django_multitenant.utils import get_current_tenant
            tenant_id = get_current_tenant()
            if tenant_id:
                validated_data['tenant_id'] = tenant_id

        validated_data['application_id'] = f"LA-{uuid.uuid4().hex[:8].upper()}"

        return super().create(validated_data)

    def validate(self, data):
        """Validate date fields and total_days calculation"""
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        total_days = data.get('total_days', 1)
        is_half_day = data.get('is_half_day', False)

        # Validate required date fields
        if not start_date:
            raise serializers.ValidationError({'start_date': 'Start date is required'})
        if not end_date:
            raise serializers.ValidationError({'end_date': 'End date is required'})

        # Validate date order
        if start_date > end_date:
            raise serializers.ValidationError({'end_date': 'End date must be after or equal to start date'})

        # Calculate expected total days
        from datetime import timedelta
        date_diff = (end_date - start_date).days + 1  # +1 because inclusive
        expected_total_days = date_diff

        # Adjust for half-day
        if is_half_day:
            expected_total_days = 0.5

        # Validate total_days matches calculation
        if abs(float(total_days) - float(expected_total_days)) > 0.01:  # Allow small floating point differences
            raise serializers.ValidationError({
                'total_days': f'Total days ({total_days}) does not match date range calculation ({expected_total_days} days)'
            })

        # Validate total_days is positive
        if total_days <= 0:
            raise serializers.ValidationError({'total_days': 'Total days must be greater than 0'})

        # Validate dates are not in the past (with some grace period)
        from django.utils import timezone
        today = timezone.now().date()
        if start_date < today - timedelta(days=1):  # Allow 1 day grace for backdating
            raise serializers.ValidationError({'start_date': 'Start date cannot be more than 1 day in the past'})

        return data


class ApprovalWorkflowSerializer(serializers.ModelSerializer):
    """Serializer for Approval Workflows"""

    class Meta:
        model = ApprovalWorkflow
        fields = [
            'id', 'level', 'approver_id', 'approver_name', 'approver_role',
            'status', 'comments', 'approved_at', 'escalated_to',
            'escalated_at', 'created_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'created_at']


class LeaveBalanceSerializer(serializers.ModelSerializer):
    """Serializer for Leave Balances"""

    class Meta:
        model = LeaveBalance
        fields = [
            'id', 'employee_id', 'leave_category_id', 'opening_balance',
            'accrued', 'used', 'carried_forward', 'encashed', 'balance',
            'year', 'month', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'created_at', 'updated_at']


class LeaveCommentSerializer(serializers.ModelSerializer):
    """Serializer for Leave Comments"""

    replies = serializers.SerializerMethodField()

    class Meta:
        model = LeaveComment
        fields = [
            'id', 'comment', 'comment_by_id', 'comment_by_name',
            'comment_by_role', 'parent_comment', 'replies', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'created_at', 'updated_at']

    def get_replies(self, obj):
        replies = obj.replies.all()
        return LeaveCommentSerializer(replies, many=True).data


class LeaveCommentCreateSerializer(LeaveCommentSerializer):
    """Serializer for creating comments"""

    class Meta(LeaveCommentSerializer.Meta):
        fields = ['comment', 'parent_comment']

    def create(self, validated_data):
        # tenant_id and leave_application are passed via serializer.save() in the API view
        # If tenant_id is not provided, try to get it from context
        if 'tenant_id' not in validated_data:
            request = self.context.get('request')
            if request and hasattr(request, 'tenant_id'):
                validated_data['tenant_id'] = request.tenant_id
            else:
                # Fallback: get from django-multitenant context
                from django_multitenant.utils import get_current_tenant
                tenant_id = get_current_tenant()
                if tenant_id:
                    validated_data['tenant_id'] = tenant_id

        return super().create(validated_data)


class LeaveApprovalSerializer(serializers.Serializer):
    """Serializer for leave application approval/rejection requests"""
    comments = serializers.CharField(required=False, allow_blank=True, help_text="Optional comments for approval/rejection")


class LeaveRejectionSerializer(serializers.Serializer):
    """Serializer for leave application rejection requests"""
    comments = serializers.CharField(required=False, allow_blank=True, help_text="Rejection comments")
    reason = serializers.ChoiceField(
        choices=[
            ('insufficient_balance', 'Insufficient Leave Balance'),
            ('policy_violation', 'Policy Violation'),
            ('duplicate_request', 'Duplicate Request'),
            ('invalid_dates', 'Invalid Dates'),
            ('other', 'Other')
        ],
        required=False,
        help_text="Reason for rejection"
    )
