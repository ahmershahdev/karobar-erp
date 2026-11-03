from typing import Any

from django.db import migrations

# Businesses created before purchasing existed have no account for these roles; new ones get
# them from the standard chart. Codes move up if the business already used them.
ROLES = [
    ("grni", "2160", "Goods received not invoiced", "liability", "2100"),
    ("purchase_variance", "5300", "Purchase price variance", "expense", "5000"),
]


def add_roles(apps: Any, schema_editor: Any) -> None:
    Account = apps.get_model("accounting", "Account")
    tenant_ids = Account.objects.values_list("tenant_id", flat=True).distinct()
    for tenant_id in tenant_ids:
        accounts = Account.objects.filter(tenant_id=tenant_id)
        for role, code, name, kind, parent_code in ROLES:
            if accounts.filter(role=role).exists():
                continue
            number = int(code)
            while accounts.filter(code=str(number)).exists():
                number += 1
            Account.objects.create(
                tenant_id=tenant_id,
                code=str(number),
                name=name,
                type=kind,
                role=role,
                parent=accounts.filter(code=parent_code, is_group=True).first(),
            )


class Migration(migrations.Migration):
    dependencies = [("accounting", "0001_initial")]

    operations = [migrations.RunPython(add_roles, migrations.RunPython.noop)]
