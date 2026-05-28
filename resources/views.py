# -*- coding: utf-8 -*-
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.utils import timezone

from .models import Resource, ResourceSiteAssignment, JobTitle, ResourceCategory
from work.models import WorkSession
from tracking.models import NoOnSiteEvent
from core.permissions import (
    user_has_permission,
    get_user_context_permissions,
)


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


@require_active_site
def worker_list(request):
    """
    Listado de trabajadores asignados a la obra activa.
    Muestra activos e inactivos para poder reactivar.
    """
    site = get_active_site(request)

    if not user_has_permission(request.user, 'resources.view', site):
        return redirect('access_denied')

    today = timezone.localdate()

    # Traer todas las asignaciones a esta obra.
    # Ordenar poniendo ACTIVE primero — así cuando un recurso tiene
    # una asignación ACTIVE y una ENDED anterior, siempre tomamos la ACTIVE.
    assignments = ResourceSiteAssignment.objects.filter(
        site=site,
    ).select_related(
        'resource',
        'resource__job_title',
        'resource__resource_category',
    ).order_by(
        'resource__display_name',
        # ACTIVE < CANCELLED < ENDED alfabéticamente — ponemos las ACTIVE primero
        # usando Case para controlar el orden exacto
    )

    # Construir mapa de resource_id -> mejor asignación
    # "mejor" = ACTIVE > ENDED > CANCELLED
    STATUS_PRIORITY = {'ACTIVE': 0, 'ENDED': 1, 'CANCELLED': 2}
    best_assignment = {}
    for assignment in assignments:
        rid = assignment.resource_id
        if rid not in best_assignment:
            best_assignment[rid] = assignment
        else:
            current_priority = STATUS_PRIORITY.get(best_assignment[rid].status, 99)
            new_priority     = STATUS_PRIORITY.get(assignment.status, 99)
            if new_priority < current_priority:
                best_assignment[rid] = assignment

    open_sessions_map = {
        s.resource_id: s
        for s in WorkSession.objects.filter(
            site=site,
            status='OPEN',
        ).select_related('task', 'stage')
    }

    nos_map = {
        e.resource_id: e
        for e in NoOnSiteEvent.objects.filter(
            site=site,
            event_date=today,
            status='ACTIVE',
        )
    }

    workers = []
    for assignment in sorted(
        best_assignment.values(),
        key=lambda a: a.resource.display_name.lower()
    ):
        resource     = assignment.resource
        open_session = open_sessions_map.get(resource.id)
        nos_event    = nos_map.get(resource.id)
        is_assigned  = assignment.status == 'ACTIVE' and resource.status == 'ACTIVE'

        if nos_event and is_assigned:
            estado = 'nos'
        elif open_session and is_assigned:
            estado = 'session'
        elif is_assigned:
            estado = 'free'
        else:
            estado = 'inactive'

        workers.append({
            'resource':     resource,
            'assignment':   assignment,
            'estado':       estado,
            'open_session': open_session,
            'nos_event':    nos_event,
            'is_assigned':  is_assigned,
        })

    perms_ctx = get_user_context_permissions(request.user, site)

    return render(request, 'resources/worker_list.html', {
        'workers':      workers,
        'site':         site,
        'today':        today,
        'page_title':   'Trabajadores',
        'perms_ctx':    perms_ctx,
        'total':        len(workers),
        'active_count': sum(1 for w in workers if w['is_assigned']),
    })


@login_required
def resource_qr_page(request, uid):
    """
    Página de QR de un recurso.
    Accesible escaneando el QR físico.
    Si el usuario no está autenticado, redirige al login y vuelve aquí.
    Si está autenticado, muestra el formulario operativo del recurso.
    """
    resource = get_object_or_404(Resource, resource_uid=uid, status='ACTIVE')

    # Obtener obra activa del usuario
    site = get_active_site(request)
    if not site:
        return redirect('select_site')

    # Verificar que el recurso pertenece a la empresa de la obra activa
    if resource.company != site.company:
        return render(request, 'resources/qr_wrong_site.html', {
            'resource': resource,
            'site': site,
        })

    # Verificar asignación a la obra activa
    assignment = ResourceSiteAssignment.objects.filter(
        resource=resource,
        site=site,
        status='ACTIVE',
    ).first()

    if not assignment:
        return render(request, 'resources/qr_not_assigned.html', {
            'resource': resource,
            'site': site,
        })

    # Sesión abierta actual
    open_session = WorkSession.objects.filter(
        resource=resource,
        site=site,
        status='OPEN',
    ).select_related('task', 'stage').first()

    # Marca No en obra hoy
    nos_event = NoOnSiteEvent.objects.filter(
        resource=resource,
        site=site,
        event_date=timezone.localdate(),
        status='ACTIVE',
    ).first()

    perms_ctx = get_user_context_permissions(request.user, site)

    return render(request, 'resources/qr_resource.html', {
        'resource':     resource,
        'site':         site,
        'open_session': open_session,
        'nos_event':    nos_event,
        'perms_ctx':    perms_ctx,
        'page_title':   resource.display_name,
        'qr_url':       request.build_absolute_uri(f'/r/{uid}/'),
    })


@require_active_site
def resource_qr_view(request, resource_id):
    """
    Vista de QR de un recurso desde el listado.
    Retorna los datos del recurso para mostrar el QR en el modal.
    """
    site = get_active_site(request)

    if not user_has_permission(request.user, 'resources.view_qr', site):
        return JsonResponse({'error': 'Sin permiso.'}, status=403)

    resource = get_object_or_404(
        Resource,
        id=resource_id,
        company=site.company,
    )

    qr_url = request.build_absolute_uri(f'/r/{resource.resource_uid}/')

    return JsonResponse({
        'id':           resource.id,
        'uid':          resource.resource_uid,
        'name':         resource.display_name,
        'cargo':        resource.job_title.name if resource.job_title else '',
        'rut':          resource.person_rut or '',
        'qr_url':       qr_url,
        'initials':     ''.join([n[0].upper() for n in resource.display_name.split()[:2]]),
    })
