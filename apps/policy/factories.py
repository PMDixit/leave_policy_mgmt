"""
Factory classes for policy models using Factory Boy and Faker.
"""

import uuid
import factory
from faker import Faker

from .models import Policy, PolicyApproval
from apps.leave.factories import LeaveCategoryFactory

fake = Faker()


class PolicyFactory(factory.django.DjangoModelFactory):
    """Factory for Policy model."""

    class Meta:
        model = Policy

    tenant_id = factory.LazyFunction(uuid.uuid4)
    policy_name = factory.LazyFunction(lambda: f"{fake.company()} Policy")
    policy_type = 'leave_time_off'  # Default to leave policies for testing
    description = factory.LazyFunction(lambda: fake.paragraph())
    location = factory.LazyFunction(lambda: fake.city())
    applies_to = factory.LazyFunction(lambda: [fake.job() for _ in range(fake.random_int(1, 3))])
    excludes = factory.LazyFunction(lambda: [fake.job() for _ in range(fake.random_int(0, 2))])
    entitlement = factory.LazyFunction(lambda: [fake.random_element(['permanent', 'probation', 'contract'])])
    employment_duration_years = factory.Faker('random_int', min=0, max=5)
    employment_duration_months = factory.Faker('random_int', min=0, max=11)
    employment_duration_days = factory.Faker('random_int', min=0, max=30)
    coverage = factory.LazyFunction(lambda: fake.sentence()[:99])  # Limit to 99 chars to fit max_length=100
    leave_category = factory.SubFactory(LeaveCategoryFactory)
    reset_leave_counter = factory.LazyFunction(lambda: fake.random_element(['beginning_year', 'employment_anniversary']))
    carry_forward = factory.Faker('random_int', min=0, max=10)
    carry_forward_priority = factory.Faker('boolean')
    encashment = factory.Faker('random_int', min=0, max=5)
    encashment_priority = factory.Faker('boolean')
    calculation_base = factory.LazyFunction(lambda: fake.random_element([
        'monthly_basic', 'daily_rate', 'hourly_rate'
    ]))
    notice_period = factory.Faker('random_int', min=1, max=14)
    limit_per_month = factory.Faker('random_int', min=1, max=3)
    can_apply_previous_date = factory.Faker('boolean', chance_of_getting_true=30)
    document_required = factory.Faker('boolean', chance_of_getting_true=25)
    allow_multiple_day = factory.Faker('boolean', chance_of_getting_true=80)
    allow_half_day = factory.Faker('boolean', chance_of_getting_true=70)
    allow_comment = factory.Faker('boolean', chance_of_getting_true=90)
    request_on_notice_period = factory.Faker('boolean', chance_of_getting_true=10)
    approval_route = factory.LazyFunction(lambda: [
        {'level': 1, 'approver_role': 'Manager'},
        {'level': 2, 'approver_role': 'HR Manager'}
    ])
    is_active = factory.Faker('boolean', chance_of_getting_true=85)
    is_approved = factory.Faker('boolean', chance_of_getting_true=60)
    created_by = factory.LazyFunction(uuid.uuid4)
    updated_by = factory.LazyFunction(uuid.uuid4)


class PolicyApprovalFactory(factory.django.DjangoModelFactory):
    """Factory for PolicyApproval model."""

    class Meta:
        model = PolicyApproval

    policy = factory.SubFactory(PolicyFactory)
    tenant_id = factory.SelfAttribute('policy.tenant_id')
    approver_id = factory.LazyFunction(uuid.uuid4)
    approver_role = factory.LazyFunction(lambda: fake.random_element([
        'HR Manager', 'Chief HR Officer', 'Department Head', 'Manager'
    ]))
    status = factory.LazyFunction(lambda: fake.random_element(['pending', 'approved', 'rejected']))
    comments = factory.LazyFunction(lambda: fake.sentence() if fake.boolean() else "")
