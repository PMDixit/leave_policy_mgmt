"""
Factory classes for leave models using Factory Boy and Faker.
"""

import uuid
import factory
from faker import Faker

from .models import LeaveCategory

fake = Faker()


class LeaveCategoryFactory(factory.django.DjangoModelFactory):
    """Factory for LeaveCategory model."""

    class Meta:
        model = LeaveCategory

    tenant_id = factory.LazyFunction(uuid.uuid4)
    name = factory.LazyFunction(lambda: fake.random_element([
        'annual', 'sick', 'casual', 'maternity', 'paternity', 'sabbatical'
    ]))
    description = factory.LazyFunction(lambda: fake.sentence())
    is_active = factory.Faker('boolean', chance_of_getting_true=90)
    default_entitlement_days = factory.Faker('random_int', min=10, max=30)
    max_carry_forward = factory.Faker('random_int', min=0, max=10)
    max_encashment_days = factory.Faker('random_int', min=0, max=5)
    requires_documentation = factory.Faker('boolean', chance_of_getting_true=20)
    documentation_threshold_days = factory.Faker('random_int', min=1, max=5)
    notice_period_days = factory.Faker('random_int', min=1, max=7)
    monthly_limit = factory.Faker('random_int', min=1, max=5)
