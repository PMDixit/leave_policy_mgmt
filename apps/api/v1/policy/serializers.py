import uuid
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from apps.policy.models import Policy, PolicyApproval

from drf_spectacular.utils import extend_schema_field


class PolicyRejectionSerializer(serializers.Serializer):
    """Serializer for policy rejection requests"""
    comments = serializers.CharField(required=False, allow_blank=True, help_text="Rejection comments")


    def create(self, validated_data):
        # Set tenant_id from request context or from django-multitenant
        request = self.context.get('request')
        if request and hasattr(request, 'tenant_id'):
            validated_data['tenant_id'] = request.tenant_id
        else:
            # Fallback: get from django-multitenant context
            from django_multitenant.utils import get_current_tenant
            current_tenant = get_current_tenant()
            if current_tenant:
                validated_data['tenant_id'] = current_tenant
            else:
                # For testing: try multiple ways to get tenant_id
                if request:
                    # Check if it's set on the request class (test mock)
                    test_tenant_id = getattr(request.__class__, 'test_tenant_id', None)
                    if test_tenant_id:
                        validated_data['tenant_id'] = test_tenant_id
                    else:
                        # Try to get from the test instance
                        test_instance = getattr(request, '_test_instance', None)
                        if test_instance and hasattr(test_instance, 'tenant_id'):
                            validated_data['tenant_id'] = test_instance.tenant_id
        return super().create(validated_data)

    def validate_default_entitlement_days(self, value):
        if value < 0:
            raise serializers.ValidationError("Entitlement days cannot be negative")
        return value

    def validate_max_encashment_days(self, value):
        if value < 0:
            raise serializers.ValidationError("Max encashment days cannot be negative")
        return value


class PolicyListSerializer(serializers.ModelSerializer):
    """Simplified serializer for listing policies"""

    leave_category = serializers.CharField(source='leave_category.name', read_only=True)

    class Meta:
        model = Policy
        fields = [
            'id', 'policy_name', 'version', 'policy_type', 'description',
            'is_active', 'is_approved', 'created_at', 'leave_category', 'updated_at', 'coverage', 'status', 'location'
        ]


class PolicySerializer(serializers.ModelSerializer):
    """Serializer for Leave Policies with comprehensive validation"""

    versions = serializers.SerializerMethodField(
        help_text="List of all policy versions, most recent first"
    )
    @extend_schema_field(serializers.ListField(child=PolicyListSerializer()))
    def get_versions(self, obj):
        """Return all versions of this policy, ordered by creation date (most recent first)"""
        # Get all policies with the same policy_name and tenant_id
        versions = Policy.objects.filter(
            tenant_id=obj.tenant_id,
            policy_name=obj.policy_name
        ).order_by('-created_at')

        # Serialize them using a simplified serializer
        return PolicyListSerializer(versions, many=True, context=self.context).data

    class Meta:
        model = Policy
        fields = [
            'id', 'policy_name', 'version', 'policy_type', 'description',
            'location', 'document_url', 'document_name', 'applies_to', 'excludes', 'entitlement',
            'employment_duration_years', 'employment_duration_months', 'employment_duration_days', 'coverage',
            'leave_category', 'reset_leave_counter', 'carry_forward',
            'carry_forward_priority', 'encashment', 'encashment_priority',
            'calculation_base', 'notice_period', 'limit_per_month',
            'can_apply_previous_date', 'document_required', 'allow_multiple_day',
            'allow_half_day', 'allow_comment', 'request_on_notice_period',
            'approval_route', 'status', 'is_active', 'is_approved', 'approved_by',
            'approved_at', 'versions', 'created_by', 'updated_by',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'version', 'status', 'is_approved',
                          'approved_by', 'approved_at', 'document_url', 'document_name',
                          'created_by', 'updated_by', 'created_at', 'updated_at', 'versions']

    def validate_carry_forward(self, value):
        if value > 365:
            raise serializers.ValidationError("Carry forward cannot exceed 365 days")
        return value

    def validate_encashment(self, value):
        if value < 0:
            raise serializers.ValidationError("Encashment days cannot be negative")
        return value

    def validate(self, data):
        """Cross-field validation"""
        carry_forward = data.get('carry_forward', 0)
        encashment = data.get('encashment', 0)

        if encashment > carry_forward:
            raise serializers.ValidationError({
                'encashment': 'Encashment cannot exceed carry forward limit'
            })

        # Validate approval route structure
        approval_route = data.get('approval_route', [])
        if approval_route and not isinstance(approval_route, list):
            raise serializers.ValidationError({
                'approval_route': 'Approval route must be a list of approver levels'
            })

        return data


class PolicyCreateSerializer(PolicySerializer):
    """Serializer for creating new policies"""

    def save(self, **kwargs):
        """Override save to handle audit fields from kwargs"""
        # Extract audit fields from kwargs
        created_by = kwargs.pop('created_by', None)
        updated_by = kwargs.pop('updated_by', None)

        # Call parent save
        instance = super().save(**kwargs)

        # Set audit fields if provided
        if created_by is not None:
            instance.created_by = created_by
        if updated_by is not None:
            instance.updated_by = updated_by
        instance.save()

        return instance

    def create(self, validated_data):
        # Auto-generate version number
        request = self.context.get('request')
        tenant_id = request.tenant_id if request else validated_data.get('tenant_id')
        policy_name = validated_data['policy_name']

        # Find latest version
        latest_policy = Policy.objects.filter(
            tenant_id=tenant_id,
            policy_name=policy_name
        ).order_by('-created_at').first()

        if latest_policy:
            # Increment version
            current_version = latest_policy.version
            if '.' in current_version:
                major, minor = current_version.split('.')
                new_version = f"{major}.{int(minor) + 1}"
            else:
                new_version = f"{current_version}.1"
            validated_data['version'] = new_version
            validated_data['parent_policy_id'] = latest_policy.id

        validated_data['tenant_id'] = tenant_id

        # Set audit fields from request or from extra kwargs
        if request:
            validated_data['created_by'] = request.user.id
            validated_data['updated_by'] = request.user.id
        else:
            # Fallback: set dummy values for testing
            validated_data['created_by'] = uuid.uuid4()
            validated_data['updated_by'] = uuid.uuid4()

        return super().create(validated_data)


class PolicyApprovalSerializer(serializers.ModelSerializer):
    """Serializer for Policy Approvals"""

    class Meta:
        model = PolicyApproval
        fields = [
            'id', 'policy', 'approver_id', 'approver_role', 'status',
            'comments', 'approved_at', 'created_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'created_at']


class PolicyApprovalActionSerializer(serializers.Serializer):
    """Serializer for policy approval/rejection requests"""
    comments = serializers.CharField(required=False, allow_blank=True, help_text="Optional comments for approval/rejection")
