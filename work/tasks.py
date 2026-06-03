# -*- coding: utf-8 -*-
"""
Tasks de Celery para el modulo work.
Cierre automatico de sesiones al fin de jornada.
"""
import logging
import pytz
from datetime import datetime

from celery import shared_task
from django.utils import timezone
from django.db import transaction

logger = logging.getLogger(__name__)


@shared_task(name='work.auto_close_sessions')
def auto_close_sessions_task():
    """
    Cierra sesiones de trabajo abiertas cuyo auto_close_time ya paso.

    Logica:
    - Corre cada 15 minutos via Celery Beat
    - Por cada obra con OvertimePolicy activa para el dia actual:
        * Verifica si la hora auto_close_time ya paso
        * Si paso, cierra sesiones OPEN escribiendo ended_at = normal_end_time
          (no la hora real del cierre automatico)
        * Registra en WorkSessionChangeLog con change_type = AUTO_CLOSE
    - Hace lo mismo para slots activos de subcontratos

    Por que dos horas distintas:
        normal_end_time = 18:00  fin de jornada oficial, para calculos de HH
        auto_close_time = 19:30  cuando el sistema actua, con buffer de seguridad
    Esto evita cerrar sesiones de hora extra legitima que esten en curso.
    """
    from companies.models import Site
    from work.models import WorkSession, WorkSessionChangeLog, OvertimePolicy
    from subcontracts.models import (
        SubcontractSession,
        SubcontractSessionHistory,
    )

    now_utc          = timezone.now()
    closed_sessions     = 0
    closed_sub_sessions = 0

    sites = Site.objects.filter(status='ACTIVE').select_related('company')

    for site in sites:
        try:
            site_tz   = pytz.timezone(site.timezone or 'America/Santiago')
            now_local = now_utc.astimezone(site_tz)
            weekday   = now_local.weekday()

            policy = OvertimePolicy.objects.filter(
                site=site,
                weekday=weekday,
                is_active=True,
            ).first()

            if not policy:
                continue

            # Si es dia de todo HE, no hay cierre automatico
            if policy.all_day_overtime:
                continue

            # Necesitamos ambas horas para operar
            if not policy.auto_close_time or not policy.normal_end_time:
                continue

            # Construir datetime de cierre automatico en timezone de la obra
            auto_close_dt_local = site_tz.localize(
                datetime.combine(now_local.date(), policy.auto_close_time)
            )
            auto_close_dt_utc = auto_close_dt_local.astimezone(pytz.utc)

            # Solo actuar si ya paso la hora de cierre automatico
            if now_utc < auto_close_dt_utc:
                continue

            # Hora oficial de fin de jornada — lo que se escribe en ended_at
            normal_end_dt_local = site_tz.localize(
                datetime.combine(now_local.date(), policy.normal_end_time)
            )
            normal_end_dt_utc = normal_end_dt_local.astimezone(pytz.utc)

            # ── Cerrar sesiones de trabajo normales ───────────────────────
            open_sessions = WorkSession.objects.filter(
                site=site,
                status='OPEN',
                started_at__date=now_local.date(),
            ).select_related('resource')

            for session in open_sessions:
                with transaction.atomic():
                    before = {
                        'status':     session.status,
                        'started_at': session.started_at.isoformat(),
                        'ended_at':   None,
                    }
                    session.status   = 'AUTO_CLOSED'
                    session.ended_at = normal_end_dt_utc  # hora oficial, no la real
                    session.save()

                    WorkSessionChangeLog.objects.create(
                        session     = session,
                        changed_by  = None,
                        change_type = 'AUTO_CLOSE',
                        before_json = before,
                        after_json  = {
                            'status':           'AUTO_CLOSED',
                            'ended_at':         normal_end_dt_utc.isoformat(),
                            'normal_end_time':  str(policy.normal_end_time),
                            'auto_close_time':  str(policy.auto_close_time),
                        },
                        reason = (
                            f'Cierre automatico. Jornada oficial: {policy.normal_end_time}. '
                            f'Cierre automatico configurado a las: {policy.auto_close_time}.'
                        ),
                    )
                    closed_sessions += 1

            # ── Cerrar sesiones de subcontratos ───────────────────────────
            open_sub_sessions = SubcontractSession.objects.filter(
                site=site,
                status='OPEN',
                started_at__date=now_local.date(),
            )

            for sub_session in open_sub_sessions:
                with transaction.atomic():
                    # Cerrar slots activos con la hora oficial de fin de jornada
                    for detail in sub_session.details.prefetch_related('personnel_slots').all():
                        active_slot = detail.personnel_slots.filter(ended_at__isnull=True).first()
                        if active_slot:
                            active_slot.ended_at = normal_end_dt_utc
                            active_slot.save()

                    sub_session.status   = 'CLOSED'
                    sub_session.ended_at = normal_end_dt_utc
                    sub_session.save()

                    SubcontractSessionHistory.objects.create(
                        session     = sub_session,
                        changed_by  = None,
                        change_type = 'FORCE_CLOSE',
                        after_json  = {
                            'ended_at':         normal_end_dt_utc.isoformat(),
                            'normal_end_time':  str(policy.normal_end_time),
                            'auto_close_time':  str(policy.auto_close_time),
                            'reason':           'Cierre automatico por fin de jornada',
                        },
                    )
                    closed_sub_sessions += 1

        except Exception as e:
            logger.error(
                f'Error cerrando sesiones para obra {site.id} ({site.name}): {e}',
                exc_info=True,
            )
            continue

    logger.info(
        f'auto_close_sessions: {closed_sessions} sesiones normales, '
        f'{closed_sub_sessions} sesiones de subcontratos cerradas.'
    )
    return {
        'closed_sessions':     closed_sessions,
        'closed_sub_sessions': closed_sub_sessions,
    }
