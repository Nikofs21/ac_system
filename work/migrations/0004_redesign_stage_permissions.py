"""
Migracion — Rediseno de permisos de etapa/partida

Que hace:
1. Elimina SupervisorStagePermission (apuntaba a etapas)
2. Crea SupervisorTaskPermission (apunta a partidas especificas)
3. En subcontracts: crea SubcontractTaskAssignment
4. En subcontracts: elimina campo reserved_stage de Subcontract
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('work', '0003_add_auto_close_time'),
        ('companies', '0001_initial'),
    ]

    operations = [

        # ── 1. Eliminar SupervisorStagePermission ─────────────────────────
        migrations.DeleteModel(
            name='SupervisorStagePermission',
        ),

        # ── 2. Crear SupervisorTaskPermission ─────────────────────────────
        migrations.CreateModel(
            name='SupervisorTaskPermission',
            fields=[
                ('id',         models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('is_active',  models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('site_membership', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='task_permissions',
                    to='companies.sitemembership',
                )),
                ('task', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='supervisor_permissions',
                    to='work.taskcatalog',
                )),
            ],
            options={
                'verbose_name': 'Permiso de partida por supervisor',
                'verbose_name_plural': 'Permisos de partida por supervisor',
                'db_table': 'work_supervisor_task_permission',
            },
        ),
        migrations.AddConstraint(
            model_name='supervisortaskpermission',
            constraint=models.UniqueConstraint(
                fields=['site_membership', 'task'],
                name='unique_supervisor_task_permission'
            ),
        ),
    ]
