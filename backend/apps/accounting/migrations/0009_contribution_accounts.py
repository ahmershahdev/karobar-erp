from typing import Any

from django.db import migrations

ACCOUNTS = [
    # role, first free code from, name, type, parent group
    ("contributions_payable", 2180, "EOBI and social security payable", "liability", "2100"),
    ("employer_contributions", 6150, "Employer contributions", "expense", "6000"),
]


def add_roles(apps: Any, schema_editor: Any) -> None:
    """Businesses created before EOBI and social security have no accounts for them."""
    account = apps.get_model("accounting", "Account")
    for tenant_id in account.objects.values_list("tenant_id", flat=True).distinct():
        accounts = account.objects.filter(tenant_id=tenant_id)
        for role, number, name, kind, parent in ACCOUNTS:
            if accounts.filter(role=role).exists():
                continue
            while accounts.filter(code=str(number)).exists():
                number += 1
            account.objects.create(
                tenant_id=tenant_id,
                code=str(number),
                name=name,
                type=kind,
                role=role,
                parent=accounts.filter(code=parent, is_group=True).first(),
            )


class Migration(migrations.Migration):
    dependencies = [("accounting", "0008_payroll_deductions")]

    operations = [migrations.RunPython(add_roles, migrations.RunPython.noop)]
