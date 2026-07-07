# -*- coding: utf-8 -*-
"""
Calculo del Informe Diario de productividad (MOD) para una obra en un dia dado.

Replica la logica de negocio de generar_informe_v3.py (colacion, clasificacion
de etapas, distribucion proporcional de HH) pero leyendo directamente desde
WorkSession en vez de un Excel exportado a mano. Ver PLAN_DASHBOARD_PRODUCTIVIDAD.md
para el diseño completo acordado.

Uso:
    from analytics.calculator import calculate_daily_data
    data = calculate_daily_data(site, date(2026, 6, 23))
    DailyProductivitySnapshot.objects.update_or_create(
        site=site, date=fecha, defaults=data
    )
"""
import pytz
from collections import defaultdict
from datetime import datetime, time as dtime, timedelta

from companies.models import SiteCargoValor, SiteWorkdayConfig


def has_lunch_gap(sessions):
    """
    True si hubo al menos 45 min de pausa entre sesiones consecutivas del
    mismo trabajador ese dia. Con una sola sesion se asume que no hubo
    colacion. Misma regla que generar_informe_v3.py::has_lunch_gap.
    """
    if len(sessions) == 1:
        return False
    ordenadas = sorted(sessions, key=lambda s: s.started_at)
    for i in range(len(ordenadas) - 1):
        gap_min = (ordenadas[i + 1].started_at - ordenadas[i].ended_at).total_seconds() / 60
        if gap_min >= 45:
            return True
    return False


def clasif_etapa(etapa):
    """
    Clasificacion productivo/contributorio/reprocesos de una etapa.
    Solo se usa para la barra de distribucion en la vista — no se guarda
    en el snapshot, para no congelar una clasificacion que puede cambiar.
    """
    if etapa == 'OTRAS':
        return 'contributorio'
    if etapa == 'REPROCESOS':
        return 'reprocesos'
    return 'productivo'


def build_resumen(daily):
    """
    Deriva el bloque RESUMEN (productivo/contributorio/reprocesos/no
    productivo, HH y costo pagado vs asignado) a partir de un dict con la
    forma de calculate_daily_data() — ya sea recien calculado o leido de
    un DailyProductivitySnapshot guardado.

    Se recalcula siempre al vuelo, nunca se persiste: si clasif_etapa()
    cambia en el futuro, los informes historicos reflejan la clasificacion
    vigente en vez de quedar con una foto congelada del dia que se generaron.
    """
    productivo = contributorio = reprocesos = 0.0
    for e in daily.get('etapas_hh', []):
        clase = clasif_etapa(e['e'])
        if clase == 'contributorio':
            contributorio += e['HH']
        elif clase == 'reprocesos':
            reprocesos += e['HH']
        else:
            productivo += e['HH']

    hh_asignadas   = float(daily.get('hh') or 0)
    hh_pagadas     = float(daily.get('hh_pag') or 0)
    costo_asignado = float(daily.get('costo_hh') or 0)
    costo_pagado   = float(daily.get('costo_pag') or 0)
    no_productivo  = round(hh_pagadas - hh_asignadas, 1)

    suma_clas = round(productivo + contributorio + reprocesos, 1)
    diff      = round(hh_asignadas - suma_clas, 1)

    return {
        'hombres_dia':           daily.get('trab', 0),
        'hh_pagadas':            round(hh_pagadas, 1),
        'hh_asignadas':          round(hh_asignadas, 1),
        'costo_pagado':          int(round(costo_pagado)),
        'costo_asignado':        int(round(costo_asignado)),
        'productivo':            round(productivo, 1),
        'contributorio':         round(contributorio, 1),
        'reprocesos':            round(reprocesos, 1),
        'no_productivo':         no_productivo,
        'alerta_no_clasificado': abs(diff) > 0.15,
        'hh_no_clasificadas':    diff,
    }


