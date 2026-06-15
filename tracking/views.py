# -*- coding: utf-8 -*-
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db import transaction

from resources.models import Resource, ResourceSiteAssignment
from work.models import WorkSession
from .models import NoOnSiteEvent
from access.models import UserPreference
from core.permissions import (
    user_has_permission,
    site_feature_enabled,
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
def no_on_site(request):
    """Vista principal de No en obra."""
    site = get_active_site(request)

    # Verificar feature flag
    if not site_feature_enabled(site, 'no_on_site'):
        return redirect('feature_disabled')

    # Verificar permiso
    if not user_has_permission(request.user, 'no_en_obra.manage', site):
        return redirect('access_denied')

    today = timezone.localdate()

    assignments = ResourceSiteAssignment.objects.filter(
        site=site,
        status='ACTIVE',
        resource__status='ACTIVE',
    ).select_related(
        'resource',
        'resource__job_title',
    ).order_by('resource__display_name')

    open_sessions = WorkSession.objects.filter(
        site=site,
        status='OPEN',
    ).select_related('task', 'stage')
    open_sessions_map = {s.resource_id: s for s in open_sessions}

    nos_events = NoOnSiteEvent.objects.filter(
        site=site,
        event_date=today,
        status='ACTIVE',
    ).select_related('marked_by')
    nos_map = {e.resource_id: e for e in nos_events}

    workers = []
    for assignment in assignments:
        resource    = assignment.resource
        open_session = open_sessions_map.get(resource.id)
        nos_event    = nos_map.get(resource.id)

        if nos_event:
            estado = 'nos'
        elif open_session:
            estado = 'session'
        else:
            estado = 'free'

        workers.append({
            'resource':     resource,
            'estado':       estado,
            'open_session': open_session,
            'nos_event':    nos_event,
        })

    nos_count = sum(1 for w in workers if w['estado'] == 'nos')

    return render(request, 'tracking/no_on_site.html', {
        'workers':     workers,
        'nos_count':   nos_count,
        'total_count': len(workers),
        'site':        site,
        'today':       today,
        'page_title':  'No en obra',
        'perms_ctx':   get_user_context_permissions(request.user, site),
    })


@require_active_site
def no_on_site_detail(request, resource_id):
    """Retorna JSON con detalle de un trabajador para el modal."""
    site  = get_active_site(request)
    today = timezone.localdate()

    if not user_has_permission(request.user, 'no_en_obra.manage', site):
        return JsonResponse({'error': 'Sin permiso para esta accion.'}, status=403)

    resource = get_object_or_404(
        Resource,
        id=resource_id,
        company=site.company,
        status='ACTIVE',
    )

    assigned = ResourceSiteAssignment.objects.filter(
        resource=resource,
        site=site,
        status='ACTIVE',
    ).exists()

    if not assigned:
        return JsonResponse({'error': 'Trabajador no asignado a esta obra.'}, status=400)

    open_session = WorkSession.objects.filter(
        resource=resource,
        site=site,
        status='OPEN',
    ).select_related('task', 'stage').first()

    nos_event = NoOnSiteEvent.objects.filter(
        resource=resource,
        site=site,
        event_date=today,
        status='ACTIVE',
    ).select_related('marked_by').first()

    data = {
        'resource_id': resource.id,
        'name':        resource.display_name,
        'cargo':       resource.job_title.name if resource.job_title else '',
        'initials':    ''.join([n[0].upper() for n in resource.display_name.split()[:2]]),
        'open_session': None,
        'nos_event':    None,
    }

    if open_session:
        data['open_session'] = {
            'id':          open_session.id,
            'task_name':   open_session.task_name_snapshot,
            'stage_name':  open_session.stage_name_snapshot,
            'started_at':  open_session.started_at.strftime('%H:%M'),
        }

    if nos_event:
        data['nos_event'] = {
            'id':             nos_event.id,
            'reason_code':    nos_event.reason_code,
            'reason_display': nos_event.get_reason_code_display(),
            'detail':         nos_event.detail or '',
            'marked_by':      nos_event.marked_by.get_full_name(),
            'created_at':     timezone.localtime(nos_event.created_at).strftime('%H:%M'),
        }

    return JsonResponse(data)


@require_active_site
@require_POST
def no_on_site_mark(request):
    """Marca a un trabajador como No en obra."""
    site  = get_active_site(request)
    today = timezone.localdate()
    now   = timezone.now()

    if not user_has_permission(request.user, 'no_en_obra.manage', site):
        return JsonResponse({'error': 'Sin permiso para esta accion.'}, status=403)

    resource_id = request.POST.get('resource_id')
    reason_code = request.POST.get('reason_code', '').strip()
    detail      = request.POST.get('detail', '').strip()

    if not resource_id or not reason_code:
        return JsonResponse({'error': 'Datos incompletos.'}, status=400)

    resource = get_object_or_404(
        Resource,
        id=resource_id,
        company=site.company,
        status='ACTIVE',
    )

    existing = NoOnSiteEvent.objects.filter(
        resource=resource,
        site=site,
        event_date=today,
        status='ACTIVE',
    ).first()

    if existing:
        return JsonResponse({'error': 'Este trabajador ya tiene una marca activa para hoy.'}, status=400)

    valid_reasons = [r[0] for r in NoOnSiteEvent.ReasonCode.choices]
    if reason_code not in valid_reasons:
        return JsonResponse({'error': 'Motivo no valido.'}, status=400)

    session_closed     = False
    closed_session_info = None

    with transaction.atomic():
        open_session = WorkSession.objects.filter(
            resource=resource,
            site=site,
            status='OPEN',
        ).first()

        if open_session:
            duration = int((now - open_session.started_at).total_seconds() / 60)
            open_session.ended_at         = now
            open_session.status           = 'CLOSED'
            open_session.ended_by         = request.user
            open_session.closure_origin   = 'MANUAL'
            open_session.duration_minutes = duration
            open_session.save()
            session_closed      = True
            closed_session_info = {
                'task_name':  open_session.task_name_snapshot,
                'stage_name': open_session.stage_name_snapshot,
            }

        event = NoOnSiteEvent.objects.create(
            company=site.company,
            site=site,
            resource=resource,
            event_date=today,
            reason_code=reason_code,
            detail=detail or None,
            marked_by=request.user,
            status='ACTIVE',
        )

    return JsonResponse({
        'status':             'ok',
        'resource_id':        resource.id,
        'reason_display':     event.get_reason_code_display(),
        'session_closed':     session_closed,
        'closed_session_info': closed_session_info,
    })


@require_active_site
@require_POST
def no_on_site_void(request):
    """Anula una marca No en obra. Cambia status a VOIDED, no borra."""
    site  = get_active_site(request)
    today = timezone.localdate()

    if not user_has_permission(request.user, 'no_en_obra.manage', site):
        return JsonResponse({'error': 'Sin permiso para esta accion.'}, status=403)

    event_id      = request.POST.get('event_id')
    voided_reason = request.POST.get('voided_reason', '').strip()

    if not event_id:
        return JsonResponse({'error': 'Evento no especificado.'}, status=400)

    event = get_object_or_404(
        NoOnSiteEvent,
        id=event_id,
        site=site,
        event_date=today,
        status='ACTIVE',
    )

    event.status        = 'VOIDED'
    event.voided_by     = request.user
    event.voided_reason = voided_reason or 'Anulado por supervisor'
    event.save()

    return JsonResponse({
        'status':      'ok',
        'resource_id': event.resource_id,
    })
