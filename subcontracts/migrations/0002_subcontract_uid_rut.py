import uuid
from django.db import migrations, models


def generate_uids(apps, schema_editor):
    Subcontract = apps.get_model('subcontracts', 'Subcontract')
    for sub in Subcontract.objects.all():
        sub.uid = str(uuid.uuid4()).replace('-', '')
        sub.save()


class Migration(migrations.Migration):

    dependencies = [
        ('subcontracts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='subcontract',
            name='uid',
            field=models.CharField(max_length=64, unique=True, blank=True, default=''),
        ),
        migrations.AddField(
            model_name='subcontract',
            name='rut',
            field=models.CharField(max_length=20, blank=True, null=True),
        ),
        migrations.RunPython(generate_uids, migrations.RunPython.noop),
    ]
