"""
API tests for category endpoints.
"""

import uuid
from django.test import TestCase, override_settings
from django.urls import reverse
from django.conf import settings
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from apps.leave.models import LeaveCategory
from apps.leave.factories import LeaveCategoryFactory
from unittest.mock import patch


class CategoryAPITestCase(APITestCase):
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


class LeaveCategoryAPITest(CategoryAPITestCase):
    """Integration tests for LeaveCategory API endpoints with HTTP requests."""

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
        self.auth_patches = [
            patch('rest_framework.permissions.IsAuthenticated.has_permission', return_value=True),
            patch('apps.api.v1.leave.permissions.IsTenantUser.has_permission', return_value=True),
            patch('apps.api.v1.leave.permissions.IsHRAdmin.has_permission', return_value=True)
        ]

        # Mock request.tenant_id access
        def mock_getattr(self, name):
            if name == 'tenant_id':
                return self.__class__.test_tenant_id
            # For other attributes, use the original getattr to handle them properly
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
        from ..api import LeaveCategoryViewSet

        def create_test_queryset(tenant_id):
            def test_get_queryset(self):
                return LeaveCategory.objects.filter(tenant_id=tenant_id)
            return test_get_queryset

        # Patch the get_queryset method
        self.get_queryset_patch = patch.object(
            LeaveCategoryViewSet,
            'get_queryset',
            create_test_queryset(self.tenant_id)
        )
        self.get_queryset_patch.start()
        self.addCleanup(self.get_queryset_patch.stop)

        # Create test categories using factory
        self.category1 = LeaveCategoryFactory.create(
            tenant_id=self.tenant_id,
            name='annual',
            is_active=True
        )
        self.category2 = LeaveCategoryFactory.create(
            tenant_id=self.tenant_id,
            name='sick',
            is_active=False
        )

    def _get_valid_category_data(self):
        """Get valid category data for testing."""
        return {
            'name': 'casual',
            'description': 'Casual leave category',
            'is_active': True,
            'default_entitlement_days': 10,
            'max_carry_forward': 0,
            'max_encashment_days': 0,
            'requires_documentation': False,
            'documentation_threshold_days': 0,
            'notice_period_days': 1,
            'monthly_limit': 1
        }

    def test_list_categories_integration(self):
        """Integration test: List all categories via API."""
        url = reverse('leave-category-list')
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('data', response.data)
        self.assertIn('results', response.data['data'])
        self.assertGreaterEqual(len(response.data['data']['results']), 2)  # Should have our 2 test categories

        # Check response structure
        category_data = response.data['data']['results'][0]
        expected_fields = ['id', 'name', 'description', 'is_active', 'default_entitlement_days']
        for field in expected_fields:
            self.assertIn(field, category_data)

    def test_get_category_detail_integration(self):
        """Integration test: Get specific category details via API."""
        url = reverse('leave-category-detail', kwargs={'pk': self.category1.pk})
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify returned data matches the category
        self.assertEqual(response.data['name'], self.category1.name)
        self.assertEqual(response.data['is_active'], self.category1.is_active)

    def test_create_category_integration(self):
        """Integration test: Create new category via API."""
        category_data = self._get_valid_category_data()
        category_data['tenant_id'] = str(self.tenant_id)  # Set tenant_id directly for testing
        url = reverse('leave-category-list')

        response = self.client.post(url, category_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify category was created in database
        created_category = LeaveCategory.objects.get(name=category_data['name'])
        self.assertEqual(created_category.tenant_id, self.tenant_id)
        self.assertEqual(created_category.default_entitlement_days, 10)

        # Verify response data
        self.assertEqual(response.data['name'], category_data['name'])

    def test_create_duplicate_category_integration(self):
        """Integration test: Creating category with duplicate name fails."""
        category_data = self._get_valid_category_data()
        category_data['tenant_id'] = str(self.tenant_id)  # Set tenant_id directly for testing
        url = reverse('leave-category-list')

        # Create first category
        response1 = self.client.post(url, category_data, format='json')
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)

        # Try to create duplicate (should fail due to unique constraint)
        response2 = self.client.post(url, category_data, format='json')
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)
        # The error should be about name field for unique constraint
        self.assertIn('name', response2.data)

    def test_update_category_integration(self):
        """Integration test: Update existing category via API."""
        update_data = {
            'name': self.category1.name,
            'description': 'Updated category description',
            'default_entitlement_days': 25,
            'is_active': True,
            'max_carry_forward': 7,
            'max_encashment_days': 4,
            'requires_documentation': True,
            'documentation_threshold_days': 5,
            'notice_period_days': 2,
            'monthly_limit': 3,
            'tenant_id': str(self.tenant_id)
        }

        url = reverse('leave-category-detail', kwargs={'pk': self.category1.pk})
        response = self.client.put(url, update_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['description'], 'Updated category description')
        self.assertEqual(response.data['default_entitlement_days'], 25)

    def test_delete_category_integration(self):
        """Integration test: Delete category via API."""
        url = reverse('leave-category-detail', kwargs={'pk': self.category2.pk})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Verify category was deleted
        with self.assertRaises(LeaveCategory.DoesNotExist):
            LeaveCategory.objects.get(pk=self.category2.pk)

    def test_category_filtering_integration(self):
        """Integration test: Test category filtering via query parameters."""
        url = reverse('leave-category-list')

        # Filter by is_active
        response = self.client.get(url, {'is_active': 'true'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data['data']['results']) >= 1)

        # Filter by name
        response = self.client.get(url, {'name': 'annual'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data['data']['results']) >= 1)

    def test_category_validation_errors_integration(self):
        """Integration test: Test API validation error responses."""
        # Test negative entitlement days
        invalid_data = self._get_valid_category_data()
        invalid_data['default_entitlement_days'] = -5  # Invalid negative value

        url = reverse('leave-category-list')
        response = self.client.post(url, invalid_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('default_entitlement_days', response.data)

    def test_category_not_found_integration(self):
        """Integration test: Test 404 responses for non-existent categories."""
        fake_uuid = str(uuid.uuid4())

        # Test GET not found
        url = reverse('leave-category-detail', kwargs={'pk': fake_uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Test PUT not found
        update_data = self._get_valid_category_data()
        response = self.client.put(url, update_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Test DELETE not found
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_category_pagination_integration(self):
        """Integration test: Test API pagination."""
        # Create many categories to test pagination
        for i in range(15):  # Create 15 more categories
            LeaveCategoryFactory.create(
                tenant_id=self.tenant_id,
                name=f'Bulk Category {i}'
            )

        url = reverse('leave-category-list')

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
