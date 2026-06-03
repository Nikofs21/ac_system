# -*- coding: utf-8 -*-
from django.db import models
from django.conf import settings


class Subcontract(models.Model):

    class Status(models.TextChoices):
        ACTIVE   = 'ACTIVE',   'Activo'
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
    uid = models.CharField(max_length=64, unique=True, blank=True)
    name = models.CharField(max_length=180)
    code = models.CharField(max_length=60)
    rut  = models.CharField(max_length=20, blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
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

    def save(self, *args, **kwargs):
        if not self.uid:
            import uuid
            self.uid = uuid.uuid4().hex
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.name} ({self.code}) - {self.site.name}'


class SubcontractSession(models.Model):
    """
    Sesion de trabajo de un subcontrato.
    Una sesion agrupa una o mas partidas (detalles) que el subcontrato
    ejecuta durante un periodo de tiempo.
    """

    class Status(models.TextChoices):
        OPEN   = 'OPEN',   'Abierta'
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
    started_at = models.DateTimeField()
    ended_at   = models.DateTimeField(null=True, blank=True)
    status     = models.CharField(
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
        on_delete=models.PROTECT,
        related_name='subcontract_sessions_ended'
    )
    notes      = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subcontracts_session'
        verbose_name = 'Sesion de subcontrato'
        verbose_name_plural = 'Sesiones de subcontrato'
        ordering = ['-started_at']

    def __str__(self):
        return f'{self.subcontract.name} — {self.started_at:%Y-%m-%d %H:%M} ({self.status})'


class SubcontractSessionDetail(models.Model):
    """
    Una partida dentro de una sesion de subcontrato.
    Cada detalle tiene su propia linea de tiempo de personal (slots).
    """
    session = models.ForeignKey(
        SubcontractSession,
        on_delete=models.PROTECT,
        related_name='details'
    )
    task = models.ForeignKey(
        'work.TaskCatalog',
        on_delete=models.PROTECT,
        related_name='subcontract_details'
    )
    unit_code  = models.CharField(max_length=20, default='personas')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subcontracts_session_detail'
        verbose_name = 'Detalle de sesion'
        verbose_name_plural = 'Detalles de sesion'
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'task'],
                name='unique_task_per_subcontract_session'
            )
        ]

    def current_quantity(self):
        """Cantidad activa en este momento (slot sin ended_at)."""
        slot = self.personnel_slots.filter(ended_at__isnull=True).first()
        return slot.quantity if slot else 0

    def total_person_minutes(self):
        """
        Calcula el total de persona-minutos para esta partida.
        Suma (quantity × duracion_minutos) de cada slot cerrado
        mas el slot activo si la sesion sigue abierta.
        """
        from django.utils import timezone
        total = 0
        for slot in self.personnel_slots.all():
            end = slot.ended_at or timezone.now()
            if slot.started_at and end:
                minutes = (end - slot.started_at).total_seconds() / 60
                total  += slot.quantity * minutes
        return round(total, 2)

    def __str__(self):
        return f'{self.session} — {self.task.name}'


class SubcontractPersonnelSlot(models.Model):
    """
    Tramo de tiempo con una cantidad fija de personas en una partida.
    Cada vez que cambia la cantidad, se cierra el slot activo y se abre uno nuevo.
    Esto permite calcular HH exactas aunque la cantidad cambie varias veces.

    Ejemplo:
      Slot 1: quantity=4, started=08:00, ended=10:00  → 4 × 120 min = 480 min
      Slot 2: quantity=5, started=10:00, ended=18:00  → 5 × 480 min = 2400 min
      Total: 2880 min = 48 HH
    """
    detail = models.ForeignKey(
        SubcontractSessionDetail,
        on_delete=models.PROTECT,
        related_name='personnel_slots'
    )
    quantity   = models.PositiveIntegerField()
    started_at = models.DateTimeField()
    ended_at   = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='subcontract_slots_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'subcontracts_personnel_slot'
        verbose_name = 'Tramo de personal'
        verbose_name_plural = 'Tramos de personal'
        ordering = ['detail', 'started_at']
        constraints = [
            # Solo puede haber un slot activo (sin ended_at) por detalle
            models.UniqueConstraint(
                fields=['detail'],
                condition=models.Q(ended_at__isnull=True),
                name='unique_active_slot_per_detail'
            )
        ]

    def duration_minutes(self):
        from django.utils import timezone
        end = self.ended_at or timezone.now()
        if self.started_at:
            return round((end - self.started_at).total_seconds() / 60, 2)
        return 0

    def __str__(self):
        ended = self.ended_at.strftime('%H:%M') if self.ended_at else 'activo'
        return f'{self.detail.task.name} | {self.quantity} pers | {self.started_at:%H:%M}→{ended}'


