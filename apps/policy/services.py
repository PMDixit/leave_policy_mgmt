"""
Business logic services for policy management.
"""

import logging
from django.utils import timezone
from django.db import transaction

from .models import PolicyApproval

logger = logging.getLogger(__name__)


class PolicyApprovalService:
    """Service for handling policy approval workflows."""

    @staticmethod
    def create_policy_approvals(policy):
        """
        Create approval workflow for policy changes.

        Args:
            policy: Policy instance
        """
        # Define approval hierarchy (this would come from org structure)
        approval_hierarchy = [
            {'role': 'HR Manager', 'level': 1},
            {'role': 'Chief Human Resource Officer', 'level': 2},
        ]

        with transaction.atomic():
            for level_data in approval_hierarchy:
                PolicyApproval.objects.create(
                    tenant_id=policy.tenant_id,
                    policy=policy,
                    approver_role=level_data['role'],
                    # approver_id would be set based on organizational structure
                )

    @staticmethod
    def process_policy_approval(policy, approver_id, action, comments=None):
        """
        Process approval/rejection of policy.

        Args:
            policy: Policy instance
            approver_id: ID of the approver
            action: 'approve' or 'reject'
            comments: Optional comments
        """
        try:
            approval = PolicyApproval.objects.get(
                policy=policy,
                approver_id=approver_id,
                status='pending'
            )
        except PolicyApproval.DoesNotExist:
            raise ValueError('No pending approval found for this policy')

        with transaction.atomic():
            if action == 'approve':
                approval.status = 'approved'
                approval.approved_at = timezone.now()

                # Check if all approvals are complete
                pending_approvals = PolicyApproval.objects.filter(
                    policy=policy,
                    status='pending'
                ).exists()

                if not pending_approvals:
                    policy.is_approved = True
                    policy.approved_by = approver_id
                    policy.approved_at = timezone.now()
                    policy.save()

            elif action == 'reject':
                approval.status = 'rejected'
                approval.comments = comments or ''
                approval.approved_at = timezone.now()

            approval.save()
