# -*- coding: utf-8 -*-
from django.db import models
from django.conf import settings


class Stage(models.Model):

    class StageType(models.TextChoices):
        NORMAL = 'NORMAL', 'Normal'
        REPROCESS = 'REPROCESS', 'Reproceso'
        RESERVED = 'RESERVED', 'Reservada'
        SUBCONTRACT_RESERVED = 'SUBCONTRACT_RESERVED', 'Reservada subcontrato'

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.PROTECT,
        related_name='stages'
    )
    site = models.ForeignKey(
        'companies.Site',
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='stages'
    )
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=40)
    stage_type = models.CharField(
        max_length=30,
        choices=StageType.choices,
        default=StageType.NORMAL
    )
    is_active = models.BooleanField(default=True)
    is_reserved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'work_stage'
        verbose_name = 'Etapa'
        verbose_name_plural = 'Etapas'
        ordering = ['company', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'site', 'name'],
                name='unique_stage_name_per_company_site'
            )
        ]

    def __str__(self):
        site_str = f' - {self.site.name}' if self.site else ''
        return f'{self.name}{site_str} ({self.company.name})'


class TaskCatalog(models.Model):

    class RiskLevel(models.TextChoices):
        NORMAL = 'NORMAL', 'Normal'
        HIGH_RISK = 'HIGH_RISK', 'Alto riesgo'

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Activa'
        INACTIVE = 'INACTIVE', 'Inactiva'

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.PROTECT,
        related_name='task_catalog'
    )
    code = models.CharField(max_length=60)
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True, null=True)
    risk_level = models.CharField(
        max_length=20,
        choices=RiskLevel.choices,
        default=RiskLevel.NORMAL
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )
    default_um = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'work_task_catalog'
        verbose_name = 'Partida'
        verbose_name_plural = 'Partidas'
        ordering = ['company', 'code']
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'code'],
                name='unique_task_code_per_company'
            )
        ]

    def __str__(self):
        return f'{self.code} - {self.name} ({self.company.name})'


class StageTask(models.Model):

    class Tipo(models.TextChoices):
        CASA         = 'casa',         'Casa'
        SUBCONTRATO  = 'subcontrato',  'Subcontrato'

    class EstadoPartida(models.TextChoices):
        ACTIVA   = 'activa',   'Activa'
        INACTIVA = 'inactiva', 'Inactiva'

    site = models.ForeignKey(
        'companies.Site',
        on_delete=models.PROTECT,
        related_name='stage_tasks'
    )
    stage = models.ForeignKey(
        Stage,
        on_delete=models.PROTECT,
        related_name='stage_tasks'
    )
    task = models.ForeignKey(
        TaskCatalog,
        on_delete=models.PROTECT,
        related_name='stage_tasks'
    )
    is_active     = models.BooleanField(default=True)
    display_order = models.IntegerField(null=True, blank=True)

    # ── Campos nuevos ────────────────────────────────────────────────────────
    subetapa = models.CharField(
        max_length=180, blank=True, null=True,
        help_text='Nombre de la subetapa. Ej: 1.2.3.3. ARMADURAS DE ACERO'
    )
    partida_cod = models.CharField(
        max_length=360, blank=True, null=True,
        help_text='Concatenacion subetapa|partida para compatibilidad con Excel RRA'
    )
    cantidad_presupuesto = models.DecimalField(
        max_digits=14, decimal_places=4,
        null=True, blank=True,
        help_text='Cantidad presupuestada en unidad de medida de la partida'
    )
    unidad_medida = models.CharField(
        max_length=20, blank=True, null=True,
        help_text='Unidad de medida. Ej: m2, ml, un'
    )
    presupuesto_total = models.DecimalField(
        max_digits=16, decimal_places=2,
        null=True, blank=True,
        help_text='Presupuesto total de la partida (MO + materiales + otros)'
    )
    presupuesto_mo = models.DecimalField(
        max_digits=16, decimal_places=2,
        null=True, blank=True,
        help_text='Presupuesto de mano obra directa en pesos'
    )
    tipo = models.CharField(
        max_length=20,
        choices=Tipo.choices,
        default=Tipo.CASA,
        help_text='Casa = MOD propia. Subcontrato = mano de obra tercerizada.'
    )
    estado_partida = models.CharField(
        max_length=20,
        choices=EstadoPartida.choices,
        default=EstadoPartida.ACTIVA,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'work_stage_task'
        verbose_name = 'Partida de etapa'
        verbose_name_plural = 'Partidas de etapa'
        ordering = ['stage', 'display_order', 'task']
        constraints = [
            models.UniqueConstraint(
                fields=['site', 'stage', 'task'],
                name='unique_stage_task_per_site'
            )
        ]

    def save(self, *args, **kwargs):
        # Auto-calcular partida_cod si tiene subetapa
        if self.subetapa and self.task_id:
            task_name = self.task.name if hasattr(self, '_task_cache') else TaskCatalog.objects.get(pk=self.task_id).name
            self.partida_cod = f'{self.subetapa}|{task_name}'
        elif self.task_id:
            task_name = self.task.name if hasattr(self, '_task_cache') else TaskCatalog.objects.get(pk=self.task_id).name
            self.partida_cod = task_name
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.stage.name} - {self.task.name} ({self.site.name})'


