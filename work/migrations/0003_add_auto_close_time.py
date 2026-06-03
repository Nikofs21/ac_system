from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('work', '0002_work_migration_nullable_changed_by'),
    ]

    operations = [
        migrations.AddField(
            model_name='overtimepolicy',
            name='auto_close_time',
            field=models.TimeField(
                null=True,
                blank=True,
                help_text='Hora en que el sistema cierra sesiones abiertas automaticamente. '
                          'Debe ser posterior a normal_end_time. '
                          'El cierre escribe ended_at = normal_end_time, no esta hora.',
            ),
        ),
    ]
