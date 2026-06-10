from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('work', '0008_alter_chilepublicholiday_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='stagetask',
            name='subetapa',
            field=models.CharField(
                blank=True, null=True, max_length=180,
                help_text='Nombre de la subetapa'
            ),
        ),
        migrations.AddField(
            model_name='stagetask',
            name='partida_cod',
            field=models.CharField(
                blank=True, null=True, max_length=360,
                help_text='Concatenacion subetapa|partida para compatibilidad Excel RRA'
            ),
        ),
        migrations.AddField(
            model_name='stagetask',
            name='cantidad_presupuesto',
            field=models.DecimalField(
                blank=True, null=True,
                max_digits=14, decimal_places=4,
            ),
        ),
        migrations.AddField(
            model_name='stagetask',
            name='unidad_medida',
            field=models.CharField(blank=True, null=True, max_length=20),
        ),
        migrations.AddField(
            model_name='stagetask',
            name='presupuesto_mo',
            field=models.DecimalField(
                blank=True, null=True,
                max_digits=16, decimal_places=2,
            ),
        ),
        migrations.AddField(
            model_name='stagetask',
            name='tipo',
            field=models.CharField(
                max_length=20,
                choices=[('casa', 'Casa'), ('subcontrato', 'Subcontrato')],
                default='casa',
            ),
        ),
        migrations.AddField(
            model_name='stagetask',
            name='estado_partida',
            field=models.CharField(
                max_length=20,
                choices=[('activa', 'Activa'), ('inactiva', 'Inactiva')],
                default='activa',
            ),
        ),
    ]
