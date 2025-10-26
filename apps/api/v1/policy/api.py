from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.db import transaction, IntegrityError
from django.db.models import Max
from drf_spectacular.utils import extend_schema

from apps.policy.models import Policy, PolicyApproval
from apps.policy.services import PolicyApprovalService
from .serializers import (
    PolicySerializer,
    PolicyCreateSerializer, PolicyListSerializer,
    PolicyApprovalSerializer, PolicyRejectionSerializer, PolicyApprovalActionSerializer
)
from .permissions import IsTenantUser, IsHRAdmin, IsPolicyManager
from core.pagination import StandardResultsSetPagination


@extend_schema(tags=['Policy Management - Policies'])
class PolicyViewSet(viewsets.ModelViewSet):
    """ViewSet for Policy management with versioning and approvals"""

    queryset = Policy.objects.none()  # For schema generation
    serializer_class = PolicySerializer
    permission_classes = [IsAuthenticated, IsTenantUser, IsPolicyManager]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['policy_type', 'is_active', 'is_approved', 'leave_category']

    def get_queryset(self):
        return Policy.objects.filter(tenant_id=self.request.tenant_id).select_related('leave_category')

    def get_serializer_class(self):
        if self.action == 'create':
            return PolicyCreateSerializer
        elif self.action == 'list':
            return PolicyListSerializer
        return PolicySerializer

    @extend_schema(
        summary="Create policy",
        description="Create a new policy with auto-versioning",
        request=PolicyCreateSerializer,
        responses={201: PolicySerializer}
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            policy = serializer.save(
                tenant_id=request.tenant_id,
                created_by=request.user.id,
                updated_by=request.user.id
            )

            # Set status to under review since approval workflow is initiated
            policy.status = 'under_review'
            policy.save()

            # Create approval workflow for policy
            PolicyApprovalService.create_policy_approvals(policy)

        serializer = PolicySerializer(policy)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Update policy",
        description="Update policy and create new version if approved policy is modified",
        request=PolicyCreateSerializer,
        responses={201: PolicySerializer}
    )
    def update(self, request, *args, **kwargs):
        instance = self.get_object()

        # If updating an approved policy, create new version
        if instance.is_approved:
            return self._create_new_version(request, instance)
        else:
            return super().update(request, *args, **kwargs)

    def _create_new_version(self, request, existing_policy):
        """Create a new version of an approved policy"""
        with transaction.atomic():
            # Create new policy version with updated data
            # Start with the existing policy data but reset approval-related fields
            new_policy_data = {
                'policy_name': existing_policy.policy_name,
                'policy_type': existing_policy.policy_type,
                'description': existing_policy.description,
                'location': existing_policy.location,
                'applies_to': existing_policy.applies_to,
                'excludes': existing_policy.excludes,
                'entitlement': existing_policy.entitlement,
                'employment_duration_years': existing_policy.employment_duration_years,
                'employment_duration_months': existing_policy.employment_duration_months,
                'employment_duration_days': existing_policy.employment_duration_days,
                'coverage': existing_policy.coverage,
                'reset_leave_counter': existing_policy.reset_leave_counter,
                'carry_forward': existing_policy.carry_forward,
                'carry_forward_priority': existing_policy.carry_forward_priority,
                'encashment': existing_policy.encashment,
                'encashment_priority': existing_policy.encashment_priority,
                'calculation_base': existing_policy.calculation_base,
                'notice_period': existing_policy.notice_period,
                'limit_per_month': existing_policy.limit_per_month,
                'can_apply_previous_date': existing_policy.can_apply_previous_date,
                'document_required': existing_policy.document_required,
                'allow_multiple_day': existing_policy.allow_multiple_day,
                'allow_half_day': existing_policy.allow_half_day,
                'allow_comment': existing_policy.allow_comment,
                'request_on_notice_period': existing_policy.request_on_notice_period,
                'approval_route': existing_policy.approval_route,
                'is_active': True,  # New versions start active
                'is_approved': False,  # New versions need approval
            }

            # Apply any updates from the request
            new_policy_data.update(request.data)

            serializer = PolicyCreateSerializer(data=new_policy_data, context={'request': request})
            serializer.is_valid(raise_exception=True)

            # Find the next version number
            latest_version = Policy.objects.filter(
                tenant_id=request.tenant_id,
                policy_name=new_policy_data['policy_name']
            ).aggregate(max_version=Max('version'))['max_version']

            if latest_version:
                if '.' in latest_version:
                    major, minor = latest_version.split('.')
                    new_version = f"{major}.{int(minor) + 1}"
                else:
                    new_version = f"{latest_version}.1"
            else:
                new_version = 'v1.0'

            # Create the policy using serializer with defaults
            new_policy_data['version'] = new_version
            new_policy_data['parent_policy_id'] = existing_policy.id
            new_policy_data['is_approved'] = False  # New versions start unapproved
            new_policy_data.setdefault('is_active', True)  # New versions are active by default

            serializer = PolicyCreateSerializer(
                data=new_policy_data,
                context={'request': request}
            )
            serializer.is_valid(raise_exception=True)
            new_policy = serializer.save(
                created_by=request.user.id,
                updated_by=request.user.id
            )

            # Set status to under review since approval workflow is initiated
            new_policy.status = 'under_review'
            new_policy.save()

            # Create approval workflow for new version
            PolicyApprovalService.create_policy_approvals(new_policy)

        serializer = PolicySerializer(new_policy)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Approve policy",
        description="Approve a policy version",
        request=PolicyApprovalActionSerializer,
        responses={200: PolicySerializer}
    )
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        policy = self.get_object()

        # Validate input using serializer
        serializer = PolicyApprovalActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comments = serializer.validated_data.get('comments', '')

        approval = PolicyApproval.objects.filter(
            policy=policy,
            approver_id=request.user.id,
            status='pending'
        ).first()

        if not approval:
            return Response(
                {'error': 'No pending approval found for this policy'},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            approval.status = 'approved'
            approval.approved_at = timezone.now()
            approval.comments = comments
            approval.save()

            # Check if all approvals are complete
            pending_approvals = PolicyApproval.objects.filter(
                policy=policy,
                status='pending'
            ).exists()

            if not pending_approvals:
                policy.is_approved = True
                policy.status = 'active'
                policy.approved_by = request.user.id
                policy.approved_at = timezone.now()
                policy.save()

        # Return the updated policy
        serializer = PolicySerializer(policy)
        return Response(serializer.data)

    @extend_schema(
        summary="Reject policy",
        description="Reject a policy version",
        request=PolicyRejectionSerializer,
        responses={200: PolicySerializer}
    )
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        policy = self.get_object()

        # Validate input using serializer
        serializer = PolicyRejectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comments = serializer.validated_data.get('comments', '')

        approval = PolicyApproval.objects.filter(
            policy=policy,
            approver_id=request.user.id,
            status='pending'
        ).first()

        if not approval:
            return Response(
                {'error': 'No pending approval found for this policy'},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            approval.status = 'rejected'
            approval.comments = comments
            approval.approved_at = timezone.now()
            approval.save()

            # Mark policy as rejected
            policy.status = 'rejected'
            policy.is_approved = False
            policy.save()

        # Return the updated policy
        serializer = PolicySerializer(policy)
        return Response(serializer.data)
