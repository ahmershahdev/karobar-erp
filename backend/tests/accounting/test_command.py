from io import StringIO

import pytest
from django.core.management import call_command

from apps.accounting.models import Account, FiscalYear
from apps.tenancy.context import tenant_context
from tests.conftest import Member

pytestmark = pytest.mark.django_db


def test_set_up_books_backfills_once(owner: Member) -> None:
    out = StringIO()
    call_command("set_up_books", stdout=out)
    call_command("set_up_books", stdout=out)
    assert "for 1 business" in out.getvalue()
    assert "for 0 business" in out.getvalue()
    with tenant_context(owner.tenant):
        assert Account.objects.count() == 36
        assert FiscalYear.objects.count() == 1
