# -*- coding: utf-8 -*-
"""
Tasks de Celery para el modulo work.
Cierre automatico de sesiones al fin de jornada.
Respeta feriados nacionales y dias extra por obra.
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
    Salta obras si el dia es feriado nacional o dia no laborable de la obra.
    """
    from companies.models import Site
    from work.models import (
        WorkSession, WorkSessionChangeLog, OvertimePolicy,
        ChilePublicHoliday, SiteHoliday,
    )
    from subcontracts.models import (
        SubcontractSession,
        SubcontractSessionHistory,
    )

    now_utc             = timezone.now()
    closed_sessions     = 0
    closed_sub_sessions = 0
    skipped_holiday     = 0

    sites = Site.objects.filter(status='ACTIVE').select_related('company')

    for site in sites:
        try:
            site_tz   = pytz.timezone(site.timezone or 'America/Santiago')
            now_local = now_utc.astimezone(site_tz)
            today     = now_local.date()
            weekday   = now_local.weekday()

            # ── Verificar feriado nacional ────────────────────────────────
            is_national_holiday = ChilePublicHoliday.objects.filter(
                date=today
            ).exists()

            if is_national_holiday:
                logger.info(f'Obra {site.name}: feriado nacional {today}, saltando cierre.')
                skipped_holiday += 1
                continue

            # ── Verificar dia no laborable de la obra ─────────────────────
            is_site_holiday = SiteHoliday.objects.filter(
                site=site,
                date=today,
                is_active=True,
            ).exists()

            if is_site_holiday:
                logger.info(f'Obra {site.name}: dia no laborable {today}, saltando cierre.')
                skipped_holiday += 1
                continue

            # ── Buscar politica del dia ───────────────────────────────────
            policy = OvertimePolicy.objects.filter(
                site=site,
                weekday=weekday,
                is_active=True,
            ).first()

            if not policy:
                continue

            if policy.all_day_overtime:
                continue

            if not policy.auto_close_time or not policy.normal_end_time:
                continue

            # ── Verificar si ya paso la hora de cierre automatico ─────────
            auto_close_dt_local = site_tz.localize(
                datetime.combine(today, policy.auto_close_time)
            )
            auto_close_dt_utc = auto_close_dt_local.astimezone(pytz.utc)

            if now_utc < auto_close_dt_utc:
                continue

            # ── Hora oficial de fin de jornada (lo que se escribe) ────────
            normal_end_dt_local = site_tz.localize(
                datetime.combine(today, policy.normal_end_time)
            )
            normal_end_dt_utc = normal_end_dt_local.astimezone(pytz.utc)

            # ── Cerrar sesiones normales ──────────────────────────────────
            open_sessions = WorkSession.objects.filter(
                site=site,
                status='OPEN',
                started_at__date=today,
            ).select_related('resource')

            for session in open_sessions:
                with transaction.atomic():
                    before = {
                        'status':     session.status,
                        'started_at': session.started_at.isoformat(),
                        'ended_at':   None,
                    }
                    session.status   = 'AUTO_CLOSED'
                    session.ended_at = normal_end_dt_utc
                    session.save()

                    WorkSessionChangeLog.objects.create(
                        session     = session,
                        changed_by  = None,
                        change_type = 'AUTO_CLOSE',
                        before_json = before,
                        after_json  = {
                            'status':          'AUTO_CLOSED',
                            'ended_at':        normal_end_dt_utc.isoformat(),
                            'normal_end_time': str(policy.normal_end_time),
                            'auto_close_time': str(policy.auto_close_time),
                        },
                        reason = (
                            f'Cierre automatico. Jornada oficial: {policy.normal_end_time}. '
                            f'Cierre configurado a las: {policy.auto_close_time}.'
                        ),
                    )
                    closed_sessions += 1

            # ── Cerrar sesiones de subcontratos ───────────────────────────
            open_sub_sessions = SubcontractSession.objects.filter(
                site=site,
                status='OPEN',
                started_at__date=today,
            )

            for sub_session in open_sub_sessions:
                with transaction.atomic():
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
                            'ended_at':        normal_end_dt_utc.isoformat(),
                            'normal_end_time': str(policy.normal_end_time),
                            'auto_close_time': str(policy.auto_close_time),
                            'reason':          'Cierre automatico por fin de jornada',
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
        f'{closed_sub_sessions} subcontratos cerrados, '
        f'{skipped_holiday} obras saltadas por feriado.'
    )
    return {
        'closed_sessions':     closed_sessions,
        'closed_sub_sessions': closed_sub_sessions,
        'skipped_holiday':     skipped_holiday,
    }
