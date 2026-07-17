# -*- coding: utf-8 -*-
"""
Utilidad compartida para la bandeja de revision de cierres fuera de
horario. Se llama justo antes de session.save() en cada lugar del codigo
que cierra una sesion "a mano" (no el job nocturno de las 2 AM).

No bloquea el cierre en si — el supervisor/prestador puede cerrar cuando
quiera. Esto solo deja una marca (needs_review=True) para que el
prestador la revise despues, sin tener que perseguir a la obra pregunta
por pregunta cada vez que algo se ve raro en el informe.
"""
import pytz
from datetime import datetime as dt

from django.conf import settings


def mark_needs_review_if_late(session, ended_at):
    """
    Evalua session.needs_review en base a la diferencia entre `ended_at`
    (datetime aware, UTC) y el work_end_time oficial del dia de esa obra.
    Modifica el objeto in-place — el caller sigue siendo responsable de
    hacer session.save().

    Si no hay jornada configurada para ese dia (SiteWorkdayConfig.
    vigente_para devuelve None), no se marca nada — no hay una hora
    oficial contra la cual comparar.
    """
    from companies.models import SiteWorkdayConfig

    session.needs_review = False

    site = session.site
    site_tz = pytz.timezone(site.timezone or 'America/Santiago')
    ended_local = ended_at.astimezone(site_tz)

    workday = SiteWorkdayConfig.vigente_para(site, ended_local.date())
    if not workday or not workday.work_end_time or workday.all_day_overtime:
        return

    official_dt = site_tz.localize(
        dt.combine(ended_local.date(), workday.work_end_time)
    )

    diff_minutes = abs((ended_local - official_dt).total_seconds()) / 60
    threshold = getattr(settings, 'REVIEW_CLOSE_THRESHOLD_MINUTES', 45)

    if diff_minutes > threshold:
        session.needs_review = True
