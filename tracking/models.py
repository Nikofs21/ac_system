# -*- coding: utf-8 -*-
from django.db import models
from django.conf import settings


class NoOnSiteEvent(models.Model):

    class ReasonCode(models.TextChoices):
        PERMISO = 'PERMISO', 'Permiso'
        LICENCIA = 'LICENCIA', 'Licencia medica'
        AUSENTE = 'AUSENTE', 'Ausente sin aviso'
        VACACIONES = 'VACACIONES', 'Vacaciones'
        OTRO = 'OTRO', 'Otro'

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Activo'
        VOIDED = 'VOIDED', 'Anulado'

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.PROTECT,
        related_name='no_on_site_events'
    )
    site = models.ForeignKey(
        'companies.Site',
        on_delete=models.PROTECT,
        related_name='no_on_site_events'
    )
    resource = models.ForeignKey(
        'resources.Resource',
        on_delete=models.PROTECT,
        related_name='no_on_site_events'
    )
    event_date = models.DateField()
    reason_code = models.CharField(
        max_length=40,
        choices=ReasonCode.choices,
        default=ReasonCode.AUSENTE
    )
    detail = models.TextField(blank=True, null=True)
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='no_on_site_events_marked'
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='no_on_site_events_voided'
    )
    voided_reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tracking_no_on_site_event'
        verbose_name = 'Evento No en obra'
        verbose_name_plural = 'Eventos No en obra'
        ordering = ['-event_date']
        constraints = [
            models.UniqueConstraint(
                fields=['site', 'resource', 'event_date'],
                condition=models.Q(status='ACTIVE'),
                name='unique_active_no_on_site_per_day'
            )
        ]

    def __str__(self):
        return f'{self.resource.display_name} - {self.event_date} ({self.reason_code})'
