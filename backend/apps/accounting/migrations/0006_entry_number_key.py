from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0005_report_indexes"),
    ]

    # The new key goes on before the old one comes off, so entry numbers stay unique throughout
    # a deploy with the API and worker still running.
    operations = [
        migrations.AddConstraint(
            model_name="journalentry",
            constraint=models.UniqueConstraint(
                fields=("number", "tenant"), name="uniq_entry_number_tenant"
            ),
        ),
        migrations.RemoveConstraint(
            model_name="journalentry",
            name="uniq_entry_number",
        ),
    ]
