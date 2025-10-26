"""
API tests for policy endpoints.
"""

import uuid
import json
from django.test import TestCase, override_settings
from django.urls import reverse
from django.conf import settings
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from apps.policy.models import Policy
from apps.policy.factories import PolicyFactory
from apps.leave.models import LeaveCategory


class PolicyAPITestCase(APITestCase):
    """Custom test case that disables tenant middleware for API testing."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Disable tenant middleware for all API tests
        cls.original_middleware = settings.MIDDLEWARE
        settings.MIDDLEWARE = [mw for mw in settings.MIDDLEWARE if 'TenantMiddleware' not in mw]

    @classmethod
    def tearDownClass(cls):
        # Restore original middleware
        settings.MIDDLEWARE = cls.original_middleware
        super().tearDownClass()


class MockUser:
    """Mock user object for testing."""
    def __init__(self, user_id=None, tenant_id=None, role='HR'):
        self.pk = user_id or uuid.uuid4()  # Django uses pk
        self.id = self.pk  # Also set id for compatibility
        self.tenant_id = tenant_id or uuid.uuid4()
        self.role = role
        self.is_hr = role in ['HR', 'Admin']
        self.is_admin = role == 'Admin'
        self.full_name = f"Test User {role}"
        self.email = f"test.{role.lower()}@example.com"
        self.is_authenticated = True  # Django user attribute

    def __str__(self):
        return self.full_name


class PolicyAPITest(PolicyAPITestCase):
    """Integration tests for Policy API endpoints with HTTP requests."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.client = APIClient()
        self.tenant_id = uuid.uuid4()
        self.user = MockUser(tenant_id=self.tenant_id, role='HR')

        # Manually set tenant context for django-multitenant
        from django_multitenant.utils import set_current_tenant
        set_current_tenant(self.tenant_id)

        # Authenticate the client
        self.client.force_authenticate(user=self.user)

        # Mock authentication permissions to allow access during tests
        from unittest.mock import patch

        self.auth_patches = [
            patch('rest_framework.permissions.IsAuthenticated.has_permission', return_value=True),
            patch('apps.api.v1.policy.permissions.IsTenantUser.has_permission', return_value=True),
            patch('apps.api.v1.policy.permissions.IsPolicyManager.has_permission', return_value=True),
            patch('apps.policy.services.PolicyApprovalService.create_policy_approvals')  # Mock to do nothing
        ]

        # Mock request.tenant_id access
        original_getattr = None

        def mock_getattr(self, name):
            if name == 'tenant_id':
                return self.__class__.test_tenant_id
            return original_getattr(self, name)

        # Store tenant_id on the Request class for the mock
        from rest_framework.request import Request
        Request.test_tenant_id = self.tenant_id
        original_getattr = Request.__getattr__
        Request.__getattr__ = mock_getattr

        self.request_patch = (Request, original_getattr)

        for p in self.auth_patches:
            p.start()

        # Add cleanup
        self.addCleanup(lambda: [p.stop() for p in self.auth_patches])
        self.addCleanup(lambda: setattr(self.request_patch[0], '__getattr__', self.request_patch[1]))

        # Override ViewSet get_queryset for testing
        from ..api import PolicyViewSet

        def create_test_queryset(tenant_id):
            def test_get_queryset(self):
                return Policy.objects.filter(tenant_id=tenant_id)
            return test_get_queryset

        # Patch the get_queryset method
        self.get_queryset_patch = patch.object(
            PolicyViewSet,
            'get_queryset',
            create_test_queryset(self.tenant_id)
        )
        self.get_queryset_patch.start()
        self.addCleanup(self.get_queryset_patch.stop)

        # Create test leave category
        self.leave_category = LeaveCategory.objects.create(
            tenant_id=self.tenant_id,
            name='annual',
            description='Annual leave category',
            is_active=True,
            default_entitlement_days=20,
            max_carry_forward=5,
            max_encashment_days=3,
            requires_documentation=False,
            documentation_threshold_days=3,
            notice_period_days=1,
            monthly_limit=2
        )

        # Create test policies using factory
        self.policy1 = PolicyFactory.create(
            tenant_id=self.tenant_id,
            policy_name='Annual Leave Policy',
            leave_category=self.leave_category,
            is_approved=True
        )
        self.policy2 = PolicyFactory.create(
            tenant_id=self.tenant_id,
            policy_name='Sick Leave Policy',
            leave_category=self.leave_category,
            is_approved=False
        )

    def _get_valid_policy_data(self):
        """Get valid policy data for testing."""
        return {
            'policy_name': 'Test Annual Leave Policy',
            'leave_category': str(self.leave_category.id),
            'description': 'Test policy for annual leave',
            'location': 'Head Office',
            'applies_to': ['Manager', 'Developer'],
            'excludes': ['Intern'],
            'entitlement': ['permanent'],
            'employment_duration_years': 1,
            'employment_duration_months': 0,
            'employment_duration_days': 0,
            'coverage': 'Policy covers all permanent employees',
            'reset_leave_counter': 'beginning_year',
            'carry_forward': 5,
            'carry_forward_priority': False,
            'encashment': 3,
            'encashment_priority': False,
            'calculation_base': 'monthly_basic',
            'notice_period': 3,
            'limit_per_month': 2,
            'can_apply_previous_date': False,
            'document_required': False,
            'allow_multiple_day': True,
            'allow_half_day': True,
            'allow_comment': True,
            'request_on_notice_period': False,
            'approval_route': [
                {'level': 1, 'approver_role': 'Manager'},
                {'level': 2, 'approver_role': 'HR Manager'}
            ]
        }

    def test_list_policies_integration(self):
        """Integration test: List all policies via API."""
        url = reverse('policy-list')
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('data', response.data)
        self.assertIn('results', response.data['data'])
        self.assertGreaterEqual(len(response.data['data']['results']), 2)  # Should have our 2 test policies

        # Check response structure
        policy_data = response.data['data']['results'][0]
        expected_fields = ['id', 'policy_name', 'version', 'policy_type', 'is_active', 'is_approved']
        for field in expected_fields:
            self.assertIn(field, policy_data)

    @override_settings(
        MIDDLEWARE=[mw for mw in settings.MIDDLEWARE if 'TenantMiddleware' not in mw],
        DEBUG=True
    )
    def test_get_policy_detail_integration(self):
        """Integration test: Get specific policy details via API."""
        url = reverse('policy-detail', kwargs={'pk': self.policy1.pk})
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify returned data matches the policy
        self.assertEqual(response.data['policy_name'], self.policy1.policy_name)
        self.assertEqual(response.data['policy_type'], self.policy1.policy_type)
        self.assertEqual(response.data['is_approved'], self.policy1.is_approved)
        self.assertEqual(response.data['version'], self.policy1.version)

    
    def test_create_policy_integration(self):
        """Integration test: Create new policy via API."""
        policy_data = self._get_valid_policy_data()
        url = reverse('policy-list')

        response = self.client.post(url, policy_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify policy was created in database
        created_policy = Policy.objects.get(policy_name=policy_data['policy_name'])
        self.assertEqual(created_policy.tenant_id, self.tenant_id)
        self.assertEqual(created_policy.version, 'v1.0')
        self.assertFalse(created_policy.is_approved)

        # Verify response data
        self.assertEqual(response.data['policy_name'], policy_data['policy_name'])
        self.assertEqual(response.data['version'], 'v1.0')

    
    def test_create_duplicate_policy_versioning_integration(self):
        """Integration test: Create duplicate policy names creates new versions."""
        policy_data = self._get_valid_policy_data()
        url = reverse('policy-list')

        # Create first policy
        response1 = self.client.post(url, policy_data, format='json')
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response1.data['version'], 'v1.0')

        # Create second policy with same name
        response2 = self.client.post(url, policy_data, format='json')
        self.assertEqual(response2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response2.data['version'], 'v1.1')

    
    def test_update_policy_integration(self):
        """Integration test: Update existing policy via API."""
        update_data = {
            'policy_name': self.policy1.policy_name,
            'description': 'Updated policy description',
            'carry_forward': 10,
            'notice_period': 5
        }

        url = reverse('policy-detail', kwargs={'pk': self.policy1.pk})
        response = self.client.put(url, update_data, format='json')

        # When updating an approved policy, it creates a new version (201 Created)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['description'], 'Updated policy description')
        self.assertEqual(response.data['carry_forward'], 10)

    
    def test_update_approved_policy_creates_version_integration(self):
        """Integration test: Updating approved policy creates new version."""
        # Ensure policy is approved
        self.policy1.is_approved = True
        self.policy1.save()

        update_data = {
            'policy_name': self.policy1.policy_name,
            'description': 'Modified approved policy description'
        }

        url = reverse('policy-detail', kwargs={'pk': self.policy1.pk})
        response = self.client.put(url, update_data, format='json')

        # When updating an approved policy, it creates a new version (201 Created)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['version'], 'v1.1')
        self.assertEqual(response.data['description'], 'Modified approved policy description')

        # Verify new version exists in database
        new_version_exists = Policy.objects.filter(
            tenant_id=self.tenant_id,
            policy_name=self.policy1.policy_name,
            version='v1.1'
        ).exists()
        self.assertTrue(new_version_exists)

    
    def test_delete_policy_integration(self):
        """Integration test: Delete policy via API."""
        url = reverse('policy-detail', kwargs={'pk': self.policy2.pk})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Verify policy was deleted
        with self.assertRaises(Policy.DoesNotExist):
            Policy.objects.get(pk=self.policy2.pk)

    
    def test_policy_filtering_integration(self):
        """Integration test: Test policy filtering via query parameters."""
        url = reverse('policy-list')

        # Filter by policy_type
        response = self.client.get(url, {'policy_type': 'leave_time_off'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data['data']['results']) >= 1)

        # Filter by is_active
        response = self.client.get(url, {'is_active': 'true'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Filter by is_approved
        response = self.client.get(url, {'is_approved': 'true'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        approved_policies = [p for p in response.data['data']['results'] if p.get('is_approved')]
        self.assertTrue(len(approved_policies) >= 1)

    
    def test_policy_validation_errors_integration(self):
        """Integration test: Test API validation error responses."""
        # Test encashment > carry_forward
        invalid_data = self._get_valid_policy_data()
        invalid_data['carry_forward'] = 3
        invalid_data['encashment'] = 5  # Invalid: more than carry_forward

        url = reverse('policy-list')
        response = self.client.post(url, invalid_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('encashment', response.data)

    
    def test_policy_not_found_integration(self):
        """Integration test: Test 404 responses for non-existent policies."""
        fake_uuid = str(uuid.uuid4())

        # Test GET not found
        url = reverse('policy-detail', kwargs={'pk': fake_uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Test PUT not found
        update_data = self._get_valid_policy_data()
        response = self.client.put(url, update_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Test DELETE not found
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    
    def test_policy_pagination_integration(self):
        """Integration test: Test API pagination."""
        # Create many policies to test pagination
        for i in range(15):  # Create 15 more policies
            PolicyFactory.create(
                tenant_id=self.tenant_id,
                policy_name=f'Bulk Policy {i}'
            )

        url = reverse('policy-list')

        # Test default pagination
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('data', response.data)
        self.assertIn('count', response.data['data'])
        self.assertIn('next', response.data['data'])
        self.assertIn('previous', response.data['data'])
        self.assertIn('results', response.data['data'])

        # Default page size should limit results
        self.assertLessEqual(len(response.data['data']['results']), 20)  # Assuming default page size

    def test_approve_policy_integration(self):
        """Integration test: Approve a policy via API."""
        from apps.policy.models import PolicyApproval

        # Create a policy with pending approval
        policy = PolicyFactory.create(
            tenant_id=self.tenant_id,
            policy_name='Policy to Approve',
            is_approved=False
        )

        # Create a pending approval for the policy
        approval = PolicyApproval.objects.create(
            tenant_id=self.tenant_id,
            policy=policy,
            approver_id=self.user.id,  # Use the test user as approver
            approver_role='HR Manager',
            status='pending'
        )

        # Approve the policy
        url = reverse('policy-approve', kwargs={'pk': policy.pk})
        response = self.client.post(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Response should contain the updated policy data
        self.assertIn('id', response.data)
        self.assertIn('policy_name', response.data)
        self.assertTrue(response.data['is_approved'])

        # Refresh objects from database
        policy.refresh_from_db()
        approval.refresh_from_db()

        # Check that policy is now approved
        self.assertTrue(policy.is_approved)
        self.assertEqual(policy.approved_by, self.user.id)
        self.assertIsNotNone(policy.approved_at)

        # Check that approval is marked as approved
        self.assertEqual(approval.status, 'approved')
        self.assertIsNotNone(approval.approved_at)

    def test_approve_policy_no_pending_approval_integration(self):
        """Integration test: Try to approve policy without pending approval."""
        # Create a policy without any approvals
        policy = PolicyFactory.create(
            tenant_id=self.tenant_id,
            policy_name='Policy Without Approval',
            is_approved=False
        )

        # Try to approve the policy
        url = reverse('policy-approve', kwargs={'pk': policy.pk})
        response = self.client.post(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertEqual(response.data['error'], 'No pending approval found for this policy')

    def test_reject_policy_integration(self):
        """Integration test: Reject a policy via API."""
        from apps.policy.models import PolicyApproval

        # Create a policy with pending approval
        policy = PolicyFactory.create(
            tenant_id=self.tenant_id,
            policy_name='Policy to Reject',
            is_approved=False
        )

        # Create a pending approval for the policy
        approval = PolicyApproval.objects.create(
            tenant_id=self.tenant_id,
            policy=policy,
            approver_id=self.user.id,  # Use the test user as approver
            approver_role='HR Manager',
            status='pending'
        )

        # Reject the policy with comments
        url = reverse('policy-reject', kwargs={'pk': policy.pk})
        rejection_data = {'comments': 'Policy needs revision'}
        response = self.client.post(url, rejection_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Response should contain the updated policy data
        self.assertIn('id', response.data)
        self.assertIn('policy_name', response.data)
        self.assertFalse(response.data['is_approved'])

        # Refresh objects from database
        policy.refresh_from_db()
        approval.refresh_from_db()

        # Check that policy is not approved
        self.assertFalse(policy.is_approved)

        # Check that approval is marked as rejected
        self.assertEqual(approval.status, 'rejected')
        self.assertEqual(approval.comments, 'Policy needs revision')
        self.assertIsNotNone(approval.approved_at)

    def test_reject_policy_no_pending_approval_integration(self):
        """Integration test: Try to reject policy without pending approval."""
        # Create a policy without any approvals
        policy = PolicyFactory.create(
            tenant_id=self.tenant_id,
            policy_name='Policy Without Approval for Rejection',
            is_approved=False
        )

        # Try to reject the policy
        url = reverse('policy-reject', kwargs={'pk': policy.pk})
        response = self.client.post(url, {'comments': 'Test rejection'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertEqual(response.data['error'], 'No pending approval found for this policy')

    def test_policy_versions_field_integration(self):
        """Integration test: Verify versions field returns all policy versions ordered by creation date"""
        import time

        # Create first version of policy
        policy1 = PolicyFactory.create(
            tenant_id=self.tenant_id,
            policy_name='Versioned Policy',
            policy_type='leave_time_off',
            is_approved=True
        )

        # Wait a bit to ensure different creation times
        time.sleep(0.1)

        # Create second version (update approved policy creates new version)
        policy1.is_approved = True
        policy1.save()

        update_data = {
            'policy_name': policy1.policy_name,
            'policy_type': policy1.policy_type,
            'description': 'Updated description for version 2',
            'carry_forward': 10,
        }

        url = reverse('policy-detail', kwargs={'pk': policy1.pk})
        response = self.client.put(url, update_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Get the new version that was created
        policy2 = Policy.objects.get(
            tenant_id=self.tenant_id,
            policy_name=policy1.policy_name,
            version='v1.1'
        )

        # Wait a bit more
        time.sleep(0.1)

        # Create third version
        policy2.is_approved = True
        policy2.save()

        update_data2 = {
            'policy_name': policy2.policy_name,
            'policy_type': policy2.policy_type,
            'description': 'Updated description for version 3',
            'carry_forward': 15,
        }

        url2 = reverse('policy-detail', kwargs={'pk': policy2.pk})
        response2 = self.client.put(url2, update_data2, format='json')

        self.assertEqual(response2.status_code, status.HTTP_201_CREATED)

        # Get the latest version
        policy3 = Policy.objects.get(
            tenant_id=self.tenant_id,
            policy_name=policy1.policy_name,
            version='v1.2'
        )

        # Check that the versions field contains all 3 versions in correct order (most recent first)
        url_detail = reverse('policy-detail', kwargs={'pk': policy3.pk})
        response_detail = self.client.get(url_detail, format='json')

        self.assertEqual(response_detail.status_code, status.HTTP_200_OK)
        self.assertIn('versions', response_detail.data)

        versions = response_detail.data['versions']
        self.assertEqual(len(versions), 3)  # Should have 3 versions

        # Check ordering (most recent first)
        self.assertEqual(versions[0]['version'], 'v1.2')  # Most recent
        self.assertEqual(versions[1]['version'], 'v1.1')
        self.assertEqual(versions[2]['version'], 'v1.0')  # Oldest

        # Check that all versions have the same policy_name
        for version in versions:
            self.assertEqual(version['policy_name'], 'Versioned Policy')
