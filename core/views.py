# -*- coding: utf-8 -*-
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone

from companies.models import SiteMembership, CompanyMembership
from access.models import UserPreference
from core.permissions import get_user_context_permissions, site_feature_enabled


@login_required
def dashboard(request):
    try:
        pref = request.user.preference
        if not pref.last_site:
            return redirect('select_site')
    except UserPreference.DoesNotExist:
        return redirect('select_site')

    site      = request.user.preference.last_site
    perms_ctx = get_user_context_permissions(request.user, site)
    role_code = perms_ctx.get('role_code', '')

    # Prestador y novus_super usan el mismo dashboard que admin_obra.
    # Se chequean ambas condiciones por separado (no solo actor_type) porque
    # is_novus_super no garantiza actor_type=PROVIDER si alguien lo edita
    # a mano desde el admin — son dos campos independientes.
    if request.user.actor_type == 'PROVIDER' or request.user.is_novus_super:
        role_code = 'admin_obra'

    context = _build_dashboard_context(request.user, site, role_code, perms_ctx)
    return render(request, 'dashboard.html', context)


def _build_dashboard_context(user, site, role_code, perms_ctx):
    """Construye el contexto del dashboard según el rol."""
    from work.models import WorkSession
    from tracking.models import NoOnSiteEvent

    now   = timezone.now()
    today = timezone.localdate()

    # ── Datos base comunes ────────────────────────────────────────────────────
    open_sessions = WorkSession.objects.filter(
        site=site, status='OPEN'
    ).select_related('resource', 'task', 'stage', 'resource__job_title')

    closed_today = WorkSession.objects.filter(
        site=site,
        status__in=['CLOSED', 'AUTO_CLOSED'],
        started_at__date=today,
    ).count()

    no_on_site_today = NoOnSiteEvent.objects.filter(
        site=site, event_date=today, status='ACTIVE'
    ).count()

    from resources.models import ResourceSiteAssignment
    assigned_count = ResourceSiteAssignment.objects.filter(
        site=site, status='ACTIVE'
    ).count()

    open_count      = open_sessions.count()
    unassigned_count = max(0, assigned_count - open_count - no_on_site_today)

    # ── Job cards: partidas que el usuario inicio y siguen abiertas ────────────
    # Disponible para CUALQUIER rol con permiso de iniciar sesiones, no una
    # lista fija de roles — un administrativo con autorizacion tambien debe
    # verlas, igual que un supervisor.
    from core.permissions import user_has_permission
    puede_iniciar_sesiones = (
        user_has_permission(user, 'sessions.start_people', site) or
        user_has_permission(user, 'sessions.start_machines', site)
    )
    mis_partidas_activas = []
    if puede_iniciar_sesiones:
        mis_partidas_activas = _agrupar_partidas_activas(
            open_sessions.filter(started_by=user)
        )

    base = {
        'site':                   site,
        'page_title':             'Dashboard',
        'perms_ctx':              perms_ctx,
        'role_code':              role_code,
        'full_screen':            True,
        'now':                    now,
        'today':                  today,
        'open_count':             open_count,
        'closed_today':           closed_today,
        'no_on_site_today':       no_on_site_today,
        'unassigned_count':       unassigned_count,
        'assigned_count':         assigned_count,
        'puede_iniciar_sesiones': puede_iniciar_sesiones,
        'mis_partidas_activas':   mis_partidas_activas,
    }

    # ── Supervisor ────────────────────────────────────────────────────────────
    if role_code == 'supervisor':
        my_sessions = open_sessions.filter(started_by=user)

        # Detectar sesiones largas (más de 10 horas abiertas)
        sesiones_largas = []
        for s in my_sessions:
            horas = (now - s.started_at).total_seconds() / 3600
            if horas > 10:
                sesiones_largas.append({
                    'worker': s.resource.display_name,
                    'horas':  round(horas, 1),
                    'task':   s.task.name,
                })

        base.update({
            'dashboard_type':   'supervisor',
            'my_open_count':    my_sessions.count(),
            'my_closed_today':  WorkSession.objects.filter(
                site=site,
                started_by=user,
                status__in=['CLOSED', 'AUTO_CLOSED'],
                started_at__date=today,
            ).count(),
            'partidas_activas': mis_partidas_activas,
            'sesiones_largas':  sesiones_largas,
        })
        return base

    # ── Jefe de terreno y AAC ─────────────────────────────────────────────────
    if role_code in ('jefe_terreno', 'aac'):
        # Sesiones largas (más de 10 horas)
        sesiones_largas = []
        for s in open_sessions:
            horas = (now - s.started_at).total_seconds() / 3600
            if horas > 10:
                sesiones_largas.append({
                    'worker': s.resource.display_name,
                    'horas':  round(horas, 1),
                    'task':   s.task.name,
                })

        base.update({
            'dashboard_type':  'jefe_terreno',
            'top_partidas':    _top_partidas_por_gente(open_sessions, limit=3),
            'sesiones_largas': sesiones_largas,
        })
        return base

    # ── Administrador de obra y Prestador ─────────────────────────────────────
    if role_code == 'admin_obra':
        # HH registradas esta semana vs semana anterior
        from datetime import timedelta
        monday_this = today - timedelta(days=today.weekday())
        monday_last = monday_this - timedelta(weeks=1)

        hh_this_week = _sum_hh(site, monday_this, today)
        hh_last_week = _sum_hh(site, monday_last, monday_this - timedelta(days=1))

        # Partidas sin actividad hace 2+ semanas (activas, no finalizadas)
        two_weeks_ago = today - timedelta(weeks=2)
        partidas_dormidas = _get_dormant_tasks(site, two_weeks_ago)

        base.update({
            'dashboard_type':      'admin_obra',
            'hh_this_week':        round(hh_this_week, 1),
            'hh_last_week':        round(hh_last_week, 1),
            'hh_delta_pct':        _pct_delta(hh_this_week, hh_last_week),
            'partidas_dormidas':   partidas_dormidas,
            'top_partidas':        _top_partidas_por_gente(open_sessions, limit=3),
            'top_partidas_presupuesto': _top_partidas_por_presupuesto(open_sessions, limit=5),
        })
        return base

    # ── Administrativo ───────────────────────────────────────────────────────
    # Rol distinto de admin_obra: gestiona trabajadores/maquinas, MOI y
    # organigrama — no hace seguimiento de partidas ni HH, asi que no ve
    # ese tipo de datos aca (solo lo que ya viene en 'base': sesiones
    # abiertas, cierres de hoy, y sus job cards si se le dio autorizacion
    # explicita para iniciar sesiones — eso ya se resuelve por permiso,
    # no por rol, mas arriba).
    if role_code == 'administrativo':
        base.update({
            'dashboard_type': 'administrativo',
        })
        return base

    # ── Gerencia ──────────────────────────────────────────────────────────────
    if role_code == 'gerencia':
        pct_asistencia = round(
            (open_count / assigned_count * 100) if assigned_count > 0 else 0, 1
        )
        from datetime import timedelta
        monday_this = today - timedelta(days=today.weekday())
        monday_last = monday_this - timedelta(weeks=1)
        hh_this_week = _sum_hh(site, monday_this, today)
        hh_last_week = _sum_hh(site, monday_last, monday_this - timedelta(days=1))

        base.update({
            'dashboard_type':      'gerencia',
            'pct_asistencia':      pct_asistencia,
            'hh_this_week':        round(hh_this_week, 1),
            'hh_last_week':        round(hh_last_week, 1),
            'hh_delta_pct':        _pct_delta(hh_this_week, hh_last_week),
            'top_partidas':        _top_partidas_por_gente(open_sessions, limit=3),
            'top_partidas_presupuesto': _top_partidas_por_presupuesto(open_sessions, limit=5),
        })
        return base

    # ── Default (rol no reconocido) ───────────────────────────────────────────
    base['dashboard_type'] = 'default'
    return base


