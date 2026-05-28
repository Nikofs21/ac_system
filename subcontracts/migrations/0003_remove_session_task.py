from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('subcontracts', '0002_subcontract_uid_rut'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='subcontractsession',
            name='task',
        ),
    ]
