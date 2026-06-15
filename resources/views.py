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
from core.utils import get_active_site


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
    Soporta filtros: active, with_session, without_session, inactive.
    Pestaña 'active' muestra checkboxes para descarga masiva de QRs.
    """
    site = get_active_site(request)

    if not user_has_permission(request.user, 'resources.view', site):
        return redirect('access_denied')

    today         = timezone.localdate()
    active_filter = request.GET.get('filter', 'active')

    # ── IDs base para cálculos ────────────────────────────────────────────
    all_assigned_ids = ResourceSiteAssignment.objects.filter(
        site=site, status='ACTIVE'
    ).values_list('resource_id', flat=True)

    open_session_ids = WorkSession.objects.filter(
        site=site, status='OPEN'
    ).values_list('resource_id', flat=True)

    # ── Counts para los tabs ──────────────────────────────────────────────
    counts = {
        'active': Resource.objects.filter(
            id__in=all_assigned_ids, status='ACTIVE'
        ).count(),
        'with_session': Resource.objects.filter(
            id__in=open_session_ids, status='ACTIVE'
        ).count(),
        'without_session': Resource.objects.filter(
            id__in=all_assigned_ids, status='ACTIVE'
        ).exclude(id__in=open_session_ids).count(),
        'inactive': Resource.objects.filter(
            company=site.company, status='INACTIVE'
        ).count(),
    }

    # ── Construir queryset según filtro ───────────────────────────────────
    base_active = Resource.objects.filter(
        id__in=all_assigned_ids, status='ACTIVE'
    ).select_related('job_title', 'resource_category')

    if active_filter == 'active':
        resources_qs = base_active
    elif active_filter == 'with_session':
        resources_qs = Resource.objects.filter(
            id__in=open_session_ids, status='ACTIVE'
        ).select_related('job_title', 'resource_category')
    elif active_filter == 'without_session':
        resources_qs = base_active.exclude(id__in=open_session_ids)
    elif active_filter == 'inactive':
        resources_qs = Resource.objects.filter(
            company=site.company, status='INACTIVE'
        ).select_related('job_title', 'resource_category')
    else:
        resources_qs = base_active

    resources_qs = resources_qs.order_by('display_name')

    # ── Mapas auxiliares ──────────────────────────────────────────────────
    open_sessions_map = {
        s.resource_id: s
        for s in WorkSession.objects.filter(
            site=site, status='OPEN'
        ).select_related('task', 'stage')
    }

    nos_map = {
        e.resource_id: e
        for e in NoOnSiteEvent.objects.filter(
            site=site, event_date=today, status='ACTIVE'
        )
    }

    # ── Construir lista de workers con propiedades extra ──────────────────
    workers = []
    for resource in resources_qs:
        open_session = open_sessions_map.get(resource.id)
        nos_event    = nos_map.get(resource.id)
        is_assigned  = resource.id in all_assigned_ids and resource.status == 'ACTIVE'

        # Anotar propiedades para el template
        resource.has_open_session    = open_session is not None
        resource.is_active_assignment = is_assigned
        resource.open_session        = open_session
        resource.nos_event           = nos_event

        workers.append(resource)

    perms_ctx = get_user_context_permissions(request.user, site)

    return render(request, 'resources/worker_list.html', {
        'workers':       workers,
        'site':          site,
        'today':         today,
        'page_title':    'Trabajadores',
        'perms_ctx':     perms_ctx,
        'active_filter': active_filter,
        'counts':        counts,
        'total':         len(workers),
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
