# -*- coding: utf-8 -*-
from django.db import models
from django.conf import settings


class Subcontract(models.Model):

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Activo'
        INACTIVE = 'INACTIVE', 'Inactivo'

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.PROTECT,
        related_name='subcontracts'
    )
    site = models.ForeignKey(
        'companies.Site',
        on_delete=models.PROTECT,
        related_name='subcontracts'
    )
    name = models.CharField(max_length=180)
    code = models.CharField(max_length=60)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )
    reserved_stage = models.ForeignKey(
        'work.Stage',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='subcontracts'
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subcontracts_subcontract'
        verbose_name = 'Subcontrato'
        verbose_name_plural = 'Subcontratos'
        ordering = ['site', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['site', 'code'],
                name='unique_subcontract_code_per_site'
            )
        ]

    def __str__(self):
        return f'{self.name} ({self.code}) - {self.site.name}'


class SubcontractSession(models.Model):

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Abierta'
        PARTIAL = 'PARTIAL', 'Parcial'
        CLOSED = 'CLOSED', 'Cerrada'
        VOIDED = 'VOIDED', 'Anulada'

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.PROTECT,
        related_name='subcontract_sessions'
    )
    site = models.ForeignKey(
        'companies.Site',
        on_delete=models.PROTECT,
        related_name='subcontract_sessions'
    )
    subcontract = models.ForeignKey(
        Subcontract,
        on_delete=models.PROTECT,
        related_name='sessions'
    )
    stage = models.ForeignKey(
        'work.Stage',
        on_delete=models.PROTECT,
        related_name='subcontract_sessions'
    )
    task = models.ForeignKey(
        'work.TaskCatalog',
        on_delete=models.PROTECT,
        related_name='subcontract_sessions'
    )
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN
    )
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='subcontract_sessions_started'
    )
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='subcontract_sessions_ended'
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subcontracts_session'
        verbose_name = 'Sesion de subcontrato'
        verbose_name_plural = 'Sesiones de subcontrato'
        ordering = ['-started_at']

    def __str__(self):
        return f'{self.subcontract.name} - {self.task.name} ({self.status})'


class SubcontractSessionDetail(models.Model):

    session = models.OneToOneField(
        SubcontractSession,
        on_delete=models.CASCADE,
        related_name='detail'
    )
    quantity_started = models.DecimalField(max_digits=14, decimal_places=4)
    quantity_closed = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    unit_code = models.CharField(max_length=20)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='subcontract_details_updated'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subcontracts_session_detail'
        verbose_name = 'Detalle de sesion de subcontrato'
        verbose_name_plural = 'Detalles de sesion de subcontrato'

    def __str__(self):
        return f'{self.session} - {self.quantity_closed}/{self.quantity_started} {self.unit_code}'


class SubcontractSessionHistory(models.Model):

    class ChangeType(models.TextChoices):
        DAY_EDIT = 'DAY_EDIT', 'Edicion del dia'
        QUANTITY_ADJUSTMENT = 'QUANTITY_ADJUSTMENT', 'Ajuste de cantidad'
        FORCE_CLOSE = 'FORCE_CLOSE', 'Cierre forzado'

    session = models.ForeignKey(
        SubcontractSession,
        on_delete=models.CASCADE,
        related_name='history'
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='subcontract_history'
    )
    change_type = models.CharField(max_length=30, choices=ChangeType.choices)
    before_json = models.JSONField(null=True, blank=True)
    after_json = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'subcontracts_session_history'
        verbose_name = 'Historial de sesion de subcontrato'
        verbose_name_plural = 'Historiales de sesion de subcontrato'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.session} - {self.change_type}'
