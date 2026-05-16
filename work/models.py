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
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(null=True, blank=True)
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

    def __str__(self):
        return f'{self.stage.name} - {self.task.name} ({self.site.name})'


class SupervisorStagePermission(models.Model):

    site_membership = models.ForeignKey(
        'companies.SiteMembership',
        on_delete=models.CASCADE,
        related_name='stage_permissions'
    )
    stage = models.ForeignKey(
        Stage,
        on_delete=models.CASCADE,
        related_name='supervisor_permissions'
    )
    is_allowed = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'work_supervisor_stage_permission'
        verbose_name = 'Permiso de etapa por supervisor'
        verbose_name_plural = 'Permisos de etapa por supervisor'
        constraints = [
            models.UniqueConstraint(
                fields=['site_membership', 'stage'],
                name='unique_supervisor_stage_permission'
            )
        ]

    def __str__(self):
        return f'{self.site_membership} - {self.stage.name}'


class WorkSession(models.Model):

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Abierta'
        CLOSED = 'CLOSED', 'Cerrada'
        AUTO_CLOSED = 'AUTO_CLOSED', 'Cierre automatico'
        VOIDED = 'VOIDED', 'Anulada'

    class ClosureOrigin(models.TextChoices):
        MANUAL = 'MANUAL', 'Manual'
        MASS_CLOSE = 'MASS_CLOSE', 'Cierre masivo'
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
        FORCE_CLOSE = 'FORCE_CLOSE', 'Cierre forzado'
        OVERTIME_SPLIT = 'OVERTIME_SPLIT', 'Division hora extra'
        VOID = 'VOID', 'Anulacion'

    session = models.ForeignKey(
        WorkSession,
        on_delete=models.CASCADE,
        related_name='change_logs'
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
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


class OvertimePolicy(models.Model):

    site = models.ForeignKey(
        'companies.Site',
        on_delete=models.CASCADE,
        related_name='overtime_policies'
    )
    weekday = models.SmallIntegerField()
    normal_end_time = models.TimeField(null=True, blank=True)
    all_day_overtime = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'work_overtime_policy'
        verbose_name = 'Politica de hora extra'
        verbose_name_plural = 'Politicas de hora extra'
        constraints = [
            models.UniqueConstraint(
                fields=['site', 'weekday'],
                name='unique_overtime_policy_per_site_weekday'
            )
        ]

    def __str__(self):
        return f'{self.site.name} - dia {self.weekday}'
