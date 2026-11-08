from typing import Any

from django.db import migrations


def add_role(apps: Any, schema_editor: Any) -> None:
    """Businesses created before payroll have no account for what payroll keeps back."""
    account = apps.get_model("accounting", "Account")
    for tenant_id in account.objects.values_list("tenant_id", flat=True).distinct():
        accounts = account.objects.filter(tenant_id=tenant_id)
        if accounts.filter(role="payroll_deductions").exists():
            continue
        number = 2170
        while accounts.filter(code=str(number)).exists():
            number += 1
        account.objects.create(
            tenant_id=tenant_id,
            code=str(number),
            name="Payroll deductions payable",
            type="liability",
            role="payroll_deductions",
            parent=accounts.filter(code="2100", is_group=True).first(),
        )


class Migration(migrations.Migration):
    dependencies = [("accounting", "0007_sales_discounts")]

    operations = [migrations.RunPython(add_role, migrations.RunPython.noop)]
