from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.db import transaction, IntegrityError
from drf_spectacular.utils import extend_schema

from apps.leave.models import LeaveApplication, ApprovalWorkflow, LeaveBalance, LeaveComment, LeaveCategory
from apps.leave.services import LeaveValidationService, LeaveApprovalService
from .serializers import (
    LeaveApplicationSerializer, LeaveApplicationCreateSerializer,
    ApprovalWorkflowSerializer, LeaveBalanceSerializer,
    LeaveCommentSerializer, LeaveCommentCreateSerializer,
    LeaveCategorySerializer, LeaveApprovalSerializer, LeaveRejectionSerializer
)
from .permissions import IsTenantUser, IsHRAdmin
from core.pagination import StandardResultsSetPagination


@extend_schema(tags=['Leave Management - Categories'])
class LeaveCategoryViewSet(viewsets.ModelViewSet):
    """ViewSet for Leave Categories management"""

    queryset = LeaveCategory.objects.none()  # For schema generation
    serializer_class = LeaveCategorySerializer
    permission_classes = [IsAuthenticated, IsTenantUser, IsHRAdmin]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['is_active', 'name']

    def get_queryset(self):
        return LeaveCategory.objects.filter(tenant_id=self.request.tenant_id)

    def perform_create(self, serializer):
        """Override to handle database integrity errors."""
        try:
            return super().perform_create(serializer)
        except IntegrityError as e:
            from rest_framework import serializers
            if 'UNIQUE constraint failed' in str(e):
                raise serializers.ValidationError({
                    'non_field_errors': ['A category with this name already exists.']
                })
            raise


