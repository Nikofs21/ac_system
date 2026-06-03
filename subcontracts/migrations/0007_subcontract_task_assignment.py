"""
Migracion subcontracts 0007 — SubcontractTaskAssignment

Que hace:
1. Crea tabla subcontracts_task_assignment
2. Elimina campo reserved_stage de Subcontract
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('subcontracts', '0006_subcontracts_migration_nullable_changed_by'),
        ('work', '0004_redesign_stage_permissions'),
    ]

    operations = [

        # ── 1. Crear SubcontractTaskAssignment ────────────────────────────
        migrations.CreateModel(
            name='SubcontractTaskAssignment',
            fields=[
                ('id',         models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('is_active',  models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('subcontract', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='task_assignments',
                    to='subcontracts.subcontract',
                )),
                ('task', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='subcontract_assignments',
                    to='work.taskcatalog',
                )),
                ('reserved_stage', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='subcontract_task_assignments',
                    to='work.stage',
                    help_text='Etapa reservada bajo la cual se registran las sesiones de esta partida.',
                )),
            ],
            options={
                'verbose_name': 'Partida asignada a subcontrato',
                'verbose_name_plural': 'Partidas asignadas a subcontrato',
                'db_table': 'subcontracts_task_assignment',
            },
        ),
        migrations.AddConstraint(
            model_name='subcontracttaskassignment',
            constraint=models.UniqueConstraint(
                fields=['subcontract', 'task'],
                name='unique_task_per_subcontract'
            ),
        ),

        # ── 2. Eliminar campo reserved_stage de Subcontract ───────────────
        migrations.RemoveField(
            model_name='subcontract',
            name='reserved_stage',
        ),
    ]
