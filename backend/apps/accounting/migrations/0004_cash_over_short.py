from typing import Any

from django.db import migrations


def add_role(apps: Any, schema_editor: Any) -> None:
    """Businesses created before the counter existed have no account for till differences."""
    account = apps.get_model("accounting", "Account")
    for tenant_id in account.objects.values_list("tenant_id", flat=True).distinct():
        accounts = account.objects.filter(tenant_id=tenant_id)
        if accounts.filter(role="cash_over_short").exists():
            continue
        number = 6800
        while accounts.filter(code=str(number)).exists():
            number += 1
        account.objects.create(
            tenant_id=tenant_id,
            code=str(number),
            name="Cash over and short",
            type="expense",
            role="cash_over_short",
            parent=accounts.filter(code="6000", is_group=True).first(),
        )


class Migration(migrations.Migration):
    dependencies = [("accounting", "0003_taxrate")]

    operations = [migrations.RunPython(add_role, migrations.RunPython.noop)]
