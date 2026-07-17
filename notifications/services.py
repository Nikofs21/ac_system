# -*- coding: utf-8 -*-
"""
Utilidades de notifications que no son ni modelo ni vista.

ensure_unassigned_check_periodic_task() sincroniza un PeriodicTask de
django-celery-beat para que exista un crontab exacto (no polling) por
cada hora unica que alguna obra tenga configurada en
SiteUnassignedAlertSchedule. Si dos obras distintas usan la misma hora
(ej: ambas a las 09:00), comparten el mismo PeriodicTask — no se duplica
nada. La tarea en si (notifications.tasks.check_unassigned_workers_task)
recibe hour/minute como kwargs y filtra alli que obras le corresponden.

No hay limpieza automatica de PeriodicTask huerfanos (si se borra el
ultimo horario que usaba una hora, el PeriodicTask queda sin dueño). Es
inofensivo: la tarea corre, no encuentra horarios para esa hora, no hace
nada. Se dejo asi a proposito para no complicar el borrado con conteos
de referencias — si en el futuro molesta, se puede agregar un comando de
limpieza aparte.
"""
import json


def ensure_unassigned_check_periodic_task(hour, minute):
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    crontab, _ = CrontabSchedule.objects.get_or_create(
        minute=str(minute),
        hour=str(hour),
        day_of_week='*',
        day_of_month='*',
        month_of_year='*',
        timezone='America/Santiago',
    )

    name = f'check-unassigned-{hour:02d}{minute:02d}'
    PeriodicTask.objects.update_or_create(
        name=name,
        defaults={
            'crontab':  crontab,
            'task':     'notifications.check_unassigned_workers',
            'kwargs':   json.dumps({'hour': hour, 'minute': minute}),
            'enabled':  True,
        }
    )


def schedule_high_risk_accumulator(site):
    """
    Debounce del correo acumulado de "alto riesgo". Se llama cada vez que
    se inicia una sesion de alto riesgo (work/views.py::assignment_confirm).

    Si la alerta esta apagada o sin destinatarios, no hace nada — la
    confirmacion en pantalla (checkbox EPP) sigue funcionando siempre,
    independiente de esto; esto es solo el correo adicional, opcional.

    Si ya hay un envio agendado (pending_send_at en el futuro), no agenda
    uno nuevo — el que ya esta agendado va a juntar tambien esta sesion
    porque el envio, cuando dispare, consulta TODAS las sesiones de alto
    riesgo abiertas en ese momento, no solo la que gatillo el agendamiento.
    """
    from django.utils import timezone
    from notifications.models import SiteAlertConfig
    from notifications.tasks import send_high_risk_accumulator_task

    try:
        config = SiteAlertConfig.objects.get(site=site, alert_type='HIGH_RISK_START')
    except SiteAlertConfig.DoesNotExist:
        return

    if not config.is_enabled or not config.to_emails:
        return

    now = timezone.now()
    if config.pending_send_at and config.pending_send_at > now:
        return  # ya hay un envio agendado, se sube solo a ese

    batch_minutes = getattr(site.config, 'high_risk_email_batch_minutes', 30) if hasattr(site, 'config') else 30
    if not batch_minutes or batch_minutes <= 0:
        batch_minutes = 30

    send_at = now + timezone.timedelta(minutes=batch_minutes)
    config.pending_send_at = send_at
    config.save(update_fields=['pending_send_at'])

    send_high_risk_accumulator_task.apply_async(
        args=[site.id], countdown=batch_minutes * 60,
    )
