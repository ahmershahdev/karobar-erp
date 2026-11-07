from typing import Any

from django.db import migrations


def add_role(apps: Any, schema_editor: Any) -> None:
    """Businesses created before discounts existed have no account to show them on."""
    account = apps.get_model("accounting", "Account")
    for tenant_id in account.objects.values_list("tenant_id", flat=True).distinct():
        accounts = account.objects.filter(tenant_id=tenant_id)
        if accounts.filter(role="sales_discounts").exists():
            continue
        number = 4250
        while accounts.filter(code=str(number)).exists():
            number += 1
        account.objects.create(
            tenant_id=tenant_id,
            code=str(number),
            name="Sales discounts",
            type="income",
            role="sales_discounts",
            parent=accounts.filter(code="4000", is_group=True).first(),
        )


class Migration(migrations.Migration):
    dependencies = [("accounting", "0006_entry_number_key")]

    operations = [migrations.RunPython(add_role, migrations.RunPython.noop)]
