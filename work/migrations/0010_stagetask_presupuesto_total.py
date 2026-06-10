from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('work', '0009_stagetask_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='stagetask',
            name='presupuesto_total',
            field=models.DecimalField(
                blank=True, null=True,
                max_digits=16, decimal_places=2,
                help_text='Presupuesto total de la partida (MO + materiales + otros)'
            ),
        ),
    ]