def _resultado_vacio():
    return {
        'trab': 0, 'hh': 0, 'costo_hh': 0, 'hh_pag': 0, 'costo_pag': 0, 'icc': 0,
        'avg_start_time': None, 'hm': 0, 'costo_hm': 0, 'maq': 0,
        'etapas_hh': [], 'etapas_hm': [], 'sups': [], 'cargos': [],
        'partidas': [], 'maquinas': [],
    }


def _cargo_de(session):
    return session.resource.job_title.name.upper() if session.resource.job_title else 'SIN CARGO'


def _supervisor_de(session):
    return session.responsible_supervisor or session.started_by


def calculate_daily_data(site, fecha):
    """
    Calcula los datos del Informe Diario para site+fecha.

    Retorna un dict con las mismas claves que los campos de
    DailyProductivitySnapshot (sin 'site' ni 'date'), listo para pasar a
    update_or_create(site=site, date=fecha, defaults=resultado).

    Sirve tanto para generar el snapshot de un dia cerrado (Celery) como
    para calcular "hoy" al vuelo en la vista — es la misma funcion en
    ambos casos, solo cambia si el resultado se persiste o no.
    """
    from work.models import WorkSession

    site_tz = pytz.timezone(site.timezone or 'America/Santiago')

    # ── Ventana UTC del dia local ───────────────────────────────────────
    dia_inicio_local = site_tz.localize(datetime.combine(fecha, dtime.min))
    dia_fin_local    = dia_inicio_local + timedelta(days=1)
    dia_inicio_utc   = dia_inicio_local.astimezone(pytz.utc)
    dia_fin_utc      = dia_fin_local.astimezone(pytz.utc)

    sessions = list(WorkSession.objects.filter(
        site=site,
        status__in=['CLOSED', 'AUTO_CLOSED'],
        ended_at__isnull=False,
        started_at__gte=dia_inicio_utc,
        started_at__lt=dia_fin_utc,
    ).select_related(
        'resource', 'resource__resource_category', 'resource__job_title',
        'responsible_supervisor', 'started_by',
    ))

    if not sessions:
        return _resultado_vacio()

    hh_sessions = [s for s in sessions if s.resource.resource_category.resource_type == 'PERSON']
    hm_sessions = [s for s in sessions if s.resource.resource_category.resource_type == 'MACHINERY']

    cargo_map = {
        cv.cargo.upper(): cv.valor_hh
        for cv in SiteCargoValor.objects.filter(site=site, is_active=True)
    }

    workday = SiteWorkdayConfig.vigente_para(site, fecha)
    hh_pag_dia = workday.hh_pagadas() if workday else 0

    # ── Colacion: se evalua por trabajador, con todas sus sesiones HH ───
    sesiones_por_uid = defaultdict(list)
    for s in hh_sessions:
        sesiones_por_uid[s.resource_id].append(s)
    tiene_colacion = {uid: has_lunch_gap(ss) for uid, ss in sesiones_por_uid.items()}

    # ── Nivel worker-day-cargo-supervisor (equivalente a 'wd' del script) ──
    combo_hh_orig    = defaultdict(float)
    combo_costo_orig = defaultdict(float)
    combo_meta       = {}
    uid_hh_orig_total = defaultdict(float)

    for s in hh_sessions:
        horas = (s.ended_at - s.started_at).total_seconds() / 3600
        cargo = _cargo_de(s)
        sup   = _supervisor_de(s)
        key   = (s.resource_id, cargo, sup.id if sup else None)

        combo_hh_orig[key] += horas
        valor = cargo_map.get(cargo)
        if valor is not None:
            combo_costo_orig[key] += horas * float(valor)
        combo_meta[key] = {'uid': s.resource_id, 'cargo': cargo, 'supervisor': sup}
        uid_hh_orig_total[s.resource_id] += horas

    # HH ajustada por combo: si no hubo colacion, se descuenta 1 HH del
    # trabajador ese dia, prorrateada entre sus combos segun peso de HH.
    combo_hh_adj    = {}
    combo_costo_adj = {}
    combo_tasa      = {}
    for key, hh_orig in combo_hh_orig.items():
        uid = key[0]
        total_uid = uid_hh_orig_total[uid]
        if tiene_colacion.get(uid, False) or total_uid == 0:
            hh_adj = hh_orig
        else:
            hh_adj = hh_orig - (1 * (hh_orig / total_uid))
        tasa = (combo_costo_orig[key] / hh_orig) if hh_orig else 0
        combo_hh_adj[key]    = hh_adj
        combo_costo_adj[key] = hh_adj * tasa
        combo_tasa[key]      = tasa

    # HH_pag: solo la primera aparicion de cada trabajador recibe la
    # jornada completa del dia — la jornada se paga una vez por persona,
    # aunque haya trabajado bajo mas de un cargo/supervisor ese dia.
    # costo_pag usa la tasa de ESE combo (la del cargo bajo el cual se le
    # asigna la jornada), igual que costo_pag_dia en generar_informe_v3.py.
    uid_ya_asignado = set()
    combo_hh_pag_alloc = {}
    combo_costo_pag     = {}
    for key in combo_hh_orig:
        uid = key[0]
        if uid not in uid_ya_asignado:
            combo_hh_pag_alloc[key] = hh_pag_dia
            combo_costo_pag[key]    = hh_pag_dia * combo_tasa[key]
            uid_ya_asignado.add(uid)
        else:
            combo_hh_pag_alloc[key] = 0
            combo_costo_pag[key]    = 0

    # ── Distribuir proporcionalmente a nivel de sesion (etapas / partidas) ──
    etapas_hh_acc = defaultdict(lambda: [0.0, 0.0])   # etapa -> [HH, costo]
    partidas_acc  = defaultdict(float)                # (partida, etapa) -> HH

    for s in hh_sessions:
        horas = (s.ended_at - s.started_at).total_seconds() / 3600
        cargo = _cargo_de(s)
        sup   = _supervisor_de(s)
        key   = (s.resource_id, cargo, sup.id if sup else None)

        hh_orig_combo = combo_hh_orig[key]
        if hh_orig_combo == 0:
            continue
        frac       = horas / hh_orig_combo
        hh_prop    = combo_hh_adj[key] * frac
        costo_prop = combo_costo_adj[key] * frac

        etapa = s.stage_name_snapshot
        etapas_hh_acc[etapa][0] += hh_prop
        etapas_hh_acc[etapa][1] += costo_prop

        partidas_acc[(s.task_name_snapshot, etapa)] += hh_prop

    # ── Supervisores y cargos (nivel worker-day-combo) ──────────────────
    sups_acc   = defaultdict(lambda: [0.0, 0.0, set()])  # nombre -> [HH, costo, {uids}]
    cargos_acc = defaultdict(lambda: [0.0, 0.0])          # cargo -> [HH, costo]

    for key, hh_adj in combo_hh_adj.items():
        meta  = combo_meta[key]
        costo = combo_costo_adj[key]
        sup   = meta['supervisor']
        sup_nombre = (sup.get_full_name() or sup.email) if sup else 'Sin supervisor'

        sups_acc[sup_nombre][0] += hh_adj
        sups_acc[sup_nombre][1] += costo
        sups_acc[sup_nombre][2].add(meta['uid'])

        cargos_acc[meta['cargo']][0] += hh_adj
        cargos_acc[meta['cargo']][1] += costo

    # ── Totales del dia ──────────────────────────────────────────────────
    trab           = len(uid_hh_orig_total)
    hh_total       = sum(combo_hh_adj.values())
    costo_hh_total = sum(combo_costo_adj.values())
    hh_pag_total   = sum(combo_hh_pag_alloc.values())
    costo_pag_total = sum(combo_costo_pag.values())
    icc            = (hh_total / hh_pag_total) if hh_pag_total else 0

    # ── Hora promedio de inicio de jornada (sesiones que parten antes de las 13:00) ──
    minutos = []
    for s in hh_sessions:
        inicio_local = s.started_at.astimezone(site_tz)
        if inicio_local.hour < 13:
            minutos.append(inicio_local.hour * 60 + inicio_local.minute)
    avg_start_time = None
    if minutos:
        prom = round(sum(minutos) / len(minutos))
        avg_start_time = dtime(prom // 60, prom % 60)

    # ── HM (Horas Maquina) — solo si la obra tiene maquinaria trackeada ──
    hm_total, costo_hm_total, maq = 0.0, 0, 0
    etapas_hm_list, maquinas_list = [], []

    if hm_sessions:
        hm_uid_horas = defaultdict(float)
        hm_uid_costo = defaultdict(float)
        etapas_hm_acc  = defaultdict(lambda: [0.0, 0.0])
        maquinas_acc   = defaultdict(lambda: [0.0, 0.0])  # (nombre, tipo) -> [HM, costo]

        for s in hm_sessions:
            horas = (s.ended_at - s.started_at).total_seconds() / 3600
            cargo = _cargo_de(s)
            valor = cargo_map.get(cargo)
            costo = horas * float(valor) if valor is not None else 0.0

            hm_uid_horas[s.resource_id] += horas
            hm_uid_costo[s.resource_id] += costo

            etapa = s.stage_name_snapshot
            etapas_hm_acc[etapa][0] += horas
            etapas_hm_acc[etapa][1] += costo

            maquinas_acc[(s.resource.display_name, cargo)][0] += horas
            maquinas_acc[(s.resource.display_name, cargo)][1] += costo

        hm_total       = sum(hm_uid_horas.values())
        costo_hm_total = int(round(sum(hm_uid_costo.values())))
        maq            = len(hm_uid_horas)

        etapas_hm_list = [
            {'e': e, 'HM': round(v[0], 1), 'c': int(round(v[1]))}
            for e, v in sorted(etapas_hm_acc.items(), key=lambda kv: -kv[1][0])
        ]
        maquinas_list = [
            {'n': n, 'tipo': t, 'HM': round(v[0], 1), 'c': int(round(v[1]))}
            for (n, t), v in sorted(maquinas_acc.items(), key=lambda kv: -kv[1][1])
        ]

    # ── Armar listas finales (misma forma que produce generar_informe_v3.py) ──
    etapas_hh_list = [
        {'e': e, 'HH': round(v[0], 1), 'c': int(round(v[1]))}
        for e, v in sorted(etapas_hh_acc.items(), key=lambda kv: -kv[1][0])
        if v[0] > 0
    ]
    sups_list = [
        {'n': n, 'HH': round(v[0], 1), 'c': int(round(v[1])), 't': len(v[2])}
        for n, v in sorted(sups_acc.items(), key=lambda kv: -kv[1][0])
    ]
    cargos_list = [
        {'n': c, 'HH': round(v[0], 1), 'c': int(round(v[1]))}
        for c, v in sorted(cargos_acc.items(), key=lambda kv: -kv[1][1])
    ]
    partidas_list = [
        {'p': p, 'e': e, 'HH': round(hh, 1)}
        for (p, e), hh in sorted(partidas_acc.items(), key=lambda kv: -kv[1])[:6]
        if hh > 0
    ]

    return {
        'trab':           trab,
        'hh':             round(hh_total, 2),
        'costo_hh':       int(round(costo_hh_total)),
        'hh_pag':         round(hh_pag_total, 2),
        'costo_pag':      int(round(costo_pag_total)),
        'icc':            round(icc, 4),
        'avg_start_time': avg_start_time,
        'hm':             round(hm_total, 2),
        'costo_hm':       costo_hm_total,
        'maq':            maq,
        'etapas_hh':      etapas_hh_list,
        'etapas_hm':      etapas_hm_list,
        'sups':           sups_list,
        'cargos':         cargos_list,
        'partidas':       partidas_list,
        'maquinas':       maquinas_list,
    }