def _agrupar_partidas_activas(sessions_qs):
    """
    Agrupa sesiones abiertas por partida (stage+task). Usada para las
    'job cards' del dashboard — sesiones que el propio usuario inicio y
    siguen abiertas, para poder cerrarlas todas de una partida con un
    solo atajo (ver work.views.close_by_task).
    """
    partidas = {}
    for s in sessions_qs:
        key = (s.stage_id, s.task_id)
        if key not in partidas:
            partidas[key] = {
                'task_id':    s.task_id,
                'task_name':  s.task.name,
                'stage_name': s.stage.name,
                'workers':    [],
                'count':      0,
            }
        partidas[key]['workers'].append(s.resource.display_name)
        partidas[key]['count'] += 1
    return list(partidas.values())


def _top_partidas_por_gente(open_sessions, limit=3):
    """Partidas con sesion abierta ahora, ordenadas por cantidad de gente."""
    partidas_map = {}
    for s in open_sessions:
        key = (s.stage_id, s.task_id)
        if key not in partidas_map:
            partidas_map[key] = {
                'task_name':  s.task.name,
                'stage_name': s.stage.name,
                'count':      0,
            }
        partidas_map[key]['count'] += 1

    return sorted(
        partidas_map.values(), key=lambda x: x['count'], reverse=True
    )[:limit]


