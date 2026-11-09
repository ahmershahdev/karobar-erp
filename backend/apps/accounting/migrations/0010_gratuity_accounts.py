from typing import Any

from django.db import migrations

ACCOUNTS = [
    # role, first free code from, name, type, parent group
    ("gratuity_provision", 2190, "End-of-service provision", "liability", "2100"),
    ("gratuity_expense", 6160, "End-of-service benefits", "expense", "6000"),
]


def add_roles(apps: Any, schema_editor: Any) -> None:
    """Businesses created before end-of-service gratuity have no accounts for it."""
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
    dependencies = [("accounting", "0009_contribution_accounts")]

    operations = [migrations.RunPython(add_roles, migrations.RunPython.noop)]
