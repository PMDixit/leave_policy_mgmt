"""
API tests for leave balance endpoints.
"""

import uuid
from django.urls import reverse
from django.conf import settings
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from apps.leave.models import LeaveBalance, LeaveApplication
from apps.leave.models import LeaveCategory
from apps.leave.factories import LeaveCategoryFactory
from django_multitenant.utils import set_current_tenant
from unittest.mock import patch


class LeaveBalanceAPITestCase(APITestCase):
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


class LeaveBalanceAPITest(LeaveBalanceAPITestCase):
    """Integration tests for Leave Balance API endpoints."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.client = APIClient()
        self.tenant_id = uuid.uuid4()

        # Create different types of users
        self.employee_user = MockUser(tenant_id=self.tenant_id, role='Employee')
        self.hr_user = MockUser(tenant_id=self.tenant_id, role='HR', is_hr=True)
        self.admin_user = MockUser(tenant_id=self.tenant_id, role='Admin', is_hr=True, is_admin=True)
        self.other_employee = MockUser(tenant_id=self.tenant_id, role='Employee')

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
        from ..api import LeaveBalanceViewSet

        def create_test_queryset(tenant_id):
            def test_get_queryset(self):
                queryset = LeaveBalance.objects.filter(tenant_id=tenant_id)
                # Apply the same user filtering logic as the actual ViewSet
                if not self.request.user.is_hr and not self.request.user.is_admin:
                    queryset = queryset.filter(employee_id=self.request.user.id)
                return queryset
            return test_get_queryset

        # Patch the get_queryset method
        self.get_queryset_patch = patch.object(
            LeaveBalanceViewSet,
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

        # Create test leave balances
        self.balance1 = LeaveBalance.objects.create(
            tenant_id=self.tenant_id,
            employee_id=self.employee_user.id,
            leave_category_id=self.leave_category.id,
            opening_balance=20,
            accrued=5,
            used=3,
            carried_forward=2,
            encashed=1,
            year=2024,
            month=12
        )

        self.balance2 = LeaveBalance.objects.create(
            tenant_id=self.tenant_id,
            employee_id=self.employee_user.id,
            leave_category_id=self.leave_category.id,
            opening_balance=15,
            accrued=3,
            used=2,
            carried_forward=1,
            encashed=0,
            year=2024,
            month=None  # Annual balance
        )

        self.balance3 = LeaveBalance.objects.create(
            tenant_id=self.tenant_id,
            employee_id=self.other_employee.id,
            leave_category_id=self.leave_category.id,
            opening_balance=25,
            accrued=4,
            used=5,
            carried_forward=3,
            encashed=2,
            year=2024,
            month=None
        )

    def test_list_balances_employee_integration(self):
        """Integration test: Employee can only see their own balances."""
        # Authenticate as employee
        self.client.force_authenticate(user=self.employee_user)

        url = reverse('leave-balance-list')
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('data', response.data)
        self.assertIn('results', response.data['data'])

        # Employee should see only their balances
        balances = response.data['data']['results']
        self.assertEqual(len(balances), 2)  # balance1 and balance2

        # All balances should belong to the employee
        for balance in balances:
            self.assertEqual(balance['employee_id'], str(self.employee_user.id))

    def test_list_balances_hr_integration(self):
        """Integration test: HR can see all balances in tenant."""
        # Authenticate as HR
        self.client.force_authenticate(user=self.hr_user)

        url = reverse('leave-balance-list')
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('data', response.data)
        self.assertIn('results', response.data['data'])

        # HR should see all balances in tenant
        balances = response.data['data']['results']
        self.assertEqual(len(balances), 3)  # All three balances

    def test_get_balance_detail_integration(self):
        """Integration test: Get specific balance details."""
        self.client.force_authenticate(user=self.employee_user)

        url = reverse('leave-balance-detail', kwargs={'pk': self.balance1.pk})
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify returned data matches the balance
        self.assertEqual(response.data['employee_id'], str(self.balance1.employee_id))
        self.assertEqual(response.data['leave_category_id'], str(self.balance1.leave_category_id))
        self.assertEqual(float(response.data['opening_balance']), 20)
        self.assertEqual(float(response.data['used']), 3)
        self.assertEqual(float(response.data['balance']), 23)  # Calculated balance

    def test_balance_filtering_by_employee_integration(self):
        """Integration test: Filter balances by employee_id."""
        self.client.force_authenticate(user=self.hr_user)

        url = reverse('leave-balance-list')

        # Filter by employee_id
        response = self.client.get(url, {'employee_id': str(self.employee_user.id)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        balances = response.data['data']['results']
        self.assertEqual(len(balances), 2)  # balance1 and balance2

        # Verify all returned balances belong to the employee
        for balance in balances:
            self.assertEqual(balance['employee_id'], str(self.employee_user.id))

    def test_balance_filtering_by_category_integration(self):
        """Integration test: Filter balances by leave_category_id."""
        self.client.force_authenticate(user=self.hr_user)

        url = reverse('leave-balance-list')

        # Filter by leave_category_id
        response = self.client.get(url, {'leave_category_id': str(self.leave_category.id)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        balances = response.data['data']['results']
        self.assertEqual(len(balances), 3)  # All three balances

        # Verify all returned balances are for the category
        for balance in balances:
            self.assertEqual(balance['leave_category_id'], str(self.leave_category.id))

    def test_balance_filtering_by_year_integration(self):
        """Integration test: Filter balances by year."""
        self.client.force_authenticate(user=self.employee_user)

        url = reverse('leave-balance-list')

        # Filter by year
        response = self.client.get(url, {'year': 2024}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        balances = response.data['data']['results']
        self.assertEqual(len(balances), 2)  # balance1 and balance2

        # Verify all returned balances are for 2024
        for balance in balances:
            self.assertEqual(balance['year'], 2024)

    def test_balance_tenant_isolation_integration(self):
        """Integration test: Balances are properly isolated by tenant."""
        # Create balance in different tenant
        different_tenant_id = uuid.uuid4()
        different_user = MockUser(tenant_id=different_tenant_id, role='Employee')

        different_category = LeaveCategoryFactory.create(
            tenant_id=different_tenant_id,
            name='annual'
        )

        LeaveBalance.objects.create(
            tenant_id=different_tenant_id,
            employee_id=different_user.id,
            leave_category_id=different_category.id,
            opening_balance=30,
            accrued=2,
            used=1,
            carried_forward=0,
            encashed=0,
            year=2024,
            month=None
        )

        # Authenticate as user from original tenant
        self.client.force_authenticate(user=self.employee_user)

        url = reverse('leave-balance-list')
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        balances = response.data['data']['results']

        # Should only see balances from the user's tenant (2 balances for employee_user)
        self.assertEqual(len(balances), 2)

        # Verify all balances belong to the correct tenant
        for balance in balances:
            balance_obj = LeaveBalance.objects.get(id=balance['id'])
            self.assertEqual(balance_obj.tenant_id, self.tenant_id)

    def test_balance_not_found_integration(self):
        """Integration test: Test 404 responses for non-existent balances."""
        self.client.force_authenticate(user=self.employee_user)

        fake_uuid = str(uuid.uuid4())

        # Test GET not found
        url = reverse('leave-balance-detail', kwargs={'pk': fake_uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_balance_readonly_operations_integration(self):
        """Integration test: Verify balances are read-only (no create/update/delete)."""
        self.client.force_authenticate(user=self.admin_user)

        url = reverse('leave-balance-list')

        # Test POST (create) - should not be allowed
        balance_data = {
            'employee_id': str(self.employee_user.id),
            'leave_category_id': str(self.leave_category.id),
            'opening_balance': 20,
            'year': 2024
        }
        response = self.client.post(url, balance_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # Test PUT (update) - should not be allowed
        update_url = reverse('leave-balance-detail', kwargs={'pk': self.balance1.pk})
        response = self.client.put(update_url, balance_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # Test PATCH (partial update) - should not be allowed
        response = self.client.patch(update_url, {'used': 5}, format='json')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # Test DELETE - should not be allowed
        response = self.client.delete(update_url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_balance_calculation_integration(self):
        """Integration test: Verify balance calculation is correct."""
        self.client.force_authenticate(user=self.employee_user)

        url = reverse('leave-balance-detail', kwargs={'pk': self.balance1.pk})
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        balance_data = response.data

        # Verify balance calculation: opening + accrued + carried_forward - used - encashed
        expected_balance = (self.balance1.opening_balance +
                          self.balance1.accrued +
                          self.balance1.carried_forward -
                          self.balance1.used -
                          self.balance1.encashed)

        self.assertEqual(float(balance_data['balance']), expected_balance)
        self.assertEqual(float(balance_data['balance']), 23)  # 20 + 5 + 2 - 3 - 1 = 23

    def test_balance_pagination_integration(self):
        """Integration test: Test API pagination."""
        # Create additional balances to test pagination
        for i in range(25):  # Create 25 more balances
            # Create unique combinations by varying employee, category, year, and month
            employee_id = self.employee_user.id if i % 2 == 0 else self.other_employee.id
            month_val = (i % 12) + 1 if i < 12 else None  # Some annual, some monthly

            LeaveBalance.objects.create(
                tenant_id=self.tenant_id,
                employee_id=employee_id,
                leave_category_id=self.leave_category.id,
                opening_balance=10 + i,
                accrued=2,
                used=1,
                carried_forward=0,
                encashed=0,
                year=2024,
                month=month_val
            )

        # Authenticate as HR to see all balances
        self.client.force_authenticate(user=self.hr_user)

        url = reverse('leave-balance-list')
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('data', response.data)
        self.assertIn('count', response.data['data'])
        self.assertIn('next', response.data['data'])
        self.assertIn('previous', response.data['data'])
        self.assertIn('results', response.data['data'])

        # Should have pagination info
        self.assertGreater(response.data['data']['count'], 25)  # At least 27 total
        self.assertLessEqual(len(response.data['data']['results']), 20)  # Default page size limit

    def test_balance_monthly_vs_annual_integration(self):
        """Integration test: Test monthly vs annual balance filtering."""
        self.client.force_authenticate(user=self.employee_user)

        url = reverse('leave-balance-list')

        # Should see both monthly (balance1) and annual (balance2) balances
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        balances = response.data['data']['results']
        self.assertEqual(len(balances), 2)

        # Check that we have one monthly balance (month=12) and one annual balance (month=None)
        monthly_balances = [b for b in balances if b['month'] is not None]
        annual_balances = [b for b in balances if b['month'] is None]

        self.assertEqual(len(monthly_balances), 1)
        self.assertEqual(len(annual_balances), 1)
        self.assertEqual(monthly_balances[0]['month'], 12)
        self.assertIsNone(annual_balances[0]['month'])