@extend_schema(tags=['Leave Management - Applications'])
class LeaveApplicationViewSet(viewsets.ModelViewSet):
    """ViewSet for Leave Application management"""

    queryset = LeaveApplication.objects.none()  # For schema generation
    serializer_class = LeaveApplicationSerializer
    permission_classes = [IsAuthenticated, IsTenantUser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'leave_category_id', 'employee_id']

    def get_queryset(self):
        queryset = LeaveApplication.objects.filter(tenant_id=self.request.tenant_id)

        # Filter by user role
        if not self.request.user.is_hr and not self.request.user.is_admin:
            queryset = queryset.filter(employee_id=self.request.user.id)

        return queryset

    def get_serializer_class(self):
        if self.action == 'create':
            return LeaveApplicationCreateSerializer
        return LeaveApplicationSerializer

    @extend_schema(
        summary="Create leave application",
        description="Submit a new leave application with validation",
        request=LeaveApplicationCreateSerializer,
        responses={201: LeaveApplicationSerializer}
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Validate leave application against policies and get selected policy
        validation_result = LeaveValidationService.validate_leave_application(
            serializer.validated_data,
            request.tenant_id,
            request.user.id,
            getattr(request.user, 'role', None),
            getattr(request.user, 'department', None)
        )

        if not validation_result['valid']:
            return Response({
                'errors': validation_result['errors'],
                'warnings': validation_result.get('warnings', [])
            }, status=status.HTTP_400_BAD_REQUEST)

        # Store validation results for processing
        selected_policy = validation_result['policy']
        actions_required = validation_result.get('actions_required', [])
        leave_type = validation_result.get('leave_type', '')

        with transaction.atomic():
            application = serializer.save(
                tenant_id=request.tenant_id,
                leave_policy_id=selected_policy.id if selected_policy else None,
                employee_id=request.user.id,
                employee_name=request.user.full_name,
                employee_email=request.user.email,
                department=getattr(request.user, 'department', ''),
                position=getattr(request.user, 'position', '')
            )

            # Set documentation requirements and provided status based on validation results
            if 'require_attachment' in actions_required or 'require_medical_certificate' in actions_required:
                application.document_required = True
                application.document_provided = bool(serializer.validated_data.get('document_url'))
                application.save()

            # Create approval workflow based on policy and required actions
            approval_route = []
            if selected_policy and selected_policy.approval_route:
                approval_route = selected_policy.approval_route
            elif 'route_to_approvers' in actions_required:
                # Default approval route based on department/role
                approval_route = LeaveValidationService._get_default_approval_route(
                    getattr(request.user, 'role', ''),
                    getattr(request.user, 'department', ''),
                    leave_type
                )

            LeaveApprovalService.create_approval_workflow(application, approval_route)

            serializer = LeaveApplicationSerializer(application)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
    @extend_schema(
        summary="Cancel leave application",
        description="Cancel a pending leave application (employee only)",
        request=None,
        responses={200: LeaveApplicationSerializer}
    )
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        application = self.get_object()

        # Only the employee who created the application can cancel it
        if str(application.employee_id) != str(request.user.id):
            return Response(
                {'error': 'You can only cancel your own leave applications'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Only allow cancellation of pending applications
        if application.status not in ['draft', 'pending']:
            return Response(
                {'error': 'Only draft or pending applications can be cancelled'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update application status
        application.status = 'cancelled'
        application.is_cancelled_by_employee = True
        application.cancelled_at = timezone.now()
        application.save()

        serializer = LeaveApplicationSerializer(application)
        return Response(serializer.data)


@extend_schema(tags=['Leave Management - Balances'])
class LeaveBalanceViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for Leave Balance management"""

    queryset = LeaveBalance.objects.none()  # For schema generation
    serializer_class = LeaveBalanceSerializer
    permission_classes = [IsAuthenticated, IsTenantUser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['employee_id', 'leave_category_id', 'year']

    def get_queryset(self):
        queryset = LeaveBalance.objects.filter(tenant_id=self.request.tenant_id)

        # Users can only see their own balance unless they're HR
        if not self.request.user.is_hr and not self.request.user.is_admin:
            queryset = queryset.filter(employee_id=self.request.user.id)

        return queryset


@extend_schema(tags=['Leave Management - Approvals'])
class LeaveApprovalViewSet(viewsets.GenericViewSet):
    """ViewSet for Leave Application approval actions"""

    queryset = LeaveApplication.objects.all()
    permission_classes = [IsAuthenticated, IsTenantUser]
    serializer_class = LeaveApplicationSerializer

    def get_queryset(self):
        return LeaveApplication.objects.filter(tenant_id=self.request.tenant_id)

    @extend_schema(
        summary="Approve leave application",
        description="Approve a leave application",
        request=LeaveApprovalSerializer,
        responses={200: LeaveApplicationSerializer}
    )
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        application = self.get_object()

        # Validate input using serializer
        serializer = LeaveApprovalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comments = serializer.validated_data.get('comments', '')

        # Check if user can approve this application
        workflow = ApprovalWorkflow.objects.filter(
            leave_application=application,
            approver_id=request.user.id,
            status='pending'
        ).first()

        if not workflow:
            return Response(
                {'error': 'You are not authorized to approve this application'},
                status=status.HTTP_403_FORBIDDEN
            )

        result = LeaveApprovalService.process_approval(
            application, request.user.id, 'approve', comments
        )

        if result['success']:
            serializer = LeaveApplicationSerializer(application)
            return Response(serializer.data)
        else:
            return Response({'error': result['error']}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Reject leave application",
        description="Reject a leave application",
        request=LeaveRejectionSerializer,
        responses={200: LeaveApplicationSerializer}
    )
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        application = self.get_object()

        # Validate input using serializer
        serializer = LeaveRejectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comments = serializer.validated_data.get('comments', '')
        reason = serializer.validated_data.get('reason')

        workflow = ApprovalWorkflow.objects.filter(
            leave_application=application,
            approver_id=request.user.id,
            status='pending'
        ).first()

        if not workflow:
            return Response(
                {'error': 'You are not authorized to reject this application'},
                status=status.HTTP_403_FORBIDDEN
            )

        result = LeaveApprovalService.process_approval(
            application, request.user.id, 'reject', comments
        )

        if result['success']:
            serializer = LeaveApplicationSerializer(application)
            return Response(serializer.data)
        else:
            return Response({'error': result['error']}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['Leave Management - Approvals'])
class ApprovalWorkflowViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for Approval Workflow management"""

    queryset = ApprovalWorkflow.objects.none()  # For schema generation
    serializer_class = ApprovalWorkflowSerializer
    permission_classes = [IsAuthenticated, IsTenantUser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'approver_id']

    def get_queryset(self):
        return ApprovalWorkflow.objects.filter(tenant_id=self.request.tenant_id)


@extend_schema(tags=['Leave Management - Comments'])
class LeaveApplicationCommentViewSet(viewsets.GenericViewSet):
    """ViewSet for Leave Application comment actions"""

    queryset = LeaveApplication.objects.all()
    permission_classes = [IsAuthenticated, IsTenantUser]
    serializer_class = LeaveApplicationSerializer

    def get_queryset(self):
        return LeaveApplication.objects.filter(tenant_id=self.request.tenant_id)

    @extend_schema(
        summary="Get application comments",
        description="Get all comments for a leave application",
        responses={200: LeaveCommentSerializer(many=True)}
    )
    @action(detail=True, methods=['get'])
    def comments(self, request, pk=None):
        application = self.get_object()
        comments = application.comments.filter(parent_comment__isnull=True)
        serializer = LeaveCommentSerializer(comments, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Add comment",
        description="Add a comment to a leave application",
        request=LeaveCommentCreateSerializer,
        responses={201: LeaveCommentSerializer}
    )
    @action(detail=True, methods=['post'])
    def add_comment(self, request, pk=None):
        application = self.get_object()

        serializer = LeaveCommentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        serializer.save(
            tenant_id=request.tenant_id,
            leave_application=application,
            comment_by_id=request.user.id,
            comment_by_name=request.user.full_name,
            comment_by_role=getattr(request.user, 'role', 'Employee')
        )

        return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(tags=['Leave Management - Comments'])
class LeaveCommentViewSet(viewsets.ModelViewSet):
    """ViewSet for Leave Comment management"""

    queryset = LeaveComment.objects.none()  # For schema generation
    serializer_class = LeaveCommentSerializer
    permission_classes = [IsAuthenticated, IsTenantUser]

    def get_queryset(self):
        return LeaveComment.objects.filter(tenant_id=self.request.tenant_id)

    def get_serializer_class(self):
        if self.action == 'create':
            return LeaveCommentCreateSerializer
        return LeaveCommentSerializer
