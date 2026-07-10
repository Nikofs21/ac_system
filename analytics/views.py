# -*- coding: utf-8 -*-
"""
Vista del Informe Diario de productividad (MOD).

Arma el mismo formato de datos (DAILY / RESUMEN / DATE_SEM) que produce
generar_informe_v3.py, pero leyendo DailyProductivitySnapshot (dias ya
cerrados) + calculate_daily_data al vuelo (hoy). El template consume estos
datos con exactamente la misma logica JS del HTML de referencia.
"""
from datetime import date as date_cls, timedelta

from django.utils.dateparse import parse_date

from core.permissions import require_permission
from analytics.calculator import calculate_daily_data, build_resumen

# Meses en español para el rango de semana (mismo formato que fmt_date() del script)
_MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

# Cuantos dias de historial se embeben en la pagina como maximo. El
# selector de fecha y el grafico de tendencia (7 dias) funcionan sobre este
# rango. Ajustable si con el tiempo se necesita ver mas historial de una.
MAX_HISTORY_DAYS = 60


def _fmt_date_es(d):
    return f'{d.day:02d} {_MESES[d.month - 1]}'


def _week_range_label(fecha):
    lunes = fecha - timedelta(days=fecha.weekday())
    domingo = lunes + timedelta(days=6)
    return f'{_fmt_date_es(lunes)} — {_fmt_date_es(domingo)}'


def _week_label(site, fecha):
    try:
        return site.week_config.get_week_label_for_date(fecha)
    except Exception:
        # Obra sin SiteWeekConfig configurado: fallback generico para no
        # romper la pagina, pero el informe deberia configurarse igual.
        return f'Sem {fecha.isocalendar()[1]}'


def _build_daily_entry(data, fecha, site):
    """
    Convierte un dict con la forma de calculate_daily_data() (recien
    calculado, o reconstruido desde un DailyProductivitySnapshot) en la
    forma DAILY[fecha] que espera el JS del template — identica a la que
    produce generar_informe_v3.py.
    """
    hh_pag = float(data['hh_pag'] or 0)
    hh     = float(data['hh'] or 0)
    hm     = float(data['hm'] or 0)
    pct_asig = round(hh / hh_pag * 100) if hh_pag else 0

    avg_start_time = data.get('avg_start_time')
    hora_inicio = avg_start_time.strftime('%H:%M') if avg_start_time else '—'

    return {
        'sem':        _week_label(site, fecha),
        'sem_rng':    _week_range_label(fecha),
        'trab':       data['trab'],
        'HH':         round(hh, 1),
        'costo_hh':   int(data['costo_hh'] or 0),
        'HH_pag':     round(hh_pag, 1),
        'pct_asig':   pct_asig,
        'hora_inicio': hora_inicio,
        'HM':         round(hm, 1),
        'costo_hm':   int(data['costo_hm'] or 0),
        'maq':        data['maq'],
        'has_hm':     1 if hm > 0 else 0,
        'etapas_hh':  data['etapas_hh'],
        'etapas_hm':  data['etapas_hm'],
        'sups':       data['sups'],
        'cargos':     data['cargos'],
        'maquinas':   data['maquinas'],
        'partidas':   data['partidas'],
        'sin_asignacion': 1 if data['trab'] == 0 else 0,
        # Se guarda tambien costo_pag (no lo usa el JS del informe diario,
        # pero build_resumen() lo necesita para calcular el costo pagado).
        'costo_pag':  int(data['costo_pag'] or 0),
    }


def _snapshot_as_calc_dict(snap):
    """Reconstruye el dict de calculate_daily_data() a partir de un snapshot guardado."""
    return {
        'trab': snap.trab, 'hh': snap.hh, 'costo_hh': snap.costo_hh,
        'hh_pag': snap.hh_pag, 'costo_pag': snap.costo_pag, 'icc': snap.icc,
        'avg_start_time': snap.avg_start_time, 'hm': snap.hm, 'costo_hm': snap.costo_hm,
        'maq': snap.maq, 'etapas_hh': snap.etapas_hh, 'etapas_hm': snap.etapas_hm,
        'sups': snap.sups, 'cargos': snap.cargos, 'partidas': snap.partidas,
        'maquinas': snap.maquinas,
    }


@require_permission('dashboard.productivity')
def productivity_dashboard(request):
    from django.shortcuts import render
    from companies.models import SiteConfig
    from analytics.models import DailyProductivitySnapshot

    site = request.user.preference.last_site

    today = date_cls.today()
    fecha_str = request.GET.get('fecha')
    selected_date = parse_date(fecha_str) if fecha_str else None
    if not selected_date:
        selected_date = today

    try:
        tiene_hm = bool(site.config.use_machinery)
    except SiteConfig.DoesNotExist:
        tiene_hm = False

    desde = today - timedelta(days=MAX_HISTORY_DAYS)
    snapshots = DailyProductivitySnapshot.objects.filter(
        site=site, date__gte=desde
    ).order_by('date')

    daily   = {}
    resumen = {}
    date_sem = {}

    for snap in snapshots:
        fstr = snap.date.isoformat()
        data = _snapshot_as_calc_dict(snap)
        entry = _build_daily_entry(data, snap.date, site)
        daily[fstr]    = entry
        resumen[fstr]  = build_resumen(data)
        date_sem[fstr] = entry['sem']

    # "Hoy" nunca tiene snapshot guardado — se calcula al vuelo y se agrega
    # igual, para que siempre aparezca en el selector y en la tendencia.
    today_str = today.isoformat()
    if today_str not in daily:
        data_hoy  = calculate_daily_data(site, today)
        entry_hoy = _build_daily_entry(data_hoy, today, site)
        daily[today_str]    = entry_hoy
        resumen[today_str]  = build_resumen(data_hoy)
        date_sem[today_str] = entry_hoy['sem']

    dias_con_datos = [d for d in daily.values() if d['trab'] > 0]
    avg_hh = round(sum(d['HH'] for d in dias_con_datos) / len(dias_con_datos), 1) if dias_con_datos else 0

    selected_str = selected_date.isoformat()
    if selected_str not in daily:
        selected_str = today_str

    context = {
        'site':          site,
        'page_title':    'Informe diario de productividad',
        'daily':         daily,
        'resumen':       resumen,
        'date_sem':      date_sem,
        'avg_hh':        avg_hh,
        'tiene_hm_js':   'true' if tiene_hm else 'false',
        'hm_col1':       '340px' if tiene_hm else '260px',
        'selected_date_str': selected_str,
    }
    return render(request, 'analytics/productivity_dashboard.html', context)
