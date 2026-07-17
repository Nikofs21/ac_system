# -*- coding: utf-8 -*-
"""
Tasks de Celery del modulo notifications.
"""
import logging
from datetime import time as dtime

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone
from django.utils.html import escape

logger = logging.getLogger(__name__)

SIN_SUPERVISOR_LABEL = 'Sin supervisor asignado'


def _agrupar_por_supervisor(trabajadores):
    """
    Agrupa una lista de dicts (que ya traen 'supervisor') en un dict
    ordenado {nombre_supervisor: [trabajadores]}. Los sin supervisor
    quedan al final, bajo SIN_SUPERVISOR_LABEL — no se descartan ni se
    mezclan con los demas, para que se note que falta ese dato.
    """
    grupos = {}
    for w in trabajadores:
        key = w['supervisor'] or SIN_SUPERVISOR_LABEL
        grupos.setdefault(key, []).append(w)

    ordenados = {k: v for k, v in sorted(grupos.items()) if k != SIN_SUPERVISOR_LABEL}
    if SIN_SUPERVISOR_LABEL in grupos:
        ordenados[SIN_SUPERVISOR_LABEL] = grupos[SIN_SUPERVISOR_LABEL]
    return ordenados


def _build_unassigned_email_html(site, schedule, trabajadores):
    """
    Arma el cuerpo HTML de la alerta "activos sin partida" — mismo formato
    visual que la funcion de App Script que reemplaza (tabla con
    Trabajador/RUT/Cargo), agrupado por supervisor para lectura mas comoda.
    trabajadores es una lista de dicts {'nombre', 'rut', 'cargo', 'supervisor'}.
    """
    grupos = _agrupar_por_supervisor(trabajadores)
    bloques = []

    for supervisor, lista in grupos.items():
        filas = []
        for w in lista:
            filas.append(
                '<tr>'
                f'<td style="border:1px solid #ddd;padding:8px;">{escape(w["nombre"])}</td>'
                f'<td style="border:1px solid #ddd;padding:8px;">{escape(w["rut"])}</td>'
                f'<td style="border:1px solid #ddd;padding:8px;">{escape(w["cargo"])}</td>'
                '</tr>'
            )
        bloques.append(
            f'<p style="margin:16px 0 6px;font-weight:bold;">{escape(supervisor)} '
            f'<span style="font-weight:normal;color:#666;">({len(lista)})</span></p>'
            '<table style="border-collapse:collapse;width:100%;max-width:900px;">'
            '<tr style="background:#f2f2f2;">'
            '<th style="border:1px solid #ddd;padding:8px;">Trabajador</th>'
            '<th style="border:1px solid #ddd;padding:8px;">RUT</th>'
            '<th style="border:1px solid #ddd;padding:8px;">Cargo</th>'
            '</tr>'
            + ''.join(filas) +
            '</table>'
        )

    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#111;">'
        f'<p>Revisión de las {schedule.send_time.strftime("%H:%M")} hrs — {escape(site.name)}.</p>'
        '<p>Los siguientes trabajadores se encuentran activos pero no poseen una partida abierta:</p>'
        + ''.join(bloques) +
        '</div>'
    )


def _build_unassigned_email_text(site, schedule, trabajadores):
    """Version texto plano, agrupada por supervisor igual que la HTML."""
    grupos = _agrupar_por_supervisor(trabajadores)
    bloques = []
    for supervisor, lista in grupos.items():
        lineas = [f'  - {w["nombre"]} (RUT: {w["rut"] or "s/i"}, Cargo: {w["cargo"] or "s/i"})' for w in lista]
        bloques.append(f'{supervisor} ({len(lista)}):\n' + '\n'.join(lineas))

    return (
        f'Revision de las {schedule.send_time.strftime("%H:%M")} hrs — {site.name}\n\n'
        f'Los siguientes trabajadores estan activos en la obra pero no tienen '
        f'una partida asignada en este momento:\n\n'
        + '\n\n'.join(bloques)
    )