class SupervisorTaskPermission(models.Model):
    """
    Restriccion de partidas permitidas para un supervisor en una obra.

    Si un supervisor tiene filas en esta tabla, solo puede ver y asignar
    las partidas listadas. Si no tiene ninguna fila, ve todas las partidas
    de la obra sin restriccion.

    Esto permite configurar supervisores especializados (electrico, yesero, etc.)
    sin afectar a supervisores generales que no necesitan restriccion.

    Solo el prestador configura estas restricciones.
    """
    site_membership = models.ForeignKey(
        'companies.SiteMembership',
        on_delete=models.CASCADE,
        related_name='task_permissions'
    )
    task = models.ForeignKey(
        'work.TaskCatalog',
        on_delete=models.CASCADE,
        related_name='supervisor_permissions'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'work_supervisor_task_permission'
        verbose_name = 'Permiso de partida por supervisor'
        verbose_name_plural = 'Permisos de partida por supervisor'
        constraints = [
            models.UniqueConstraint(
                fields=['site_membership', 'task'],
                name='unique_supervisor_task_permission'
            )
        ]

    def __str__(self):
        return f'{self.site_membership} — {self.task.name}'


class WorkSession(models.Model):

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Abierta'
        CLOSED = 'CLOSED', 'Cerrada'
        AUTO_CLOSED = 'AUTO_CLOSED', 'Cierre automatico'
        VOIDED = 'VOIDED', 'Anulada'

    class ClosureOrigin(models.TextChoices):
        MANUAL = 'MANUAL', 'Manual'
        MASS_CLOSE = 'MASS_CLOSE', 'Cierre masivo'
        TASK_CLOSE = 'TASK_CLOSE', 'Cierre por partida'
        AUTO_CLOSE = 'AUTO_CLOSE', 'Cierre automatico'
        OVERTIME_SPLIT = 'OVERTIME_SPLIT', 'Division hora extra'

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.PROTECT,
        related_name='sessions'
    )
    site = models.ForeignKey(
        'companies.Site',
        on_delete=models.PROTECT,
        related_name='sessions'
    )
    resource = models.ForeignKey(
        'resources.Resource',
        on_delete=models.PROTECT,
        related_name='sessions'
    )
    resource_assignment = models.ForeignKey(
        'resources.ResourceSiteAssignment',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='sessions'
    )
    stage = models.ForeignKey(
        Stage,
        on_delete=models.PROTECT,
        related_name='sessions'
    )
    task = models.ForeignKey(
        TaskCatalog,
        on_delete=models.PROTECT,
        related_name='sessions'
    )
    stage_name_snapshot = models.CharField(max_length=120)
    task_code_snapshot = models.CharField(max_length=60)
    task_name_snapshot = models.CharField(max_length=180)
    risk_level_snapshot = models.CharField(max_length=20)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.IntegerField(null=True, blank=True)
    duration_productive_minutes = models.IntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN
    )
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='sessions_started'
    )
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='sessions_ended'
    )
    responsible_supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='sessions_supervised'
    )
    operated_by_role_code = models.CharField(max_length=80, blank=True, null=True)
    is_overtime = models.BooleanField(default=False)
    parent_session = models.ForeignKey(
        'self',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='overtime_sessions'
    )
    closure_origin = models.CharField(
        max_length=20,
        choices=ClosureOrigin.choices,
        null=True, blank=True
    )
    needs_review = models.BooleanField(
        default=False,
        help_text='Cierre manual/masivo/por partida cuya hora real se aleja del '
                  'work_end_time oficial mas alla de settings.REVIEW_CLOSE_THRESHOLD_MINUTES. '
                  'No bloquea nada — es solo para la bandeja de revision del prestador.'
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'work_session'
        verbose_name = 'Sesion de trabajo'
        verbose_name_plural = 'Sesiones de trabajo'
        ordering = ['-started_at']
        constraints = [
            models.UniqueConstraint(
                fields=['resource'],
                condition=models.Q(status='OPEN'),
                name='unique_open_session_per_resource'
            )
        ]

    def __str__(self):
        return f'{self.resource.display_name} - {self.task_name_snapshot} ({self.status})'


class WorkSessionChangeLog(models.Model):

    class ChangeType(models.TextChoices):
        DAY_CORRECTION = 'DAY_CORRECTION', 'Correccion del dia'
        FORCE_CLOSE    = 'FORCE_CLOSE',    'Cierre forzado'
        OVERTIME_SPLIT = 'OVERTIME_SPLIT', 'Division hora extra'
        VOID           = 'VOID',           'Anulacion'
        AUTO_CLOSE     = 'AUTO_CLOSE',     'Cierre automatico'
        PROVIDER_ADJUST = 'PROVIDER_ADJUST', 'Ajuste del prestador (bandeja de revision)'

    session = models.ForeignKey(
        WorkSession,
        on_delete=models.CASCADE,
        related_name='change_logs'
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='session_changes'
    )
    change_type = models.CharField(max_length=20, choices=ChangeType.choices)
    before_json = models.JSONField(null=True, blank=True)
    after_json = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'work_session_change_log'
        verbose_name = 'Log de cambio de sesion'
        verbose_name_plural = 'Logs de cambio de sesion'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.session} - {self.change_type}'


