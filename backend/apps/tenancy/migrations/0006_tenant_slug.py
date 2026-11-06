from typing import Any

from django.db import migrations, models
from django.utils.text import slugify


def fill_slugs(apps: Any, schema_editor: Any) -> None:
    tenant_model = apps.get_model("tenancy", "Tenant")
    taken: set[str] = set()
    for tenant in tenant_model.objects.order_by("pk"):
        stem = slugify(tenant.name)[:50].strip("-") or "business"
        slug = f"{stem}-{tenant.public_id.hex[:6]}" if stem in taken else stem
        taken.add(slug)
        tenant.slug = slug
        tenant.save(update_fields=["slug"])


class Migration(migrations.Migration):
    dependencies = [("tenancy", "0005_audit_json_encoder")]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="slug",
            field=models.SlugField(max_length=60, null=True, editable=False),
        ),
        migrations.RunPython(fill_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="tenant",
            name="slug",
            field=models.SlugField(max_length=60, unique=True, editable=False),
        ),
    ]
