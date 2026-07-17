# -*- coding: utf-8 -*-
from django.db import models
from django.conf import settings


class SiteAlertConfig(models.Model):

    class AlertType(models.TextChoices):
        HIGH_RISK_START = 'HIGH_RISK_START', 'Inicio alto riesgo'
        ACTIVE_WITHOUT_SESSION = 'ACTIVE_WITHOUT_SESSION', 'Activo sin sesion'
        POST_LUNCH_UNASSIGNED = 'POST_LUNCH_UNASSIGNED', 'Sin asignar post colacion'
        OPEN_AFTER_SHIFT = 'OPEN_AFTER_SHIFT', 'Sesion abierta fuera de jornada'

    site = models.ForeignKey(
        'companies.Site',
        on_delete=models.CASCADE,
        related_name='alert_configs'
    )
    alert_type = models.CharField(max_length=40, choices=AlertType.choices)
    is_enabled = models.BooleanField(default=True)
    to_emails = models.JSONField(default=list)
    cc_emails = models.JSONField(default=list, blank=True)
    send_window_json = models.JSONField(null=True, blank=True)
    pending_send_at = models.DateTimeField(
        null=True, blank=True,
        help_text='Uso interno (debounce de HIGH_RISK_START): si tiene fecha futura, '
                  'ya hay un envio acumulado agendado y no hay que agendar otro.'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notifications_site_alert_config'
        verbose_name = 'Configuracion de alerta'
        verbose_name_plural = 'Configuraciones de alerta'
        constraints = [
            models.UniqueConstraint(
                fields=['site', 'alert_type'],
                name='unique_alert_config_per_site'
            )
        ]

    def __str__(self):
        return f'{self.site.name} - {self.alert_type}'


class AlertLog(models.Model):

    class Status(models.TextChoices):
        SENT = 'SENT', 'Enviado'
        FAILED = 'FAILED', 'Fallido'
        SKIPPED = 'SKIPPED', 'Omitido'

    site = models.ForeignKey(
        'companies.Site',
        on_delete=models.PROTECT,
        related_name='alert_logs'
    )
    alert_type = models.CharField(max_length=40)
    status = models.CharField(max_length=20, choices=Status.choices)
    recipients_json = models.JSONField(null=True, blank=True)
    payload_json = models.JSONField(null=True, blank=True)
    error_detail = models.TextField(blank=True, null=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications_alert_log'
        verbose_name = 'Log de alerta'
        verbose_name_plural = 'Logs de alerta'
        ordering = ['-sent_at']

    def __str__(self):
        return f'{self.site.name} - {self.alert_type} ({self.status})'


class SiteUnassignedAlertSchedule(models.Model):
    """
    Horario de revision "activos sin partida asignada" por obra. A
    diferencia de SiteAlertConfig (un registro por tipo de alerta), una
    obra puede tener VARIOS horarios distintos acá, cada uno con sus
    propios destinatarios (ej: 09:00 avisa a un supervisor, 15:30 avisa
    al jefe de terreno).

    Regla de negocio (definida junto al cliente): si a la hora de revision
    no hay ningun trabajador activo sin sesion, no se manda nada — "si no
    se avisa nada, es porque todo esta bien". El envio real corre en
    notifications.tasks.check_unassigned_workers_task, disparado por un
    PeriodicTask de Celery Beat sincronizado a esta hora exacta (ver
    notifications/services.py::ensure_unassigned_check_periodic_task).

    Opcional para el cliente: no bloquea la creacion/activacion de la obra.
    """
    site = models.ForeignKey(
        'companies.Site',
        on_delete=models.CASCADE,
        related_name='unassigned_alert_schedules'
    )
    send_time = models.TimeField(
        help_text='Hora local de la obra en que se revisa si hay activos sin partida.'
    )
    to_emails = models.JSONField(default=list, help_text='Lista de correos TO.')
    cc_emails = models.JSONField(default=list, blank=True, help_text='Lista de correos CC (opcional).')
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notifications_site_unassigned_alert_schedule'
        verbose_name = 'Horario de alerta — activos sin partida'
        verbose_name_plural = 'Horarios de alerta — activos sin partida'
        ordering = ['site', 'send_time']
        constraints = [
            models.UniqueConstraint(
                fields=['site', 'send_time'],
                name='unique_unassigned_schedule_per_site_time'
            )
        ]

    def __str__(self):
        return f'{self.site.name} — {self.send_time.strftime("%H:%M")}'