class MassCloseBatch(models.Model):

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.PROTECT,
        related_name='mass_close_batches'
    )
    site = models.ForeignKey(
        'companies.Site',
        on_delete=models.PROTECT,
        related_name='mass_close_batches'
    )
    executed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='mass_close_batches'
    )
    responsible_supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='mass_close_batches_supervised'
    )
    closed_count = models.IntegerField(default=0)
    executed_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'work_mass_close_batch'
        verbose_name = 'Lote de cierre masivo'
        verbose_name_plural = 'Lotes de cierre masivo'
        ordering = ['-executed_at']

    def __str__(self):
        return f'Cierre masivo {self.site.name} - {self.executed_at}'


class MassCloseBatchItem(models.Model):

    batch = models.ForeignKey(
        MassCloseBatch,
        on_delete=models.CASCADE,
        related_name='items'
    )
    session = models.ForeignKey(
        WorkSession,
        on_delete=models.PROTECT,
        related_name='mass_close_items'
    )
    closed_at_effective = models.DateTimeField()

    class Meta:
        db_table = 'work_mass_close_batch_item'
        verbose_name = 'Item de cierre masivo'
        verbose_name_plural = 'Items de cierre masivo'
        constraints = [
            models.UniqueConstraint(
                fields=['batch', 'session'],
                name='unique_batch_session'
            )
        ]

    def __str__(self):
        return f'{self.batch} - {self.session}'


class ChilePublicHoliday(models.Model):
    """
    Feriados nacionales de Chile.
    Se siembran via comando seed_holidays.
    Los fijos se repiten cada año, los variables (Semana Santa) cambian.
    """
    date         = models.DateField(unique=True)
    name         = models.CharField(max_length=120)
    year         = models.SmallIntegerField()
    is_recurring = models.BooleanField(
        default=True,
        help_text='True = feriado fijo que se repite cada año. False = variable (Semana Santa, etc.)'
    )

    class Meta:
        db_table = 'work_chile_public_holiday'
        verbose_name = 'Feriado nacional Chile'
        verbose_name_plural = 'Feriados nacionales Chile'
        ordering = ['date']

    def __str__(self):
        return f'{self.name} ({self.date})'


class SiteHoliday(models.Model):
    """
    Dias no laborables adicionales por obra.
    Para sandwiches, dias de faena, feriados regionales, etc.
    Solo el prestador puede crear estos dias.
    """
    site        = models.ForeignKey(
        'companies.Site',
        on_delete=models.CASCADE,
        related_name='holidays'
    )
    date        = models.DateField()
    description = models.CharField(
        max_length=180,
        help_text='Ej: Viernes sandwich feriado 18 de septiembre'
    )
    is_active   = models.BooleanField(default=True)
    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='site_holidays_created'
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'work_site_holiday'
        verbose_name = 'Dia no laborable por obra'
        verbose_name_plural = 'Dias no laborables por obra'
        ordering = ['site', 'date']
        constraints = [
            models.UniqueConstraint(
                fields=['site', 'date'],
                name='unique_site_holiday_per_date'
            )
        ]

    def __str__(self):
        return f'{self.site.name} — {self.date} ({self.description})'