@shared_task(name='notifications.check_unassigned_workers')
def check_unassigned_workers_task(hour, minute):
    """
    Disparada por Celery Beat a una hora exacta (ver notifications/services.py
    ::ensure_unassigned_check_periodic_task), una vez por cada horario unico
    que exista entre todas las obras. Revisa, para cada obra con un
    SiteUnassignedAlertSchedule configurado a esta hora, si hay trabajadores
    activos sin sesion abierta ahora mismo.

    Regla de negocio: si no hay nadie sin partida, no se manda correo — "si
    no se avisa nada, es porque todo esta bien".

    La consulta de "quien esta activo sin sesion" replica intencionalmente
    la misma logica de work.views.active_workers (unassigned_count): asignado
    activo a la obra, sin sesion OPEN, y sin marca de "No en obra" hoy.

    El "supervisor" de cada trabajador se toma de
    ResourceSiteAssignment.assigned_by — es el campo mas cercano a "quien
    es responsable de este trabajador en la obra" que existe hoy en el
    modelo. No es un campo llamado "supervisor" en si (no existe uno), asi
    que si en algun momento se agrega uno mas preciso, cambiar aqui.
    """
    from companies.models import Site
    from resources.models import Resource, ResourceSiteAssignment
    from work.models import WorkSession
    from tracking.models import NoOnSiteEvent
    from notifications.models import SiteUnassignedAlertSchedule, AlertLog

    target_time = dtime(hour, minute)
    schedules = SiteUnassignedAlertSchedule.objects.filter(
        send_time=target_time, is_enabled=True,
    ).select_related('site')

    sent    = 0
    skipped = 0

    for schedule in schedules:
        site = schedule.site

        if site.status != 'ACTIVE':
            continue

        today = timezone.localdate()

        assignments = ResourceSiteAssignment.objects.filter(
            site=site, status='ACTIVE',
        ).select_related('assigned_by')
        assignment_by_resource = {a.resource_id: a for a in assignments}
        assigned_ids = set(assignment_by_resource.keys())

        with_session_ids = set(WorkSession.objects.filter(
            site=site, status='OPEN',
        ).values_list('resource_id', flat=True))

        no_on_site_ids = set(NoOnSiteEvent.objects.filter(
            site=site, event_date=today, status='ACTIVE',
        ).values_list('resource_id', flat=True))

        unassigned_ids = assigned_ids - with_session_ids - no_on_site_ids

        if not unassigned_ids:
            skipped += 1
            continue

        trabajadores = []
        for r in Resource.objects.filter(id__in=unassigned_ids).select_related('job_title').order_by('display_name'):
            asignacion = assignment_by_resource.get(r.id)
            supervisor = asignacion.assigned_by.get_full_name() if asignacion and asignacion.assigned_by else ''
            trabajadores.append({
                'nombre':     r.display_name,
                'rut':        r.person_rut or '',
                'cargo':      r.job_title.name if r.job_title else '',
                'supervisor': supervisor,
            })

        asunto = f'{site.name}: {len(trabajadores)} trabajador(es) activo(s) sin partida asignada'
        cuerpo_texto = _build_unassigned_email_text(site, schedule, trabajadores)
        cuerpo_html  = _build_unassigned_email_html(site, schedule, trabajadores)

        recipients_json = {'to': schedule.to_emails, 'cc': schedule.cc_emails}

        try:
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@novusimperium.cl')
            email = EmailMultiAlternatives(
                subject=asunto,
                body=cuerpo_texto,
                from_email=from_email,
                to=schedule.to_emails,
                cc=schedule.cc_emails or None,
            )
            email.attach_alternative(cuerpo_html, 'text/html')
            email.send(fail_silently=False)

            AlertLog.objects.create(
                site=site,
                alert_type='ACTIVE_WITHOUT_SESSION',
                status='SENT',
                recipients_json=recipients_json,
                payload_json={
                    'trabajadores': [w['nombre'] for w in trabajadores],
                    'hora':         schedule.send_time.strftime('%H:%M'),
                },
            )
            sent += 1
        except Exception as e:
            logger.error(
                f'Error enviando alerta "activos sin partida" ({site.name}, '
                f'{schedule.send_time}): {e}',
                exc_info=True,
            )
            AlertLog.objects.create(
                site=site,
                alert_type='ACTIVE_WITHOUT_SESSION',
                status='FAILED',
                recipients_json=recipients_json,
                error_detail=str(e),
            )

    logger.info(
        f'check_unassigned_workers[{hour:02d}:{minute:02d}]: '
        f'{sent} correo(s) enviado(s), {skipped} obra(s) sin novedad.'
    )
    return {'sent': sent, 'skipped': skipped}


def _build_high_risk_email_html(site, trabajadores):
    """
    Mismo lenguaje visual que la tabla de "activos sin partida", agregando
    la columna Partida, agrupado por supervisor (WorkSession.responsible_supervisor,
    que es un campo directo y confiable — no una aproximacion como en el
    caso de "activos sin partida").
    """
    grupos = _agrupar_por_supervisor(trabajadores)
    bloques = []

    for supervisor, lista in grupos.items():
        filas = []
        for w in lista:
            filas.append(
                '<tr>'
                f'<td style="border:1px solid #ddd;padding:8px;">{escape(w["nombre"])}</td>'
                f'<td style="border:1px solid #ddd;padding:8px;">{escape(w["rut"])}</td>'
                f'<td style="border:1px solid #ddd;padding:8px;">{escape(w["cargo"])}</td>'
                f'<td style="border:1px solid #ddd;padding:8px;">{escape(w["partida"])}</td>'
                '</tr>'
            )
        bloques.append(
            f'<p style="margin:16px 0 6px;font-weight:bold;">{escape(supervisor)} '
            f'<span style="font-weight:normal;color:#666;">({len(lista)})</span></p>'
            '<table style="border-collapse:collapse;width:100%;max-width:900px;">'
            '<tr style="background:#f2f2f2;">'
            '<th style="border:1px solid #ddd;padding:8px;">Trabajador</th>'
            '<th style="border:1px solid #ddd;padding:8px;">RUT</th>'
            '<th style="border:1px solid #ddd;padding:8px;">Cargo</th>'
            '<th style="border:1px solid #ddd;padding:8px;">Partida</th>'
            '</tr>'
            + ''.join(filas) +
            '</table>'
        )

    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#111;">'
        f'<p>Trabajadores actualmente en partidas de <strong>alto riesgo</strong> — {escape(site.name)}.</p>'
        + ''.join(bloques) +
        '</div>'
    )


