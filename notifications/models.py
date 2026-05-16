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
