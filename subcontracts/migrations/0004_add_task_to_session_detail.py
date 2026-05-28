import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('subcontracts', '0003_remove_session_task'),
        ('work', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='subcontractsessiondetail',
            name='task',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='subcontract_details',
                to='work.taskcatalog',
                null=True,  # null temporal para que la migración no falle con filas existentes
            ),
        ),
        # Quitar null una vez agregado el campo
        migrations.AlterField(
            model_name='subcontractsessiondetail',
            name='task',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='subcontract_details',
                to='work.taskcatalog',
                null=False,
            ),
        ),
    ]
