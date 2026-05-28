"""
Migracion 0005 — Rediseno completo de subcontratos.

Que hace:
1. Elimina subcontracts_session_detail (estructura incorrecta)
2. Elimina subcontracts_session_history (se recrea con campos nuevos)
3. Elimina subcontracts_session (se recrea sin campo task)
4. Recrea subcontracts_session limpia
5. Recrea subcontracts_session_detail con FK a session y task (sin OneToOne)
6. Crea subcontracts_personnel_slot (nuevo — trazabilidad de tiempo)
7. Recrea subcontracts_session_history
"""
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('subcontracts', '0004_add_task_to_session_detail'),
        ('companies', '0001_initial'),
        ('work', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [

        # ── 1. Borrar tablas dependientes primero ────────────────────────────
        migrations.DeleteModel(name='SubcontractSessionHistory'),
        migrations.DeleteModel(name='SubcontractSessionDetail'),
        migrations.DeleteModel(name='SubcontractSession'),

        # ── 2. Recrear SubcontractSession sin campo task ─────────────────────
        migrations.CreateModel(
            name='SubcontractSession',
            fields=[
                ('id',         models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('started_at', models.DateTimeField()),
                ('ended_at',   models.DateTimeField(blank=True, null=True)),
                ('status',     models.CharField(
                    choices=[('OPEN', 'Abierta'), ('CLOSED', 'Cerrada'), ('VOIDED', 'Anulada')],
                    default='OPEN', max_length=20
                )),
                ('notes',      models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company',    models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='subcontract_sessions',
                    to='companies.company'
                )),
                ('site',       models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='subcontract_sessions',
                    to='companies.site'
                )),
                ('subcontract', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='sessions',
                    to='subcontracts.subcontract'
                )),
                ('started_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='subcontract_sessions_started',
                    to=settings.AUTH_USER_MODEL
                )),
                ('ended_by',   models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='subcontract_sessions_ended',
                    to=settings.AUTH_USER_MODEL
                )),
            ],
            options={
                'verbose_name': 'Sesion de subcontrato',
                'verbose_name_plural': 'Sesiones de subcontrato',
                'db_table': 'subcontracts_session',
                'ordering': ['-started_at'],
            },
        ),

        # ── 3. Recrear SubcontractSessionDetail con FK (no OneToOne) ─────────
        migrations.CreateModel(
            name='SubcontractSessionDetail',
            fields=[
                ('id',         models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('unit_code',  models.CharField(default='personas', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('session',    models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='details',
                    to='subcontracts.subcontractsession'
                )),
                ('task',       models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='subcontract_details',
                    to='work.taskcatalog'
                )),
            ],
            options={
                'verbose_name': 'Detalle de sesion',
                'verbose_name_plural': 'Detalles de sesion',
                'db_table': 'subcontracts_session_detail',
            },
        ),
        migrations.AddConstraint(
            model_name='subcontractsessiondetail',
            constraint=models.UniqueConstraint(
                fields=['session', 'task'],
                name='unique_task_per_subcontract_session'
            ),
        ),

        # ── 4. Crear SubcontractPersonnelSlot (NUEVO) ─────────────────────────
        migrations.CreateModel(
            name='SubcontractPersonnelSlot',
            fields=[
                ('id',         models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('quantity',   models.PositiveIntegerField()),
                ('started_at', models.DateTimeField()),
                ('ended_at',   models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('detail',     models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='personnel_slots',
                    to='subcontracts.subcontractsessiondetail'
                )),
                ('created_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='subcontract_slots_created',
                    to=settings.AUTH_USER_MODEL
                )),
            ],
            options={
                'verbose_name': 'Tramo de personal',
                'verbose_name_plural': 'Tramos de personal',
                'db_table': 'subcontracts_personnel_slot',
                'ordering': ['detail', 'started_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='subcontractpersonnelslot',
            constraint=models.UniqueConstraint(
                fields=['detail'],
                condition=models.Q(ended_at__isnull=True),
                name='unique_active_slot_per_detail'
            ),
        ),

        # ── 5. Recrear SubcontractSessionHistory ─────────────────────────────
        migrations.CreateModel(
            name='SubcontractSessionHistory',
            fields=[
                ('id',          models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('change_type', models.CharField(
                    choices=[
                        ('START',           'Inicio'),
                        ('QUANTITY_CHANGE', 'Cambio de cantidad'),
                        ('TASK_ADDED',      'Partida agregada'),
                        ('TASK_REMOVED',    'Partida eliminada'),
                        ('CLOSE',           'Cierre'),
                        ('FORCE_CLOSE',     'Cierre forzado'),
                    ],
                    max_length=40
                )),
                ('before_json', models.JSONField(blank=True, null=True)),
                ('after_json',  models.JSONField(blank=True, null=True)),
                ('reason',      models.TextField(blank=True, null=True)),
                ('created_at',  models.DateTimeField(auto_now_add=True)),
                ('session',     models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='history',
                    to='subcontracts.subcontractsession'
                )),
                ('changed_by',  models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='subcontract_history_entries',
                    to=settings.AUTH_USER_MODEL
                )),
            ],
            options={
                'verbose_name': 'Historial de sesion',
                'verbose_name_plural': 'Historial de sesiones',
                'db_table': 'subcontracts_session_history',
                'ordering': ['session', 'created_at'],
            },
        ),
    ]
