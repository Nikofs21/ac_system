# -*- coding: utf-8 -*-
"""
Tasks de Celery para el modulo analytics.
Generacion del snapshot diario del Informe Diario de productividad.
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='analytics.generate_daily_snapshot')
def generate_daily_snapshot_task(site_id, date_str):
    """
    Genera (o regenera) el DailyProductivitySnapshot de una obra para una
    fecha especifica.

    Se dispara automaticamente desde work.auto_close_sessions apenas se
    cierra el dia de una obra (ver work/tasks.py). Tambien se puede llamar
    a mano desde el shell o un management command para generar snapshots
    de dias historicos que quedaron sin generar (por ejemplo, al activar
    este modulo por primera vez en una obra que ya tenia dias trabajados).

    No hay proteccion de inmutabilidad a este nivel — quien dispare esta
    tarea para un dia que ya tiene snapshot lo va a sobrescribir
    (update_or_create). La regla de "los dias pasados no se recalculan" se
    aplica en el punto de disparo (work/tasks.py no la llama si ya existe),
    no aca, para que siga sirviendo como herramienta de recuperacion manual.
    """
    from datetime import date as date_cls

    from companies.models import Site
    from analytics.calculator import calculate_daily_data
    from analytics.models import DailyProductivitySnapshot

    try:
        site = Site.objects.get(id=site_id)
    except Site.DoesNotExist:
        logger.error(f'generate_daily_snapshot: obra {site_id} no existe.')
        return {'error': 'site_not_found', 'site_id': site_id}

    fecha = date_cls.fromisoformat(date_str)
    data  = calculate_daily_data(site, fecha)

    snapshot, created = DailyProductivitySnapshot.objects.update_or_create(
        site=site, date=fecha, defaults=data
    )

    logger.info(
        f'generate_daily_snapshot: {"creado" if created else "actualizado"} '
        f'{site.name} — {fecha} (trab={data["trab"]}, hh={data["hh"]}, icc={data["icc"]})'
    )
    return {
        'site_id': site_id,
        'date':    date_str,
        'created': created,
        'trab':    data['trab'],
        'hh':      float(data['hh']),
    }