def _top_partidas_por_presupuesto(open_sessions, limit=5):
    """
    Partidas con sesion abierta ahora, ordenadas por presupuesto_total —
    no por cantidad de gente. Una partida con poca gente pero mucho
    presupuesto en juego (ej. mayoritariamente materiales) no deberia
    pasar desapercibida solo porque tiene pocos trabajadores asignados.
    """
    from work.models import StageTask

    combos_activos = set(open_sessions.values_list('stage_id', 'task_id').distinct())
    if not combos_activos:
        return []

    stage_ids = {c[0] for c in combos_activos}
    task_ids  = {c[1] for c in combos_activos}

    stage_tasks = StageTask.objects.filter(
        stage_id__in=stage_ids,
        task_id__in=task_ids,
        presupuesto_total__isnull=False,
    ).select_related('stage', 'task')

    resultado = [
        {
            'task_name':             st.task.name,
            'stage_name':            st.stage.name,
            'presupuesto_total':     st.presupuesto_total,
            'presupuesto_total_fmt': f'{int(st.presupuesto_total):,}'.replace(',', '.'),
        }
        for st in stage_tasks
        if (st.stage_id, st.task_id) in combos_activos
    ]
    resultado.sort(key=lambda x: x['presupuesto_total'], reverse=True)
    return resultado[:limit]


def _sum_hh(site, date_from, date_to):
    """Suma HH (duracion_minutes / 60) de sesiones cerradas en un rango."""
    from work.models import WorkSession
    from django.db.models import Sum
    result = WorkSession.objects.filter(
        site=site,
        status__in=['CLOSED', 'AUTO_CLOSED'],
        started_at__date__gte=date_from,
        started_at__date__lte=date_to,
        duration_minutes__isnull=False,
    ).aggregate(total=Sum('duration_minutes'))
    total_min = result['total'] or 0
    return total_min / 60


def _pct_delta(current, previous):
    """Calcula delta porcentual entre dos valores."""
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


def _get_dormant_tasks(site, cutoff_date):
    """
    Retorna partidas que tuvieron sesiones alguna vez pero
    no han tenido actividad desde cutoff_date y no están al 100%.
    """
    from work.models import WorkSession, StageTask
    from django.db.models import Max

    # Última sesión por partida en esta obra
    last_session = WorkSession.objects.filter(
        site=site,
    ).values('task_id').annotate(last=Max('started_at__date'))

    dormant = []
    for entry in last_session:
        if entry['last'] and entry['last'] < cutoff_date:
            from work.models import TaskCatalog
            try:
                task = TaskCatalog.objects.get(id=entry['task_id'])
                dormant.append({
                    'task_name':  task.name,
                    'last_seen':  entry['last'],
                    'days_ago':   (timezone.localdate() - entry['last']).days,
                })
            except TaskCatalog.DoesNotExist:
                continue

    # Ordenar por más tiempo sin actividad
    dormant.sort(key=lambda x: x['days_ago'], reverse=True)
    return dormant[:5]  # máximo 5


# ─────────────────────────────────────────────────────────────────────────────
# RESTO DE VISTAS (sin cambios)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def select_site(request):
    site_memberships = SiteMembership.objects.select_related(
        'site', 'site__company', 'role'
    ).filter(
        user=request.user,
        is_active=True,
        site__status='ACTIVE'
    ).order_by('site__company__name', 'site__name')

    if request.method == 'POST':
        site_membership_id = request.POST.get('site_membership_id')
        if site_membership_id:
            try:
                membership = site_memberships.get(id=site_membership_id)
                pref, created = UserPreference.objects.get_or_create(
                    user=request.user
                )
                pref.last_site    = membership.site
                pref.last_company = membership.site.company
                pref.save()
                messages.success(request, f'Obra activa: {membership.site.name}')
                return redirect('dashboard')
            except SiteMembership.DoesNotExist:
                messages.error(request, 'Obra no valida.')

    return render(request, 'select_site.html', {
        'site_memberships': site_memberships,
        'page_title':       'Seleccionar obra',
        'full_screen':      True,
    })


@login_required
def change_site(request):
    try:
        pref           = request.user.preference
        pref.last_site    = None
        pref.last_company = None
        pref.save()
    except UserPreference.DoesNotExist:
        pass
    return redirect('select_site')


@login_required
def access_denied(request):
    return render(request, 'access_denied.html', {
        'page_title': 'Acceso denegado',
    }, status=403)


@login_required
def feature_disabled(request):
    return render(request, 'feature_disabled.html', {
        'page_title': 'Funcionalidad no disponible',
    })
