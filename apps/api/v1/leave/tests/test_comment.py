"""
API tests for leave comment endpoints.
"""

import uuid
from django.urls import reverse
from django.conf import settings
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from apps.leave.models import LeaveComment, LeaveApplication
from apps.leave.models import LeaveCategory
from apps.policy.models import Policy
from apps.leave.factories import LeaveCategoryFactory
from apps.policy.factories import PolicyFactory
from django_multitenant.utils import set_current_tenant
from unittest.mock import patch


class LeaveCommentAPITestCase(APITestCase):
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


class LeaveCommentAPITest(LeaveCommentAPITestCase):
    """Integration tests for Leave Comment API endpoints."""

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
        from ..api import LeaveCommentViewSet

        def create_test_queryset(tenant_id):
            def test_get_queryset(self):
                return LeaveComment.objects.filter(tenant_id=tenant_id)
            return test_get_queryset

        # Patch the get_queryset method
        self.get_queryset_patch = patch.object(
            LeaveCommentViewSet,
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
            application_id='LA-COMMENT001',
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

        # Create test comments
        self.comment1 = LeaveComment.objects.create(
            tenant_id=self.tenant_id,
            leave_application=self.leave_application,
            comment='Please approve my leave request',
            comment_by_id=self.employee_user.id,
            comment_by_name=self.employee_user.full_name,
            comment_by_role=self.employee_user.role
        )

        self.comment2 = LeaveComment.objects.create(
            tenant_id=self.tenant_id,
            leave_application=self.leave_application,
            comment='Approved, enjoy your vacation!',
            comment_by_id=self.hr_user.id,
            comment_by_name=self.hr_user.full_name,
            comment_by_role=self.hr_user.role
        )

        # Create a reply comment
        self.comment3 = LeaveComment.objects.create(
            tenant_id=self.tenant_id,
            leave_application=self.leave_application,
            comment='Thank you!',
            comment_by_id=self.employee_user.id,
            comment_by_name=self.employee_user.full_name,
            comment_by_role=self.employee_user.role,
            parent_comment=self.comment2
        )

    def _get_valid_comment_data(self):
        """Get valid comment data for testing."""
        return {
            'comment': 'This is a test comment',
            'parent_comment': None
        }

    def test_list_comments_integration(self):
        """Integration test: List all comments."""
        self.client.force_authenticate(user=self.employee_user)

        url = reverse('leave-comment-list')
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('data', response.data)
        self.assertIn('results', response.data['data'])

        # Should have our 3 test comments
        comments = response.data['data']['results']
        self.assertEqual(len(comments), 3)

        # Check comment structure
        comment_data = comments[0]
        expected_fields = ['id', 'comment', 'comment_by_name', 'comment_by_role', 'created_at']
        for field in expected_fields:
            self.assertIn(field, comment_data)

    def test_get_comment_detail_integration(self):
        """Integration test: Get specific comment details."""
        self.client.force_authenticate(user=self.employee_user)

        url = reverse('leave-comment-detail', kwargs={'pk': self.comment1.pk})
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify returned data matches the comment
        self.assertEqual(response.data['comment'], self.comment1.comment)
        self.assertEqual(response.data['comment_by_name'], self.comment1.comment_by_name)
        self.assertEqual(response.data['comment_by_role'], self.comment1.comment_by_role)

    def test_create_comment_via_application_integration(self):
        """Integration test: Create new comment via leave application."""
        self.client.force_authenticate(user=self.employee_user)

        comment_data = self._get_valid_comment_data()
        url = reverse('leave-application-comment-add-comment', kwargs={'pk': self.leave_application.pk})

        response = self.client.post(url, comment_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify response structure
        self.assertEqual(response.data['comment'], comment_data['comment'])

        # Verify comment was created in database
        created_comment = LeaveComment.objects.get(
            comment=comment_data['comment']
        )
        self.assertEqual(created_comment.tenant_id, self.tenant_id)
        self.assertEqual(created_comment.comment_by_id, self.employee_user.id)
        self.assertEqual(created_comment.leave_application.id, self.leave_application.id)

    def test_create_reply_comment_integration(self):
        """Integration test: Create reply to existing comment via application."""
        self.client.force_authenticate(user=self.employee_user)

        reply_data = {
            'comment': 'This is a reply to the comment',
            'parent_comment': str(self.comment1.pk)
        }
        url = reverse('leave-application-comment-add-comment', kwargs={'pk': self.leave_application.pk})

        response = self.client.post(url, reply_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify comment was created in database with correct parent
        created_comment = LeaveComment.objects.get(
            comment=reply_data['comment']
        )
        self.assertEqual(created_comment.parent_comment.id, self.comment1.id)
        self.assertEqual(created_comment.tenant_id, self.tenant_id)
        self.assertEqual(created_comment.leave_application.id, self.leave_application.id)

    def test_update_comment_integration(self):
        """Integration test: Update existing comment."""
        self.client.force_authenticate(user=self.employee_user)

        update_data = {
            'comment': 'Updated comment text',
        }

        url = reverse('leave-comment-detail', kwargs={'pk': self.comment1.pk})
        response = self.client.patch(url, update_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify comment was updated
        self.comment1.refresh_from_db()
        self.assertEqual(self.comment1.comment, 'Updated comment text')

    def test_delete_comment_integration(self):
        """Integration test: Delete comment."""
        self.client.force_authenticate(user=self.employee_user)

        url = reverse('leave-comment-detail', kwargs={'pk': self.comment1.pk})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Verify comment was deleted
        with self.assertRaises(LeaveComment.DoesNotExist):
            LeaveComment.objects.get(pk=self.comment1.pk)

    def test_comment_tenant_isolation_integration(self):
        """Integration test: Comments are properly isolated by tenant."""
        # Create comment in different tenant
        different_tenant_id = uuid.uuid4()
        different_user = MockUser(tenant_id=different_tenant_id, role='Employee')

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

        LeaveComment.objects.create(
            tenant_id=different_tenant_id,
            leave_application=different_application,
            comment='Different tenant comment',
            comment_by_id=different_user.id,
            comment_by_name=different_user.full_name,
            comment_by_role=different_user.role
        )

        # Authenticate as user from original tenant
        self.client.force_authenticate(user=self.employee_user)

        url = reverse('leave-comment-list')
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        comments = response.data['data']['results']

        # Should only see comments from the user's tenant (3 comments)
        self.assertEqual(len(comments), 3)

        # Verify all comments belong to the correct tenant
        for comment in comments:
            comment_obj = LeaveComment.objects.get(id=comment['id'])
            self.assertEqual(comment_obj.tenant_id, self.tenant_id)

    def test_comment_not_found_integration(self):
        """Integration test: Test 404 responses for non-existent comments."""
        self.client.force_authenticate(user=self.employee_user)

        fake_uuid = str(uuid.uuid4())

        # Test GET not found
        url = reverse('leave-comment-detail', kwargs={'pk': fake_uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Test PUT not found
        update_data = {'comment': 'Updated'}
        response = self.client.put(url, update_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Test DELETE not found
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_comment_validation_errors_integration(self):
        """Integration test: Test validation error responses."""
        self.client.force_authenticate(user=self.employee_user)

        # Test empty comment
        invalid_data = {
            'comment': '',  # Empty comment should fail
            'parent_comment': None
        }
        url = reverse('leave-comment-list')
        response = self.client.post(url, invalid_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_comment_relationships_integration(self):
        """Integration test: Verify comment relationships and threading."""
        self.client.force_authenticate(user=self.employee_user)

        # Test that reply comments are properly linked
        reply_comment = LeaveComment.objects.get(parent_comment=self.comment2)
        self.assertEqual(reply_comment.comment, 'Thank you!')
        self.assertEqual(reply_comment.parent_comment.id, self.comment2.id)

        # Test that root comments have no parent
        root_comments = LeaveComment.objects.filter(parent_comment__isnull=True)
        self.assertEqual(len(root_comments), 2)  # comment1 and comment2

        reply_comments = LeaveComment.objects.filter(parent_comment__isnull=False)
        self.assertEqual(len(reply_comments), 1)  # comment3

    def test_comment_pagination_integration(self):
        """Integration test: Test API pagination."""
        # Create additional comments to test pagination
        for i in range(25):  # Create 25 more comments
            LeaveComment.objects.create(
                tenant_id=self.tenant_id,
                leave_application=self.leave_application,
                comment=f'Bulk comment {i}',
                comment_by_id=self.employee_user.id,
                comment_by_name=self.employee_user.full_name,
                comment_by_role=self.employee_user.role
            )

        self.client.force_authenticate(user=self.employee_user)

        url = reverse('leave-comment-list')
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('data', response.data)
        self.assertIn('count', response.data['data'])
        self.assertIn('next', response.data['data'])
        self.assertIn('previous', response.data['data'])
        self.assertIn('results', response.data['data'])

        # Should have pagination info
        self.assertGreater(response.data['data']['count'], 25)  # At least 28 total
        self.assertLessEqual(len(response.data['data']['results']), 20)  # Default page size limit

    def test_comment_data_integrity_integration(self):
        """Integration test: Verify comment data integrity and audit fields."""
        self.client.force_authenticate(user=self.employee_user)

        url = reverse('leave-comment-detail', kwargs={'pk': self.comment1.pk})
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        comment_data = response.data

        # Verify comment relationships
        self.assertEqual(comment_data['comment_by_name'], self.employee_user.full_name)
        self.assertEqual(comment_data['comment_by_role'], self.employee_user.role)

        # Verify audit field
        self.assertIsNotNone(comment_data['created_at'])
        self.assertIsNotNone(comment_data['updated_at'])

        # Verify tenant isolation
        comment_obj = LeaveComment.objects.get(id=self.comment1.id)
        self.assertEqual(comment_obj.tenant_id, self.tenant_id)
        self.assertEqual(comment_obj.leave_application.id, self.leave_application.id)
