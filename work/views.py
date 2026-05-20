# -*- coding: utf-8 -*-
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.db.models import Q

from companies.models import SiteMembership
from access.models import UserPreference
from resources.models import Resource, ResourceSiteAssignment
from tracking.models import NoOnSiteEvent
from .models import Stage, TaskCatalog, StageTask, WorkSession
from core.permissions import (
    user_has_permission,
    site_feature_enabled,
    get_user_context_permissions,
)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_active_site(request):
    try:
        return request.user.preference.last_site
    except Exception:
        return None


def require_active_site(view_func):
    from functools import wraps
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not get_active_site(request):
            return redirect('select_site')
        return view_func(request, *args, **kwargs)
    return login_required(wrapper)


# ─────────────────────────────────────────────────────────────────────────────
# FLUJO DE ASIGNACION
# ─────────────────────────────────────────────────────────────────────────────

@require_active_site
def assignment_new(request):
    """
    Paso 1: Seleccionar etapa y partida.
    Si viene de una pre-carga (QR o listado), muestra aviso del trabajador.
    Si el usuario inicia el flujo desde cero (sin pre-carga), limpia
    cualquier pre-carga huerfana que haya quedado de una sesion anterior.
    """
    site = get_active_site(request)

    can_people   = user_has_permission(request.user, 'sessions.start_people', site)
    can_machines = user_has_permission(request.user, 'sessions.start_machines', site)

    if not can_people and not can_machines:
        return redirect('access_denied')

    # Si viene directo a /asignar/ sin pre-carga activa, limpiar sesion anterior
    # para evitar que un trabajador pre-cargado persista sin querer.
    # La pre-carga se mantiene solo si viene de assignment_preload (tiene flag).
    coming_from_preload = request.session.get('assignment_from_preload', False)
    if not coming_from_preload:
        # Limpiar cualquier estado previo
        request.session.pop('assignment_stage_id', None)
        request.session.pop('assignment_task_id', None)
        request.session.pop('assignment_workers', None)
        request.session.pop('assignment_preloaded_name', None)

    # Limpiar el flag de pre-carga una vez usado
    request.session.pop('assignment_from_preload', None)

    stage_tasks = StageTask.objects.select_related(
        'stage', 'task'
    ).filter(
        site=site,
        is_active=True,
        stage__is_active=True,
        task__status='ACTIVE',
        stage__stage_type='NORMAL',
    ).order_by('stage__name', 'display_order', 'task__name')

    etapas = {}
    for st in stage_tasks:
        stage_id = st.stage.id
        if stage_id not in etapas:
            etapas[stage_id] = {'stage': st.stage, 'tasks': []}
        etapas[stage_id]['tasks'].append(st.task)

    preloaded_name = request.session.get('assignment_preloaded_name', '')

    if request.method == 'POST':
        stage_id = request.POST.get('stage_id')
        task_id  = request.POST.get('task_id')
        if stage_id and task_id:
            request.session['assignment_stage_id'] = int(stage_id)
            request.session['assignment_task_id']  = int(task_id)
            if not request.session.get('assignment_workers'):
                request.session['assignment_workers'] = []
            request.session.pop('assignment_preloaded_name', None)
            return redirect('work:assignment_scan')

    return render(request, 'work/assignment_step1.html', {
        'etapas':         etapas.values(),
        'site':           site,
        'page_title':     'Nueva asignacion',
        'step':           1,
        'preloaded_name': preloaded_name,
        'perms_ctx':      get_user_context_permissions(request.user, site),
    })


@require_active_site
def assignment_scan(request):
    """Paso 2: Escanear QRs y armar grupo."""
    site = get_active_site(request)

    if not user_has_permission(request.user, 'sessions.start_people', site) and \
       not user_has_permission(request.user, 'sessions.start_machines', site):
        return redirect('access_denied')

    stage_id = request.session.get('assignment_stage_id')
    task_id  = request.session.get('assignment_task_id')
    if not stage_id or not task_id:
        return redirect('work:assignment_new')

    stage = get_object_or_404(Stage, id=stage_id, site=site)
    task  = get_object_or_404(TaskCatalog, id=task_id)

    worker_ids       = request.session.get('assignment_workers', [])
    workers_in_group = Resource.objects.filter(
        id__in=worker_ids
    ).select_related('job_title') if worker_ids else []

    if request.method == 'POST' and 'confirm' in request.POST:
        return redirect('work:assignment_confirm')

    return render(request, 'work/assignment_step2.html', {
        'stage':            stage,
        'task':             task,
        'workers_in_group': workers_in_group,
        'site':             site,
        'page_title':       'Escanear trabajadores',
        'step':             2,
    })


