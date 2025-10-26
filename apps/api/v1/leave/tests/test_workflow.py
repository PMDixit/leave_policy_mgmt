"""
API tests for approval workflow endpoints.
"""

import uuid
from django.urls import reverse
from django.conf import settings
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from apps.leave.models import ApprovalWorkflow, LeaveApplication
from apps.leave.models import LeaveCategory
from apps.policy.models import Policy
from apps.leave.factories import LeaveCategoryFactory
from apps.policy.factories import PolicyFactory
from django_multitenant.utils import set_current_tenant
from unittest.mock import patch


class ApprovalWorkflowAPITestCase(APITestCase):
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


class ApprovalWorkflowAPITest(ApprovalWorkflowAPITestCase):
    """Integration tests for Approval Workflow API endpoints."""

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
        from ..api import ApprovalWorkflowViewSet

        def create_test_queryset(tenant_id):
            def test_get_queryset(self):
                return ApprovalWorkflow.objects.filter(tenant_id=tenant_id)
            return test_get_queryset

        # Patch the get_queryset method
        self.get_queryset_patch = patch.object(
            ApprovalWorkflowViewSet,
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

        # Create test leave application
        self.leave_application = LeaveApplication.objects.create(
            tenant_id=self.tenant_id,
            application_id='LA-TEST001',
            employee_id=self.employee_user.id,
            employee_name=self.employee_user.full_name,
            employee_email=self.employee_user.email,
            department=self.employee_user.department,
            position=self.employee_user.position,
            leave_category_id=self.leave_category.id,
            leave_policy_id=self.policy.id,
            start_date='2024-12-01',
            end_date='2024-12-05',
            total_days=5,
            is_half_day=False,
            reason='Vacation',
            status='pending',
            document_required=False,
            document_provided=False,
        )

        # Create test approval workflows
        self.workflow1 = ApprovalWorkflow.objects.create(
            tenant_id=self.tenant_id,
            leave_application=self.leave_application,
            level=1,
            approver_id=self.hr_user.id,
            approver_name=self.hr_user.full_name,
            approver_role='HR Manager',
            status='pending'
        )

        self.workflow2 = ApprovalWorkflow.objects.create(
            tenant_id=self.tenant_id,
            leave_application=self.leave_application,
            level=2,
            approver_id=self.admin_user.id,
            approver_name=self.admin_user.full_name,
            approver_role='Admin',
            status='pending'
        )

        # Create another leave application and workflow for variety
        self.leave_application2 = LeaveApplication.objects.create(
            tenant_id=self.tenant_id,
            application_id='LA-TEST002',
            employee_id=self.employee_user.id,
            employee_name=self.employee_user.full_name,
            employee_email=self.employee_user.email,
            department=self.employee_user.department,
            position=self.employee_user.position,
            leave_category_id=self.leave_category.id,
            leave_policy_id=self.policy.id,
            start_date='2024-12-10',
            end_date='2024-12-12',
            total_days=3,
            is_half_day=False,
            reason='Personal leave',
            status='approved',
            document_required=False,
            document_provided=False,
        )

        self.workflow3 = ApprovalWorkflow.objects.create(
            tenant_id=self.tenant_id,
            leave_application=self.leave_application2,
            level=1,
            approver_id=self.hr_user.id,
            approver_name=self.hr_user.full_name,
            approver_role='HR Manager',
            status='approved'
        )

    def test_list_workflows_integration(self):
        """Integration test: List all approval workflows."""
        self.client.force_authenticate(user=self.employee_user)

        url = reverse('approval-workflow-list')
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('data', response.data)
        self.assertIn('results', response.data['data'])

        # Should have our 3 test workflows
        workflows = response.data['data']['results']
        self.assertEqual(len(workflows), 3)

        # Check workflow structure
        workflow_data = workflows[0]
        expected_fields = ['id', 'level', 'approver_name', 'approver_role', 'status', 'comments', 'approved_at']
        for field in expected_fields:
            self.assertIn(field, workflow_data)

    def test_get_workflow_detail_integration(self):
        """Integration test: Get specific workflow details."""
        self.client.force_authenticate(user=self.employee_user)

        url = reverse('approval-workflow-detail', kwargs={'pk': self.workflow1.pk})
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify returned data matches the workflow
        self.assertEqual(response.data['level'], self.workflow1.level)
        self.assertEqual(response.data['approver_name'], self.workflow1.approver_name)
        self.assertEqual(response.data['status'], self.workflow1.status)
        self.assertEqual(response.data['approver_role'], self.workflow1.approver_role)

    def test_workflow_filtering_by_status_integration(self):
        """Integration test: Filter workflows by status."""
        self.client.force_authenticate(user=self.hr_user)

        url = reverse('approval-workflow-list')

        # Filter by pending status
        response = self.client.get(url, {'status': 'pending'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        workflows = response.data['data']['results']
        self.assertEqual(len(workflows), 2)  # workflow1 and workflow2 are pending

        # Verify all returned workflows have pending status
        for workflow in workflows:
            self.assertEqual(workflow['status'], 'pending')

        # Filter by approved status
        response = self.client.get(url, {'status': 'approved'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        workflows = response.data['data']['results']
        self.assertEqual(len(workflows), 1)  # workflow3 is approved

        # Verify returned workflow has approved status
        self.assertEqual(workflows[0]['status'], 'approved')

    def test_workflow_filtering_by_approver_integration(self):
        """Integration test: Filter workflows by approver."""
        self.client.force_authenticate(user=self.hr_user)

        url = reverse('approval-workflow-list')

        # Filter by approver_id
        response = self.client.get(url, {'approver_id': str(self.hr_user.id)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        workflows = response.data['data']['results']
        self.assertEqual(len(workflows), 2)  # workflow1 and workflow3 are assigned to HR user

        # Verify all returned workflows are assigned to the HR user
        for workflow in workflows:
            self.assertEqual(workflow['approver_id'], str(self.hr_user.id))

    def test_workflow_tenant_isolation_integration(self):
        """Integration test: Workflows are properly isolated by tenant."""
        # Create workflow in different tenant
        different_tenant_id = uuid.uuid4()
        different_user = MockUser(tenant_id=different_tenant_id, role='HR', is_hr=True)

        different_category = LeaveCategoryFactory.create(
            tenant_id=different_tenant_id,
            name='annual'
        )
        different_policy = PolicyFactory.create(
            tenant_id=different_tenant_id,
            policy_type='leave_time_off'
        )

        different_application = LeaveApplication.objects.create(
            tenant_id=different_tenant_id,
            application_id='LA-DIFF001',
            employee_id=different_user.id,
            employee_name=different_user.full_name,
            employee_email=different_user.email,
            department=different_user.department,
            position=different_user.position,
            leave_category_id=different_category.id,
            leave_policy_id=different_policy.id,
            start_date='2024-12-01',
            end_date='2024-12-03',
            total_days=3,
            is_half_day=False,
            reason='Different tenant leave',
            status='pending',
            document_required=False,
            document_provided=False,
        )

        ApprovalWorkflow.objects.create(
            tenant_id=different_tenant_id,
            leave_application=different_application,
            level=1,
            approver_id=different_user.id,
            approver_name=different_user.full_name,
            approver_role='HR Manager',
            status='pending'
        )

        # Authenticate as user from original tenant
        self.client.force_authenticate(user=self.employee_user)

        url = reverse('approval-workflow-list')
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        workflows = response.data['data']['results']

        # Should only see workflows from the user's tenant (3 workflows)
        self.assertEqual(len(workflows), 3)

        # Verify all workflows belong to the correct tenant
        for workflow in workflows:
            # Check that the workflow exists in our tenant
            workflow_obj = ApprovalWorkflow.objects.get(id=workflow['id'])
            self.assertEqual(workflow_obj.tenant_id, self.tenant_id)

    def test_workflow_not_found_integration(self):
        """Integration test: Test 404 responses for non-existent workflows."""
        self.client.force_authenticate(user=self.employee_user)

        fake_uuid = str(uuid.uuid4())

        # Test GET not found
        url = reverse('approval-workflow-detail', kwargs={'pk': fake_uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_workflow_pagination_integration(self):
        """Integration test: Test API pagination."""
        # Create additional workflows to test pagination
        for i in range(20):  # Create 20 more workflows
            ApprovalWorkflow.objects.create(
                tenant_id=self.tenant_id,
                leave_application=self.leave_application,
                level=i + 3,  # Start from level 3
                approver_id=self.employee_user.id,
                approver_name=f"Approver {i}",
                approver_role='Manager',
                status='pending'
            )

        self.client.force_authenticate(user=self.employee_user)

        url = reverse('approval-workflow-list')
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('data', response.data)
        self.assertIn('count', response.data['data'])
        self.assertIn('next', response.data['data'])
        self.assertIn('previous', response.data['data'])
        self.assertIn('results', response.data['data'])

        # Should have pagination info
        self.assertGreater(response.data['data']['count'], 20)  # At least 23 total
        self.assertLessEqual(len(response.data['data']['results']), 20)  # Default page size limit

    def test_workflow_readonly_operations_integration(self):
        """Integration test: Verify workflows are read-only (no create/update/delete)."""
        self.client.force_authenticate(user=self.admin_user)

        url = reverse('approval-workflow-list')

        # Test POST (create) - should not be allowed
        workflow_data = {
            'leave_application': str(self.leave_application.id),
            'level': 3,
            'approver_id': str(self.employee_user.id),
            'approver_name': 'Test Approver',
            'approver_role': 'Manager',
            'status': 'pending'
        }
        response = self.client.post(url, workflow_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # Test PUT (update) - should not be allowed
        update_url = reverse('approval-workflow-detail', kwargs={'pk': self.workflow1.pk})
        response = self.client.put(update_url, workflow_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # Test PATCH (partial update) - should not be allowed
        response = self.client.patch(update_url, {'status': 'approved'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # Test DELETE - should not be allowed
        response = self.client.delete(update_url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_workflow_data_integrity_integration(self):
        """Integration test: Verify workflow data integrity and relationships."""
        self.client.force_authenticate(user=self.employee_user)

        url = reverse('approval-workflow-detail', kwargs={'pk': self.workflow1.pk})
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        workflow_data = response.data

        # Verify workflow relationships
        self.assertEqual(workflow_data['level'], 1)
        self.assertEqual(workflow_data['status'], 'pending')
        self.assertEqual(workflow_data['approver_role'], 'HR Manager')

        # Verify the workflow is linked to the correct leave application
        workflow_obj = ApprovalWorkflow.objects.get(id=self.workflow1.id)
        self.assertEqual(workflow_obj.leave_application.id, self.leave_application.id)
        self.assertEqual(workflow_obj.tenant_id, self.tenant_id)

    def test_workflow_multiple_filters_integration(self):
        """Integration test: Test multiple filters combined."""
        self.client.force_authenticate(user=self.admin_user)

        url = reverse('approval-workflow-list')

        # Filter by both status and approver_id
        response = self.client.get(url, {
            'status': 'pending',
            'approver_id': str(self.admin_user.id)
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        workflows = response.data['data']['results']

        # Should only return workflow2 (pending status, assigned to admin user)
        self.assertEqual(len(workflows), 1)
        self.assertEqual(workflows[0]['id'], str(self.workflow2.id))
        self.assertEqual(workflows[0]['status'], 'pending')
        self.assertEqual(workflows[0]['approver_id'], str(self.admin_user.id))
