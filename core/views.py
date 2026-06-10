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

    # Prestador usa el mismo dashboard que admin_obra
    if request.user.actor_type == 'PROVIDER':
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

    base = {
        'site':             site,
        'page_title':       'Dashboard',
        'perms_ctx':        perms_ctx,
        'role_code':        role_code,
        'now':              now,
        'today':            today,
        'open_count':       open_count,
        'closed_today':     closed_today,
        'no_on_site_today': no_on_site_today,
        'unassigned_count': unassigned_count,
        'assigned_count':   assigned_count,
    }

    # ── Supervisor ────────────────────────────────────────────────────────────
    if role_code == 'supervisor':
        my_sessions = open_sessions.filter(started_by=user)

        # Agrupar sesiones por partida
        partidas_activas = {}
        for s in my_sessions:
            key = s.task.name
            if key not in partidas_activas:
                partidas_activas[key] = {
                    'task_name':  s.task.name,
                    'stage_name': s.stage.name,
                    'workers':    [],
                    'count':      0,
                }
            partidas_activas[key]['workers'].append(s.resource.display_name)
            partidas_activas[key]['count'] += 1

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
            'partidas_activas': list(partidas_activas.values()),
            'sesiones_largas':  sesiones_largas,
        })
        return base

    # ── Jefe de terreno y AAC ─────────────────────────────────────────────────
    if role_code in ('jefe_terreno', 'aac'):
        # Top 3 partidas con más trabajadores ahora
        partidas_map = {}
        for s in open_sessions:
            key = s.task.name
            if key not in partidas_map:
                partidas_map[key] = {
                    'task_name':  s.task.name,
                    'stage_name': s.stage.name,
                    'count':      0,
                }
            partidas_map[key]['count'] += 1

        top_partidas = sorted(
            partidas_map.values(),
            key=lambda x: x['count'],
            reverse=True
        )[:3]

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
            'dashboard_type': 'jefe_terreno',
            'top_partidas':   top_partidas,
            'sesiones_largas': sesiones_largas,
        })
        return base

    # ── Administrador de obra y Prestador ─────────────────────────────────────
    if role_code in ('admin_obra', 'administrativo'):
        # HH registradas esta semana vs semana anterior
        from datetime import timedelta
        monday_this = today - timedelta(days=today.weekday())
        monday_last = monday_this - timedelta(weeks=1)

        hh_this_week = _sum_hh(site, monday_this, today)
        hh_last_week = _sum_hh(site, monday_last, monday_this - timedelta(days=1))

        # Partidas sin actividad hace 2+ semanas (activas, no finalizadas)
        two_weeks_ago = today - timedelta(weeks=2)
        partidas_dormidas = _get_dormant_tasks(site, two_weeks_ago)

        # Top 3 partidas activas ahora
        partidas_map = {}
        for s in open_sessions:
            key = s.task.name
            if key not in partidas_map:
                partidas_map[key] = {
                    'task_name':  s.task.name,
                    'stage_name': s.stage.name,
                    'count':      0,
                }
            partidas_map[key]['count'] += 1

        top_partidas = sorted(
            partidas_map.values(),
            key=lambda x: x['count'],
            reverse=True
        )[:3]

        base.update({
            'dashboard_type':    'admin_obra',
            'hh_this_week':      round(hh_this_week, 1),
            'hh_last_week':      round(hh_last_week, 1),
            'hh_delta_pct':      _pct_delta(hh_this_week, hh_last_week),
            'partidas_dormidas': partidas_dormidas,
            'top_partidas':      top_partidas,
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
            'dashboard_type':  'gerencia',
            'pct_asistencia':  pct_asistencia,
            'hh_this_week':    round(hh_this_week, 1),
            'hh_last_week':    round(hh_last_week, 1),
            'hh_delta_pct':    _pct_delta(hh_this_week, hh_last_week),
        })
        return base

    # ── Default (rol no reconocido) ───────────────────────────────────────────
    base['dashboard_type'] = 'default'
    return base


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