@require_active_site
def scan_qr(request):
    """
    Procesa escaneo de QR o busqueda manual.
    Si el recurso tiene sesion abierta, lo agrega igualmente al grupo
    pero marca la advertencia. El cierre se hace al confirmar en paso 3.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Metodo no permitido'}, status=405)

    site = get_active_site(request)

    if not user_has_permission(request.user, 'sessions.start_people', site) and \
       not user_has_permission(request.user, 'sessions.start_machines', site):
        return JsonResponse({'error': 'Sin permiso para esta accion.'}, status=403)

    uid = request.POST.get('uid', '').strip()
    if not uid:
        return JsonResponse({'error': 'UID requerido'}, status=400)

    try:
        resource = Resource.objects.select_related(
            'job_title', 'resource_category'
        ).get(
            resource_uid=uid,
            company=site.company,
            status='ACTIVE'
        )
    except Resource.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Trabajador no encontrado o no pertenece a esta empresa.'
        }, status=404)

    # Verificar permiso por tipo de recurso
    is_person    = resource.resource_category.resource_type == 'PERSON'
    is_machinery = resource.resource_category.resource_type == 'MACHINERY'

    if is_person and not user_has_permission(request.user, 'sessions.start_people', site):
        return JsonResponse({'status': 'error', 'message': 'Sin permiso para iniciar sesiones de personas.'}, status=403)
    if is_machinery and not user_has_permission(request.user, 'sessions.start_machines', site):
        return JsonResponse({'status': 'error', 'message': 'Sin permiso para iniciar sesiones de maquinarias.'}, status=403)

    # Verificar asignacion a la obra
    assigned = ResourceSiteAssignment.objects.filter(
        resource=resource, site=site, status='ACTIVE'
    ).exists()
    if not assigned:
        return JsonResponse({
            'status': 'error',
            'message': f'{resource.display_name} no esta asignado a esta obra.'
        }, status=400)

    # Verificar si ya esta en el grupo
    worker_ids = request.session.get('assignment_workers', [])
    if resource.id in worker_ids:
        return JsonResponse({
            'status': 'already_in_group',
            'message': f'{resource.display_name} ya esta en el grupo.'
        })

    # Sesion abierta
    open_session = WorkSession.objects.filter(
        resource=resource, site=site, status='OPEN'
    ).select_related('task', 'stage').first()

    # No en obra
    no_on_site = NoOnSiteEvent.objects.filter(
        resource=resource,
        site=site,
        event_date=timezone.localdate(),
        status='ACTIVE'
    ).first()

    # Agregar al grupo — con o sin sesion abierta
    worker_ids.append(resource.id)
    request.session['assignment_workers'] = worker_ids
    request.session.modified = True

    response_data = {
        'status': 'ok',
        'worker': {
            'id':       resource.id,
            'name':     resource.display_name,
            'cargo':    resource.job_title.name if resource.job_title else '',
            'initials': ''.join([n[0].upper() for n in resource.display_name.split()[:2]]),
        }
    }

    # Advertencia de sesion abierta — se cierra automaticamente al confirmar
    if open_session:
        response_data['warning'] = {
            'type':       'open_session',
            'message':    f'Tiene sesion abierta en: {open_session.task_name_snapshot}. Se cerrara al confirmar.',
            'session_id': open_session.id,
        }

    # Advertencia de No en obra — se puede agregar igual
    if no_on_site:
        response_data['warning'] = {
            'type':    'no_on_site',
            'message': f'Marcado No en obra: {no_on_site.get_reason_code_display()}',
        }

    return JsonResponse(response_data)


@require_active_site
def remove_from_group(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Metodo no permitido'}, status=405)

    worker_id  = int(request.POST.get('worker_id', 0))
    worker_ids = request.session.get('assignment_workers', [])

    if worker_id in worker_ids:
        worker_ids.remove(worker_id)
        request.session['assignment_workers'] = worker_ids
        request.session.modified = True

    return JsonResponse({'status': 'ok', 'count': len(worker_ids)})


@require_active_site
def search_resources(request):
    """Busqueda de recursos por nombre o RUT para el paso 2."""
    site = get_active_site(request)

    if not user_has_permission(request.user, 'sessions.start_people', site) and \
       not user_has_permission(request.user, 'sessions.start_machines', site):
        return JsonResponse({'results': []})

    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'results': []})

    worker_ids_in_group = request.session.get('assignment_workers', [])

    can_people   = user_has_permission(request.user, 'sessions.start_people', site)
    can_machines = user_has_permission(request.user, 'sessions.start_machines', site)
    allowed_types = []
    if can_people:   allowed_types.append('PERSON')
    if can_machines: allowed_types.append('MACHINERY')

    resources = Resource.objects.filter(
        site_assignments__site=site,
        site_assignments__status='ACTIVE',
        status='ACTIVE',
        company=site.company,
        resource_category__resource_type__in=allowed_types,
    ).filter(
        Q(normalized_name__icontains=query.lower()) |
        Q(display_name__icontains=query) |
        Q(person_rut__icontains=query.replace('.', '').replace('-', ''))
    ).exclude(
        id__in=worker_ids_in_group
    ).select_related('job_title').distinct()[:8]

    results = []
    for resource in resources:
        results.append({
            'id':       resource.id,
            'uid':      resource.resource_uid,
            'name':     resource.display_name,
            'cargo':    resource.job_title.name if resource.job_title else '',
            'rut':      resource.person_rut or '',
            'initials': ''.join([n[0].upper() for n in resource.display_name.split()[:2]]),
        })

    return JsonResponse({'results': results})


@require_active_site
def assignment_confirm(request):
    """
    Paso 3: Confirmar e iniciar sesiones.
    Si alguno del grupo tiene sesion abierta, la cierra antes de crear la nueva.
    Muestra advertencia en pantalla antes de confirmar.
    """
    site = get_active_site(request)

    if not user_has_permission(request.user, 'sessions.start_people', site) and \
       not user_has_permission(request.user, 'sessions.start_machines', site):
        return redirect('access_denied')

    stage_id   = request.session.get('assignment_stage_id')
    task_id    = request.session.get('assignment_task_id')
    worker_ids = request.session.get('assignment_workers', [])

    if not stage_id or not task_id or not worker_ids:
        return redirect('work:assignment_new')

    stage   = get_object_or_404(Stage, id=stage_id, site=site)
    task    = get_object_or_404(TaskCatalog, id=task_id)
    workers = Resource.objects.filter(id__in=worker_ids).select_related('job_title')

    # Detectar trabajadores con sesion abierta
    workers_with_session = []
    for worker in workers:
        open_session = WorkSession.objects.filter(
            resource=worker, site=site, status='OPEN'
        ).select_related('task', 'stage').first()
        if open_session:
            workers_with_session.append({
                'worker':       worker,
                'open_session': open_session,
            })

    # Detectar marcas No en obra
    no_on_site_workers = []
    for worker in workers:
        nos = NoOnSiteEvent.objects.filter(
            resource=worker,
            site=site,
            event_date=timezone.localdate(),
            status='ACTIVE'
        ).first()
        if nos:
            no_on_site_workers.append({
                'worker': worker,
                'reason': nos.get_reason_code_display()
            })

    if request.method == 'POST' and 'start' in request.POST:
        now = timezone.now()
        sessions_created  = 0
        sessions_replaced = 0

        try:
            role_code = request.user.site_memberships.get(
                site=site, is_active=True
            ).role.code
        except Exception:
            role_code = ''

        with transaction.atomic():
            for worker in workers:
                # Cerrar sesion abierta si existe
                open_session = WorkSession.objects.filter(
                    resource=worker, site=site, status='OPEN'
                ).first()
                if open_session:
                    duration = int((now - open_session.started_at).total_seconds() / 60)
                    open_session.ended_at         = now
                    open_session.status           = 'CLOSED'
                    open_session.ended_by         = request.user
                    open_session.closure_origin   = 'MANUAL'
                    open_session.duration_minutes = duration
                    open_session.save()
                    sessions_replaced += 1

                # Obtener asignacion activa
                assignment = ResourceSiteAssignment.objects.filter(
                    resource=worker, site=site, status='ACTIVE'
                ).first()

                # Crear nueva sesion
                WorkSession.objects.create(
                    company=site.company,
                    site=site,
                    resource=worker,
                    resource_assignment=assignment,
                    stage=stage,
                    task=task,
                    stage_name_snapshot=stage.name,
                    task_code_snapshot=task.code,
                    task_name_snapshot=task.name,
                    risk_level_snapshot=task.risk_level,
                    started_at=now,
                    status='OPEN',
                    started_by=request.user,
                    responsible_supervisor=request.user,
                    operated_by_role_code=role_code,
                )
                sessions_created += 1

        # Limpiar sesion Django
        request.session.pop('assignment_stage_id', None)
        request.session.pop('assignment_task_id', None)
        request.session.pop('assignment_workers', None)
        request.session.pop('assignment_preloaded_name', None)

        msg = f'{sessions_created} sesiones iniciadas en {task.name}.'
        if sessions_replaced:
            msg += f' ({sessions_replaced} sesion{"es" if sessions_replaced > 1 else ""} anterior{"es" if sessions_replaced > 1 else ""} cerrada{"s" if sessions_replaced > 1 else ""})'
        messages.success(request, msg)
        return redirect('work:active_workers')

    return render(request, 'work/assignment_step3.html', {
        'stage':                stage,
        'task':                 task,
        'workers':              workers,
        'workers_with_session': workers_with_session,
        'no_on_site_workers':   no_on_site_workers,
        'site':                 site,
        'page_title':           'Confirmar asignacion',
        'step':                 3,
        'now':                  timezone.now(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# TRABAJADORES ACTIVOS Y CIERRE
# ─────────────────────────────────────────────────────────────────────────────

@require_active_site
def active_workers(request):
    """
    Vista de trabajadores activos con sesiones abiertas.
    Supervisor y Bodeguero ven solo sus propias sesiones.
    Jefe de terreno, AAC, Admin obra y superiores ven todas.
    """
    site  = get_active_site(request)
    today = timezone.localdate()

    # Determinar si el usuario ve solo sus propias sesiones
    try:
        role_code = request.user.site_memberships.get(
            site=site, is_active=True
        ).role.code
    except Exception:
        role_code = ''

    ROLES_OWN_SESSIONS_ONLY = {'supervisor', 'bodeguero'}
    own_only = role_code in ROLES_OWN_SESSIONS_ONLY

    # Filtrar sesiones abiertas
    sessions_filter = {
        'site':   site,
        'status': 'OPEN',
    }
    if own_only:
        sessions_filter['started_by'] = request.user

    open_sessions = WorkSession.objects.filter(
        **sessions_filter
    ).select_related(
        'resource', 'resource__job_title', 'task', 'stage'
    ).order_by('started_at')

    # Sesiones cerradas hoy (propias si corresponde)
    closed_filter = {
        'site':             site,
        'status__in':       ['CLOSED', 'AUTO_CLOSED'],
        'started_at__date': today,
    }
    if own_only:
        closed_filter['started_by'] = request.user

    closed_today = WorkSession.objects.filter(**closed_filter).count()

    # Recursos asignados activamente a la obra
    assigned_resources = ResourceSiteAssignment.objects.filter(
        site=site, status='ACTIVE'
    ).values_list('resource_id', flat=True)

    resources_with_open = open_sessions.values_list('resource_id', flat=True)

    no_on_site_today = NoOnSiteEvent.objects.filter(
        site=site, event_date=today, status='ACTIVE'
    ).values_list('resource_id', flat=True)

    # Sin sesion: solo cuenta recursos relevantes segun scope
    if own_only:
        # El supervisor solo ve cuantos de sus recursos no tienen sesion abierta
        # (los que el mismo ha iniciado alguna vez hoy pero ya cerraron, o sin sesion)
        unassigned_count = 0  # No aplica el concepto de "sin asignar" para supervisor
    else:
        unassigned_count = len([
            r for r in assigned_resources
            if r not in resources_with_open and r not in no_on_site_today
        ])

    perms_ctx = get_user_context_permissions(request.user, site)

    return render(request, 'work/active_workers.html', {
        'open_sessions':    open_sessions,
        'closed_today':     closed_today,
        'unassigned_count': unassigned_count,
        'active_count':     open_sessions.count(),
        'own_only':         own_only,
        'site':             site,
        'page_title':       'Trabajadores activos',
        'now':              timezone.now(),
        'perms_ctx':        perms_ctx,
    })



@require_active_site
@require_POST
def close_session(request, session_id):
    """Cierra una sesion individual."""
    site = get_active_site(request)

    if not user_has_permission(request.user, 'sessions.start_people', site) and \
       not user_has_permission(request.user, 'sessions.start_machines', site):
        return JsonResponse({'error': 'Sin permiso.'}, status=403)

    session = get_object_or_404(
        WorkSession, id=session_id, site=site, status='OPEN'
    )

    now      = timezone.now()
    duration = int((now - session.started_at).total_seconds() / 60)

    session.ended_at         = now
    session.status           = 'CLOSED'
    session.ended_by         = request.user
    session.closure_origin   = 'MANUAL'
    session.duration_minutes = duration
    session.save()

    # Respuesta para HTMX o AJAX (pagina QR)
    if request.htmx:
        return HttpResponse(status=204, headers={'HX-Trigger': 'sessionClosed'})

    # Si viene de fetch() (JS), devolver JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
       'application/json' in request.headers.get('Accept', ''):
        return JsonResponse({'status': 'ok'})

    messages.success(request, f'Sesion de {session.resource.display_name} cerrada.')
    return redirect('work:active_workers')


@require_active_site
@require_POST
def mass_close(request):
    """Cierre masivo de sesiones abiertas propias."""
    site = get_active_site(request)

    if not user_has_permission(request.user, 'bulk_close.own_sessions', site):
        return redirect('access_denied')

    now = timezone.now()

    open_sessions = WorkSession.objects.filter(
        site=site,
        status='OPEN',
        started_by=request.user,
    )

    count = 0
    with transaction.atomic():
        for session in open_sessions:
            duration = int((now - session.started_at).total_seconds() / 60)
            session.ended_at         = now
            session.status           = 'CLOSED'
            session.ended_by         = request.user
            session.closure_origin   = 'MASS_CLOSE'
            session.duration_minutes = duration
            session.save()
            count += 1

    messages.success(request, f'{count} sesiones cerradas.')
    return redirect('work:active_workers')


# ─────────────────────────────────────────────────────────────────────────────
# PRE-CARGA DESDE LISTADO O QR
# ─────────────────────────────────────────────────────────────────────────────

@require_active_site
def assignment_preload(request, resource_id):
    """
    Inicia el flujo de asignacion con un trabajador pre-cargado.
    Establece flag 'assignment_from_preload' para que assignment_new
    no limpie la sesion al entrar.
    """
    site = get_active_site(request)

    if not user_has_permission(request.user, 'sessions.start_people', site) and \
       not user_has_permission(request.user, 'sessions.start_machines', site):
        return redirect('access_denied')

    resource = get_object_or_404(
        Resource,
        id=resource_id,
        company=site.company,
        status='ACTIVE',
    )

    assigned = ResourceSiteAssignment.objects.filter(
        resource=resource, site=site, status='ACTIVE'
    ).exists()

    if not assigned:
        messages.error(
            request,
            f'{resource.display_name} no esta asignado activamente a esta obra.'
        )
        return redirect('resources:worker_list')

    is_person    = resource.resource_category.resource_type == 'PERSON'
    is_machinery = resource.resource_category.resource_type == 'MACHINERY'

    if is_person and not user_has_permission(request.user, 'sessions.start_people', site):
        messages.error(request, 'Sin permiso para iniciar sesiones de personas.')
        return redirect('resources:worker_list')

    if is_machinery and not user_has_permission(request.user, 'sessions.start_machines', site):
        messages.error(request, 'Sin permiso para iniciar sesiones de maquinarias.')
        return redirect('resources:worker_list')

    # Limpiar estado anterior y pre-cargar este trabajador
    request.session['assignment_stage_id']       = None
    request.session['assignment_task_id']        = None
    request.session['assignment_workers']        = [resource.id]
    request.session['assignment_preloaded_name'] = resource.display_name
    request.session['assignment_from_preload']   = True  # Flag para que no se limpie
    request.session.modified = True

    messages.info(
        request,
        f'{resource.display_name} pre-cargado. Selecciona la etapa y partida.'
    )
    return redirect('work:assignment_new')
