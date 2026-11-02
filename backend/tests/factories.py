from typing import Any, cast

import factory

from apps.accounts.models import User
from apps.tenancy.models import Membership, Role, Tenant

# factory_boy has no type hints; tests call the typed create_* helpers at the bottom.

TEST_PASSWORD = "correct horse battery staple"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.test")
    full_name = factory.Faker("name")

    @factory.post_generation
    def password(self, create: bool, extracted: Any, **kwargs: Any) -> None:
        self.set_password(extracted or TEST_PASSWORD)
        if create:
            self.save()


class TenantFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Tenant

    name = factory.Sequence(lambda n: f"Invented Traders {n}")


class RoleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Role

    name = factory.Sequence(lambda n: f"Role {n}")
    permissions = factory.LazyFunction(dict)


class MembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Membership

    user = factory.SubFactory(UserFactory)
    is_owner = False


def create_user(**kwargs: Any) -> User:
    return cast(User, UserFactory(**kwargs))


def create_tenant(**kwargs: Any) -> Tenant:
    return cast(Tenant, TenantFactory(**kwargs))


def create_role(**kwargs: Any) -> Role:
    return cast(Role, RoleFactory(**kwargs))


def create_membership(**kwargs: Any) -> Membership:
    return cast(Membership, MembershipFactory(**kwargs))
