# -*- coding: utf-8 -*-
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from companies.models import SiteMembership
from access.models import UserPreference
from resources.models import Resource, ResourceSiteAssignment
from tracking.models import NoOnSiteEvent
from .models import Stage, TaskCatalog, StageTask, WorkSession
import json


def get_active_site(request):
    """Helper para obtener obra activa del usuario."""
    try:
        return request.user.preference.last_site
    except Exception:
        return None


def require_active_site(view_func):
    """Decorator que redirige a seleccion si no hay obra activa."""
    def wrapper(request, *args, **kwargs):
        if not get_active_site(request):
            return redirect('select_site')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return login_required(wrapper)


@require_active_site
def assignment_new(request):
    """Paso 1: Seleccionar etapa y partida."""
    site = get_active_site(request)

    # Obtener etapas activas de la obra (excluir reprocesos y reservadas)
    stage_tasks = StageTask.objects.select_related(
        'stage', 'task'
    ).filter(
        site=site,
        is_active=True,
        stage__is_active=True,
        task__status='ACTIVE',
        stage__stage_type='NORMAL',
    ).order_by('stage__name', 'display_order', 'task__name')

    # Agrupar por etapa
    etapas = {}
    for st in stage_tasks:
        stage_id = st.stage.id
        if stage_id not in etapas:
            etapas[stage_id] = {
                'stage': st.stage,
                'tasks': []
            }
        etapas[stage_id]['tasks'].append(st.task)

    if request.method == 'POST':
        stage_id = request.POST.get('stage_id')
        task_id = request.POST.get('task_id')

        if stage_id and task_id:
            # Guardar seleccion en sesion Django
            request.session['assignment_stage_id'] = int(stage_id)
            request.session['assignment_task_id'] = int(task_id)
            request.session['assignment_workers'] = []
            return redirect('work:assignment_scan')

    return render(request, 'work/assignment_step1.html', {
        'etapas': etapas.values(),
        'site': site,
        'page_title': 'Nueva asignacion',
        'step': 1,
    })


@require_active_site
def assignment_scan(request):
    """Paso 2: Escanear QRs y armar grupo."""
    site = get_active_site(request)

    stage_id = request.session.get('assignment_stage_id')
    task_id = request.session.get('assignment_task_id')

    if not stage_id or not task_id:
        return redirect('work:assignment_new')

    stage = get_object_or_404(Stage, id=stage_id, site=site)
    task = get_object_or_404(TaskCatalog, id=task_id)

    # Trabajadores ya en el grupo (guardados en sesion)
    worker_ids = request.session.get('assignment_workers', [])
    workers_in_group = Resource.objects.filter(
        id__in=worker_ids
    ).select_related('job_title') if worker_ids else []

    if request.method == 'POST' and 'confirm' in request.POST:
        # Ir al paso 3
        return redirect('work:assignment_confirm')

    return render(request, 'work/assignment_step2.html', {
        'stage': stage,
        'task': task,
        'workers_in_group': workers_in_group,
        'site': site,
        'page_title': 'Escanear trabajadores',
        'step': 2,
    })


@require_active_site
def scan_qr(request):
    """Procesa el escaneo de un QR y agrega trabajador al grupo."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Metodo no permitido'}, status=405)

    site = get_active_site(request)
    uid = request.POST.get('uid', '').strip()

    if not uid:
        return JsonResponse({'error': 'UID requerido'}, status=400)

    # Buscar recurso por UID
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

    # Verificar que esta asignado a la obra
    assigned = ResourceSiteAssignment.objects.filter(
        resource=resource,
        site=site,
        status='ACTIVE'
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

    # Verificar sesion abierta
    open_session = WorkSession.objects.filter(
        resource=resource,
        site=site,
        status='OPEN'
    ).select_related('task').first()

    # Verificar No en obra
    no_on_site = NoOnSiteEvent.objects.filter(
        resource=resource,
        site=site,
        event_date=timezone.localdate(),
        status='ACTIVE'
    ).first()

    # Agregar al grupo
    worker_ids.append(resource.id)
    request.session['assignment_workers'] = worker_ids
    request.session.modified = True

    response_data = {
        'status': 'ok',
        'worker': {
            'id': resource.id,
            'name': resource.display_name,
            'cargo': resource.job_title.name if resource.job_title else '',
            'initials': ''.join([n[0].upper() for n in resource.display_name.split()[:2]]),
        }
    }

    if open_session:
        response_data['warning'] = {
            'type': 'open_session',
            'message': f'Tiene sesion abierta en: {open_session.task_name_snapshot}',
            'session_id': open_session.id,
        }

    if no_on_site:
        response_data['warning'] = {
            'type': 'no_on_site',
            'message': f'Marcado No en obra: {no_on_site.get_reason_code_display()}',
        }

    return JsonResponse(response_data)


@require_active_site
def remove_from_group(request):
    """Elimina un trabajador del grupo actual."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Metodo no permitido'}, status=405)

    worker_id = int(request.POST.get('worker_id', 0))
    worker_ids = request.session.get('assignment_workers', [])

    if worker_id in worker_ids:
        worker_ids.remove(worker_id)
        request.session['assignment_workers'] = worker_ids
        request.session.modified = True

    return JsonResponse({'status': 'ok', 'count': len(worker_ids)})