def _build_high_risk_email_text(site, trabajadores):
    grupos = _agrupar_por_supervisor(trabajadores)
    bloques = []
    for supervisor, lista in grupos.items():
        lineas = [
            f'  - {w["nombre"]} (RUT: {w["rut"] or "s/i"}, Cargo: {w["cargo"] or "s/i"}) — {w["partida"]}'
            for w in lista
        ]
        bloques.append(f'{supervisor} ({len(lista)}):\n' + '\n'.join(lineas))

    return (
        f'Trabajadores actualmente en partidas de alto riesgo — {site.name}\n\n'
        + '\n\n'.join(bloques)
    )


@shared_task(name='notifications.send_high_risk_accumulator')
def send_high_risk_accumulator_task(site_id):
    """
    Dispara con countdown (no crontab) desde
    notifications.services.schedule_high_risk_accumulator, unos minutos
    despues de la primera sesion de alto riesgo que la gatillo (debounce
    para no mandar un correo por cada trabajador si varios entran casi al
    mismo tiempo).

    Al momento de disparar, consulta TODAS las sesiones de alto riesgo
    abiertas en ese instante — no solo la que la gatillo — para que el
    correo sea un acumulado real, no un correo por evento.
    """
    from companies.models import Site
    from work.models import WorkSession
    from notifications.models import SiteAlertConfig, AlertLog

    try:
        site = Site.objects.get(id=site_id)
    except Site.DoesNotExist:
        return {'sent': 0}

    try:
        config = SiteAlertConfig.objects.get(site=site, alert_type='HIGH_RISK_START')
    except SiteAlertConfig.DoesNotExist:
        return {'sent': 0}

    # Cierra la ventana de debounce — el proximo inicio de riesgo agenda un
    # envio nuevo en vez de sumarse a este, que ya esta por salir.
    config.pending_send_at = None
    config.save(update_fields=['pending_send_at'])

    if not config.is_enabled or not config.to_emails:
        return {'sent': 0}

    open_risk_sessions = WorkSession.objects.filter(
        site=site, status='OPEN', risk_level_snapshot='HIGH_RISK',
    ).select_related('resource', 'resource__job_title', 'task', 'responsible_supervisor')

    trabajadores = [
        {
            'nombre':     s.resource.display_name,
            'rut':        s.resource.person_rut or '',
            'cargo':      s.resource.job_title.name if s.resource.job_title else '',
            'partida':    s.task_name_snapshot,
            'supervisor': s.responsible_supervisor.get_full_name() if s.responsible_supervisor else '',
        }
        for s in open_risk_sessions.order_by('resource__display_name')
    ]

    recipients_json = {'to': config.to_emails, 'cc': config.cc_emails}

    if not trabajadores:
        # Se agendo el envio pero para cuando disparo ya no quedaba nadie
        # en riesgo (sesiones cerradas en el intertanto) — no es un error,
        # se registra como omitido para trazabilidad.
        AlertLog.objects.create(
            site=site, alert_type='HIGH_RISK_START', status='SKIPPED',
            recipients_json=recipients_json,
        )
        return {'sent': 0}

    asunto = f'{site.name}: {len(trabajadores)} trabajador(es) en partidas de alto riesgo'
    cuerpo_texto = _build_high_risk_email_text(site, trabajadores)
    cuerpo_html  = _build_high_risk_email_html(site, trabajadores)

    try:
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@novusimperium.cl')
        email = EmailMultiAlternatives(
            subject=asunto,
            body=cuerpo_texto,
            from_email=from_email,
            to=config.to_emails,
            cc=config.cc_emails or None,
        )
        email.attach_alternative(cuerpo_html, 'text/html')
        email.send(fail_silently=False)

        AlertLog.objects.create(
            site=site, alert_type='HIGH_RISK_START', status='SENT',
            recipients_json=recipients_json,
            payload_json={'trabajadores': [w['nombre'] for w in trabajadores]},
        )
        return {'sent': 1}
    except Exception as e:
        logger.error(
            f'Error enviando alerta acumulada de alto riesgo ({site.name}): {e}',
            exc_info=True,
        )
        AlertLog.objects.create(
            site=site, alert_type='HIGH_RISK_START', status='FAILED',
            recipients_json=recipients_json, error_detail=str(e),
        )
        return {'sent': 0}
