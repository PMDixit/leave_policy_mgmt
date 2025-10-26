"""
API tests for leave application endpoints.
"""

import uuid
import json
from datetime import date, timedelta
from django.test import TestCase, override_settings
from django.urls import reverse
from django.conf import settings
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from apps.leave.models import LeaveApplication, ApprovalWorkflow, LeaveBalance, LeaveComment
from apps.leave.models import LeaveCategory
from apps.policy.models import Policy
from apps.leave.factories import LeaveCategoryFactory
from apps.policy.factories import PolicyFactory
from django_multitenant.utils import set_current_tenant
from unittest.mock import patch


class LeaveAPITestCase(APITestCase):
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
    def __init__(self, user_id=None, tenant_id=None, role='Employee', is_hr=False, is_admin=False):
        self.pk = user_id or uuid.uuid4()
        self.id = self.pk
        self.tenant_id = tenant_id or uuid.uuid4()
        self.role = role
        self.is_hr = is_hr or role in ['HR', 'Admin']
        self.is_admin = role == 'Admin'
        self.full_name = f"Test User {role}"
        self.email = f"test.{role.lower()}@example.com"
        self.department = "Engineering"
        self.position = "Developer"
        self.is_authenticated = True


class LeaveApplicationAPITest(LeaveAPITestCase):
    """Integration tests for Leave Application API endpoints with HTTP requests."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.client = APIClient()
        self.tenant_id = uuid.uuid4()

        # Create different types of users
        self.employee_user = MockUser(tenant_id=self.tenant_id, role='Employee')
        self.hr_user = MockUser(tenant_id=self.tenant_id, role='HR', is_hr=True)
        self.admin_user = MockUser(tenant_id=self.tenant_id, role='Admin', is_hr=True, is_admin=True)

        # Manually set tenant context for django-multitenant
        set_current_tenant(self.tenant_id)

        # Mock authentication permissions to allow access during tests
        self.auth_patches = [
            patch('rest_framework.permissions.IsAuthenticated.has_permission', return_value=True),
            patch('apps.api.v1.leave.permissions.IsTenantUser.has_permission', return_value=True),
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
        from ..api import LeaveApplicationViewSet

        def create_test_queryset(tenant_id):
            def test_get_queryset(self):
                return LeaveApplication.objects.filter(tenant_id=tenant_id)
            return test_get_queryset

        # Patch the get_queryset method
        self.get_queryset_patch = patch.object(
            LeaveApplicationViewSet,
            'get_queryset',
            create_test_queryset(self.tenant_id)
        )
        self.get_queryset_patch.start()
        self.addCleanup(self.get_queryset_patch.stop)

        # Create test data
        self.leave_category = LeaveCategoryFactory.create(
            tenant_id=self.tenant_id,
            name='annual'
        )
        self.policy = PolicyFactory.create(
            tenant_id=self.tenant_id,
            policy_type='leave_time_off'
        )

        # Create test leave applications
        self.application1 = self._create_leave_application(self.employee_user, 'pending')
        self.application2 = self._create_leave_application(self.employee_user, 'approved')

    def _create_leave_application(self, user, status='draft'):
        """Helper method to create a leave application."""
        from django.utils import timezone
        import random
        from string import ascii_letters, digits

        # Generate a unique application ID
        app_id = f"LA-{''.join(random.choices(ascii_letters + digits, k=8))}"

        return LeaveApplication.objects.create(
            tenant_id=self.tenant_id,
            application_id=app_id,
            employee_id=user.id,
            employee_name=user.full_name,
            employee_email=user.email,
            department=user.department,
            position=user.position,
            leave_category_id=self.leave_category.id,
            leave_policy_id=self.policy.id,
            start_date=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=10),
            total_days=4,
            is_half_day=False,
            reason="Family vacation",
            status=status,
            document_required=False,
            document_provided=False,
        )

    def _get_valid_application_data(self):
        """Get valid leave application data for testing."""
        return {
            'leave_category_id': str(self.leave_category.id),
            'start_date': (date.today() + timedelta(days=7)).isoformat(),
            'end_date': (date.today() + timedelta(days=10)).isoformat(),
            'total_days': 4,
            'is_half_day': False,
            'reason': 'Medical appointment',
            'document_required': False,
            'document_provided': False,
        }

    def test_list_applications_employee_integration(self):
        """Integration test: Employee can only see their own applications."""
        # Authenticate as employee
        self.client.force_authenticate(user=self.employee_user)

        url = reverse('leave-application-list')
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('data', response.data)
        self.assertIn('results', response.data['data'])

        # Employee should see their applications
        applications = response.data['data']['results']
        self.assertTrue(len(applications) >= 2)

        # All applications should belong to the employee
        for app in applications:
            self.assertEqual(app['employee_id'], str(self.employee_user.id))

    def test_list_applications_hr_integration(self):
        """Integration test: HR can see all applications."""
        # Authenticate as HR
        self.client.force_authenticate(user=self.hr_user)

        url = reverse('leave-application-list')
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('data', response.data)
        self.assertIn('results', response.data['data'])

        # HR should see all applications in tenant
        applications = response.data['data']['results']
        self.assertTrue(len(applications) >= 2)

    def test_get_application_detail_integration(self):
        """Integration test: Get specific application details."""
        self.client.force_authenticate(user=self.employee_user)

        url = reverse('leave-application-detail', kwargs={'pk': self.application1.pk})
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify returned data matches the application
        self.assertEqual(response.data['application_id'], self.application1.application_id)
        self.assertEqual(response.data['employee_name'], self.application1.employee_name)
        self.assertEqual(response.data['status'], self.application1.status)

    def test_create_application_integration(self):
        """Integration test: Create new leave application."""
        self.client.force_authenticate(user=self.employee_user)

        application_data = self._get_valid_application_data()
        url = reverse('leave-application-list')

        with patch('apps.leave.services.LeaveValidationService.validate_leave_application') as mock_validate, \
             patch('apps.leave.services.LeaveApprovalService.create_approval_workflow') as mock_workflow:

            mock_validate.return_value = {'valid': True, 'errors': [], 'policy': self.policy}
            mock_workflow.return_value = None  # Mock to do nothing

            response = self.client.post(url, application_data, format='json')

            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

            # Verify response structure - now returns serializer data directly
            self.assertEqual(response.data['reason'], application_data['reason'])

            # Verify application was created in database
            created_app = LeaveApplication.objects.get(
                employee_id=self.employee_user.id,
                reason=application_data['reason']
            )
            self.assertEqual(created_app.tenant_id, self.tenant_id)
            self.assertEqual(created_app.leave_policy_id, self.policy.id)  # Policy should be auto-selected
            self.assertEqual(created_app.status, 'draft')  # Default status

    def test_create_application_validation_failure_integration(self):
        """Integration test: Create application with validation failure."""
        self.client.force_authenticate(user=self.employee_user)

        application_data = self._get_valid_application_data()
        url = reverse('leave-application-list')

        with patch('apps.leave.services.LeaveValidationService.validate_leave_application') as mock_validate, \
             patch('apps.leave.services.LeaveApprovalService.create_approval_workflow') as mock_workflow:

            mock_validate.return_value = {
                'valid': False,
                'errors': ['Insufficient leave balance', 'Invalid date range'],
                'policy': None
            }
            mock_workflow.return_value = None  # Mock to do nothing

            response = self.client.post(url, application_data, format='json')

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('errors', response.data)

    def test_create_application_no_policy_integration(self):
        """Integration test: Create application when no active policy exists for category."""
        self.client.force_authenticate(user=self.employee_user)

        # Create a new leave category without a policy
        from apps.leave.factories import LeaveCategoryFactory
        new_category = LeaveCategoryFactory.create(
            tenant_id=self.tenant_id,
            name='emergency'
        )

        application_data = self._get_valid_application_data()
        application_data['leave_category_id'] = str(new_category.id)

        url = reverse('leave-application-list')

        with patch('apps.leave.services.LeaveValidationService.validate_leave_application') as mock_validate, \
             patch('apps.leave.services.LeaveApprovalService.create_approval_workflow') as mock_workflow:

            # Mock validation to return no policy found
            mock_validate.return_value = {
                'valid': False,
                'errors': {'policy': 'No active and approved policy found for the selected leave category'},
                'warnings': [],
                'policy': None
            }
            mock_workflow.return_value = None

            response = self.client.post(url, application_data, format='json')

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('errors', response.data)
            self.assertIn('policy', response.data['errors'])

    def test_update_application_integration(self):
        """Integration test: Update existing application."""
        self.client.force_authenticate(user=self.employee_user)

        # Use PATCH instead of PUT for partial updates
        update_data = {
            'reason': 'Updated reason for leave',
        }

        url = reverse('leave-application-detail', kwargs={'pk': self.application1.pk})
        response = self.client.patch(url, update_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify application was updated
        self.application1.refresh_from_db()
        self.assertEqual(self.application1.reason, 'Updated reason for leave')

    def test_delete_application_integration(self):
        """Integration test: Delete application."""
        self.client.force_authenticate(user=self.employee_user)

        url = reverse('leave-application-detail', kwargs={'pk': self.application1.pk})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Verify application was deleted
        with self.assertRaises(LeaveApplication.DoesNotExist):
            LeaveApplication.objects.get(pk=self.application1.pk)

    def test_application_filtering_integration(self):
        """Integration test: Test application filtering."""
        self.client.force_authenticate(user=self.hr_user)

        url = reverse('leave-application-list')

        # Filter by status
        response = self.client.get(url, {'status': 'approved'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        applications = response.data['data']['results']
        for app in applications:
            self.assertEqual(app['status'], 'approved')

        # Filter by leave_category_id
        response = self.client.get(url, {'leave_category_id': str(self.leave_category.id)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        applications = response.data['data']['results']
        self.assertTrue(len(applications) >= 1)

    def test_approve_application_integration(self):
        """Integration test: Approve leave application."""
        # Create an approval workflow for the application
        workflow = ApprovalWorkflow.objects.create(
            tenant_id=self.tenant_id,
            leave_application=self.application1,
            level=1,
            approver_id=self.hr_user.id,
            approver_name=self.hr_user.full_name,
            approver_role='HR Manager',
            status='pending'
        )

        self.client.force_authenticate(user=self.hr_user)

        url = reverse('leave-approval-approve', kwargs={'pk': self.application1.pk})

        response = self.client.post(url, {'comments': 'Approved for vacation'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'approved')

        # Verify application status was updated in database
        self.application1.refresh_from_db()
        self.assertEqual(self.application1.status, 'approved')

        # Verify workflow was updated
        workflow.refresh_from_db()
        self.assertEqual(workflow.status, 'approved')
        self.assertEqual(workflow.comments, 'Approved for vacation')

    def test_approve_application_unauthorized_integration(self):
        """Integration test: Try to approve application without authorization."""
        # Create workflow for different user
        other_user = MockUser(tenant_id=self.tenant_id, role='Manager')
        workflow = ApprovalWorkflow.objects.create(
            tenant_id=self.tenant_id,
            leave_application=self.application1,
            level=1,
            approver_id=other_user.id,
            approver_name=other_user.full_name,
            approver_role='Manager',
            status='pending'
        )

        self.client.force_authenticate(user=self.employee_user)  # Wrong user

        url = reverse('leave-approval-approve', kwargs={'pk': self.application1.pk})
        response = self.client.post(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('error', response.data)

    def test_reject_application_integration(self):
        """Integration test: Reject leave application."""
        # Create an approval workflow for the application
        workflow = ApprovalWorkflow.objects.create(
            tenant_id=self.tenant_id,
            leave_application=self.application1,
            level=1,
            approver_id=self.hr_user.id,
            approver_name=self.hr_user.full_name,
            approver_role='HR Manager',
            status='pending'
        )

        self.client.force_authenticate(user=self.hr_user)

        url = reverse('leave-approval-reject', kwargs={'pk': self.application1.pk})

        response = self.client.post(url, {'comments': 'Insufficient balance'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'rejected')

        # Verify application status was updated in database
        self.application1.refresh_from_db()
        self.assertEqual(self.application1.status, 'rejected')

        # Verify workflow was updated
        workflow.refresh_from_db()
        self.assertEqual(workflow.status, 'rejected')
        self.assertEqual(workflow.comments, 'Insufficient balance')

    def test_add_comment_integration(self):
        """Integration test: Add comment to leave application."""
        self.client.force_authenticate(user=self.employee_user)

        url = reverse('leave-application-comment-add-comment', kwargs={'pk': self.application1.pk})

        comment_data = {
            'comment': 'Please approve my leave request',
            'parent_comment': None
        }

        response = self.client.post(url, comment_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['comment'], comment_data['comment'])

        # Verify comment was created
        comment = LeaveComment.objects.get(
            leave_application=self.application1,
            comment=comment_data['comment']
        )
        self.assertEqual(comment.comment_by_id, self.employee_user.id)

    def test_get_comments_integration(self):
        """Integration test: Get comments for leave application."""
        # Create a comment first
        comment = LeaveComment.objects.create(
            tenant_id=self.tenant_id,
            leave_application=self.application1,
            comment='Test comment',
            comment_by_id=self.employee_user.id,
            comment_by_name=self.employee_user.full_name,
            comment_by_role=self.employee_user.role
        )

        self.client.force_authenticate(user=self.employee_user)

        url = reverse('leave-application-comment-comments', kwargs={'pk': self.application1.pk})
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data) >= 1)

    def test_application_validation_errors_integration(self):
        """Integration test: Test validation error responses."""
        self.client.force_authenticate(user=self.employee_user)

        # Test invalid date range (start after end)
        invalid_data = self._get_valid_application_data()
        invalid_data['start_date'] = (date.today() + timedelta(days=10)).isoformat()
        invalid_data['end_date'] = (date.today() + timedelta(days=7)).isoformat()

        url = reverse('leave-application-list')

        # This test is for model-level validation (like invalid dates), not service validation
        # Let the actual validation service run, but it should pass validation
        # The model validation (start_date > end_date) should cause the 400 error
        response = self.client.post(url, invalid_data, format='json')

        # Should fail at model validation level
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_application_not_found_integration(self):
        """Integration test: Test 404 responses for non-existent applications."""
        self.client.force_authenticate(user=self.employee_user)

        fake_uuid = str(uuid.uuid4())

        # Test GET not found
        url = reverse('leave-application-detail', kwargs={'pk': fake_uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Test PUT not found
        update_data = {'reason': 'Updated reason'}
        response = self.client.put(url, update_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Test DELETE not found
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)  # DELETE should return 404 for non-existent

    def test_application_pagination_integration(self):
        """Integration test: Test API pagination."""
        # Create many applications to test pagination
        for i in range(15):
            self._create_leave_application(self.employee_user, 'pending')

        self.client.force_authenticate(user=self.employee_user)

        url = reverse('leave-application-list')
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('data', response.data)
        self.assertIn('count', response.data['data'])
        self.assertIn('next', response.data['data'])
        self.assertIn('previous', response.data['data'])
        self.assertIn('results', response.data['data'])

        # Default page size should limit results
        self.assertLessEqual(len(response.data['data']['results']), 20)
