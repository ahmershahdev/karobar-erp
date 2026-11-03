import importlib

import pytest
from django.db import connection
from django.db.migrations.loader import MigrationLoader

from apps.accounting.models import Account
from apps.tenancy.context import tenant_context
from tests.accounting.conftest import with_books
from tests.conftest import make_member

pytestmark = pytest.mark.django_db
add_roles = importlib.import_module("apps.accounting.migrations.0002_purchasing_roles").add_roles


def test_older_charts_get_the_purchasing_roles_without_code_clashes() -> None:
    member = with_books(make_member(owner=True))
    with tenant_context(member.tenant):
        Account.objects.filter(role__in=["grni", "purchase_variance"]).delete()
        Account.objects.create(code="2160", name="Someone's own account", type="liability")
    # Historical models, as a real migration gets them: plain managers, no tenant scoping.
    state = MigrationLoader(connection).project_state(("accounting", "0002_purchasing_roles"))
    add_roles(state.apps, None)
    add_roles(state.apps, None)
    with tenant_context(member.tenant):
        grni = Account.objects.get(role="grni")
        variance = Account.objects.get(role="purchase_variance")
        assert (grni.code, grni.parent and grni.parent.code) == ("2161", "2100")
        assert (variance.code, variance.type) == ("5300", "expense")