class SubcontractSessionHistory(models.Model):
    """
    Bitacora de cambios relevantes en una sesion de subcontrato.
    """

    class ChangeType(models.TextChoices):
        START              = 'START',              'Inicio'
        QUANTITY_CHANGE    = 'QUANTITY_CHANGE',    'Cambio de cantidad'
        TASK_ADDED         = 'TASK_ADDED',         'Partida agregada'
        TASK_REMOVED       = 'TASK_REMOVED',       'Partida eliminada'
        CLOSE              = 'CLOSE',              'Cierre'
        FORCE_CLOSE        = 'FORCE_CLOSE',        'Cierre forzado'

    session    = models.ForeignKey(
        SubcontractSession,
        on_delete=models.PROTECT,
        related_name='history'
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='subcontract_history_entries'
    )
    change_type  = models.CharField(max_length=40, choices=ChangeType.choices)
    before_json  = models.JSONField(null=True, blank=True)
    after_json   = models.JSONField(null=True, blank=True)
    reason       = models.TextField(blank=True, null=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'subcontracts_session_history'
        verbose_name = 'Historial de sesion'
        verbose_name_plural = 'Historial de sesiones'
        ordering = ['session', 'created_at']

    def __str__(self):
        return f'{self.session} — {self.change_type} por {self.changed_by}'

class SubcontractTaskAssignment(models.Model):
    """
    Partidas autorizadas para un subcontrato en una obra.

    Cada partida tiene su propia etapa reservada — esto permite que un
    subcontrato trabaje partidas de etapas distintas, cada una bajo
    una etapa reservada especifica creada para ese subcontrato.

    Ejemplo:
        Subcontrato "Yeseros Martinez":
            - Partida "Tabique simple"  → Etapa "Tabiques - Yeseros Martinez"
            - Partida "Tabique doble"   → Etapa "Tabiques - Yeseros Martinez"
            - Partida "Cielo yeso"      → Etapa "Cielos - Yeseros Martinez"

    En reportes, buscar por etapa reservada muestra todo lo del subcontrato
    agrupado limpiamente.

    Solo el prestador configura estas asignaciones.
    """
    subcontract = models.ForeignKey(
        'subcontracts.Subcontract',
        on_delete=models.CASCADE,
        related_name='task_assignments'
    )
    task = models.ForeignKey(
        'work.TaskCatalog',
        on_delete=models.PROTECT,
        related_name='subcontract_assignments'
    )
    reserved_stage = models.ForeignKey(
        'work.Stage',
        on_delete=models.PROTECT,
        related_name='subcontract_task_assignments',
        help_text='Etapa reservada bajo la cual se registran las sesiones de esta partida.'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subcontracts_task_assignment'
        verbose_name = 'Partida asignada a subcontrato'
        verbose_name_plural = 'Partidas asignadas a subcontrato'
        constraints = [
            models.UniqueConstraint(
                fields=['subcontract', 'task'],
                name='unique_task_per_subcontract'
            )
        ]

    def __str__(self):
        return f'{self.subcontract.name} — {self.task.name} ({self.reserved_stage.name})'