@require_active_site
def assignment_confirm(request):
    """Paso 3: Confirmar e iniciar sesiones."""
    site = get_active_site(request)

    stage_id = request.session.get('assignment_stage_id')
    task_id = request.session.get('assignment_task_id')
    worker_ids = request.session.get('assignment_workers', [])

    if not stage_id or not task_id or not worker_ids:
        return redirect('work:assignment_new')

    stage = get_object_or_404(Stage, id=stage_id, site=site)
    task = get_object_or_404(TaskCatalog, id=task_id)
    workers = Resource.objects.filter(
        id__in=worker_ids
    ).select_related('job_title')

    # Verificar No en obra para mostrar advertencias
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
        sessions_created = 0

        with transaction.atomic():
            for worker in workers:
                # Obtener asignacion activa
                assignment = ResourceSiteAssignment.objects.filter(
                    resource=worker,
                    site=site,
                    status='ACTIVE'
                ).first()

                # Crear sesion
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
                    operated_by_role_code='supervisor',
                )
                sessions_created += 1

        # Limpiar sesion Django
        request.session.pop('assignment_stage_id', None)
        request.session.pop('assignment_task_id', None)
        request.session.pop('assignment_workers', None)

        messages.success(
            request,
            f'{sessions_created} sesiones iniciadas en {task.name}.'
        )
        return redirect('work:active_workers')

    return render(request, 'work/assignment_step3.html', {
        'stage': stage,
        'task': task,
        'workers': workers,
        'no_on_site_workers': no_on_site_workers,
        'site': site,
        'page_title': 'Confirmar asignacion',
        'step': 3,
        'now': timezone.now(),
    })


@require_active_site
def active_workers(request):
    """Vista de trabajadores activos con sesiones abiertas."""
    site = get_active_site(request)
    today = timezone.localdate()
    now = timezone.now()

    # Sesiones abiertas hoy
    open_sessions = WorkSession.objects.filter(
        site=site,
        status='OPEN',
    ).select_related(
        'resource', 'resource__job_title', 'task', 'stage'
    ).order_by('started_at')

    # Sesiones cerradas hoy
    closed_today = WorkSession.objects.filter(
        site=site,
        status__in=['CLOSED', 'AUTO_CLOSED'],
        started_at__date=today,
    ).count()

    # Recursos activos sin sesion
    assigned_resources = ResourceSiteAssignment.objects.filter(
        site=site,
        status='ACTIVE'
    ).values_list('resource_id', flat=True)

    resources_with_open = open_sessions.values_list('resource_id', flat=True)

    no_on_site_today = NoOnSiteEvent.objects.filter(
        site=site,
        event_date=today,
        status='ACTIVE'
    ).values_list('resource_id', flat=True)

    unassigned_count = len([
        r for r in assigned_resources
        if r not in resources_with_open and r not in no_on_site_today
    ])

    return render(request, 'work/active_workers.html', {
        'open_sessions': open_sessions,
        'closed_today': closed_today,
        'unassigned_count': unassigned_count,
        'active_count': open_sessions.count(),
        'site': site,
        'page_title': 'Trabajadores activos',
        'now': now,
    })


@require_active_site
@require_POST
def close_session(request, session_id):
    """Cierra una sesion individual."""
    site = get_active_site(request)
    session = get_object_or_404(
        WorkSession, id=session_id, site=site, status='OPEN'
    )

    now = timezone.now()
    duration = int((now - session.started_at).total_seconds() / 60)

    session.ended_at = now
    session.status = 'CLOSED'
    session.ended_by = request.user
    session.closure_origin = 'MANUAL'
    session.duration_minutes = duration
    session.save()

    if request.htmx:
        return HttpResponse(status=204, headers={'HX-Trigger': 'sessionClosed'})

    messages.success(request, f'Sesion de {session.resource.display_name} cerrada.')
    return redirect('work:active_workers')


@require_active_site
@require_POST
def mass_close(request):
    """Cierre masivo de todas las sesiones abiertas."""
    site = get_active_site(request)
    now = timezone.now()

    open_sessions = WorkSession.objects.filter(
        site=site,
        status='OPEN'
    )

    count = 0
    with transaction.atomic():
        for session in open_sessions:
            duration = int((now - session.started_at).total_seconds() / 60)
            session.ended_at = now
            session.status = 'CLOSED'
            session.ended_by = request.user
            session.closure_origin = 'MASS_CLOSE'
            session.duration_minutes = duration
            session.save()
            count += 1

    messages.success(request, f'{count} sesiones cerradas.')
    return redirect('work:active_workers')
