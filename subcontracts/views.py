# -*- coding: utf-8 -*-
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.utils import timezone
from django.db import transaction
from django.contrib import messages

from .models import (
    Subcontract,
    SubcontractSession,
    SubcontractSessionDetail,
    SubcontractPersonnelSlot,
    SubcontractSessionHistory,
)
from companies.models import Site, SiteMembership
from work.models import StageTask, TaskCatalog
from core.permissions import user_has_permission, get_user_context_permissions


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_active_site(request):
    pref = getattr(request.user, 'preference', None)
    if pref and pref.last_site:
        return pref.last_site
    membership = SiteMembership.objects.filter(
        user=request.user, is_active=True
    ).select_related('site').first()
    return membership.site if membership else None


def require_active_site(view_func):
    def wrapper(request, *args, **kwargs):
        site = get_active_site(request)
        if not site:
            return redirect('no_site')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


# ─────────────────────────────────────────────────────────────────────────────
# LISTADO
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_active_site
def subcontract_list(request):
    site = get_active_site(request)

    if not user_has_permission(request.user, 'sessions.start_people', site) and \
       not request.user.actor_type == 'PROVIDER':
        return redirect('access_denied')

    subcontracts = Subcontract.objects.filter(
        site=site,
    ).select_related('reserved_stage').order_by('name')

    is_provider = request.user.actor_type == 'PROVIDER'
    perms_ctx   = get_user_context_permissions(request.user, site)

    return render(request, 'subcontracts/subcontract_list.html', {
        'subcontracts': subcontracts,
        'site':         site,
        'page_title':   'Subcontratos',
        'perms_ctx':    perms_ctx,
        'is_provider':  is_provider,
        'total':        subcontracts.count(),
        'active_count': subcontracts.filter(status='ACTIVE').count(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# CRUD (solo prestador)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_active_site
def subcontract_create(request):
    site = get_active_site(request)

    if request.user.actor_type != 'PROVIDER':
        return redirect('access_denied')

    reserved_stages = site.stages.filter(
        stage_type='SUBCONTRACT_RESERVED', is_active=True
    )

    errors   = {}
    post_data = None

    if request.method == 'POST':
        name             = request.POST.get('name', '').strip()
        code             = request.POST.get('code', '').strip().upper()
        rut              = request.POST.get('rut', '').strip()
        reserved_stage_id = request.POST.get('reserved_stage_id', '').strip()
        notes            = request.POST.get('notes', '').strip()
        post_data        = request.POST

        if not name:
            errors['name'] = 'El nombre es obligatorio.'
        if not code:
            errors['code'] = 'El codigo es obligatorio.'
        elif Subcontract.objects.filter(site=site, code=code).exists():
            errors['code'] = 'Ya existe un subcontrato con ese codigo en esta obra.'

        if not errors:
            sub = Subcontract.objects.create(
                company          = site.company,
                site             = site,
                name             = name,
                code             = code,
                rut              = rut or None,
                reserved_stage_id = reserved_stage_id or None,
                notes            = notes or None,
            )
            messages.success(request, f'Subcontrato "{sub.name}" creado correctamente.')
            return redirect('subcontracts:subcontract_list')

    return render(request, 'subcontracts/subcontract_form.html', {
        'mode':             'create',
        'page_title':       'Nuevo subcontrato',
        'site':             site,
        'reserved_stages':  reserved_stages,
        'errors':           errors,
        'post_data':        post_data,
    })


@login_required
@require_active_site
def subcontract_edit(request, subcontract_id):
    site = get_active_site(request)

    if request.user.actor_type != 'PROVIDER':
        return redirect('access_denied')

    subcontract = get_object_or_404(Subcontract, id=subcontract_id, site=site)
    reserved_stages = site.stages.filter(
        stage_type='SUBCONTRACT_RESERVED', is_active=True
    )

    errors    = {}
    post_data = None

    if request.method == 'POST':
        name              = request.POST.get('name', '').strip()
        code              = request.POST.get('code', '').strip().upper()
        rut               = request.POST.get('rut', '').strip()
        reserved_stage_id = request.POST.get('reserved_stage_id', '').strip()
        notes             = request.POST.get('notes', '').strip()
        post_data         = request.POST

        if not name:
            errors['name'] = 'El nombre es obligatorio.'
        if not code:
            errors['code'] = 'El codigo es obligatorio.'
        elif Subcontract.objects.filter(site=site, code=code).exclude(id=subcontract_id).exists():
            errors['code'] = 'Ya existe un subcontrato con ese codigo en esta obra.'

        if not errors:
            subcontract.name              = name
            subcontract.code              = code
            subcontract.rut               = rut or None
            subcontract.reserved_stage_id = reserved_stage_id or None
            subcontract.notes             = notes or None
            subcontract.save()
            messages.success(request, 'Cambios guardados.')
            return redirect('subcontracts:subcontract_list')

    return render(request, 'subcontracts/subcontract_form.html', {
        'mode':            'edit',
        'page_title':      f'Editar — {subcontract.name}',
        'site':            site,
        'subcontract':     subcontract,
        'reserved_stages': reserved_stages,
        'errors':          errors,
        'post_data':       post_data,
    })


@login_required
@require_POST
def subcontract_deactivate(request, subcontract_id):
    site = get_active_site(request)
    if request.user.actor_type != 'PROVIDER':
        return JsonResponse({'error': 'Sin permiso.'}, status=403)
    sub = get_object_or_404(Subcontract, id=subcontract_id, site=site)
    sub.status = 'INACTIVE'
    sub.save()
    return JsonResponse({'status': 'ok', 'message': f'"{sub.name}" inactivado.'})


@login_required
@require_POST
def subcontract_reactivate(request, subcontract_id):
    site = get_active_site(request)
    if request.user.actor_type != 'PROVIDER':
        return JsonResponse({'error': 'Sin permiso.'}, status=403)
    sub = get_object_or_404(Subcontract, id=subcontract_id, site=site)
    sub.status = 'ACTIVE'
    sub.save()
    return JsonResponse({'status': 'ok', 'message': f'"{sub.name}" reactivado.'})


@login_required
def subcontract_qr(request, subcontract_id):
    site = get_active_site(request)
    sub  = get_object_or_404(Subcontract, id=subcontract_id, site=site)
    qr_url = request.build_absolute_uri(f'/subcontratos/{sub.uid}/')
    return JsonResponse({
        'name':   sub.name,
        'code':   sub.code,
        'stage':  sub.reserved_stage.name if sub.reserved_stage else None,
        'qr_url': qr_url,
    })


# ─────────────────────────────────────────────────────────────────────────────
# FORMULARIO OPERATIVO (via QR)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def subcontract_form(request, subcontract_uid):
    """
    Formulario operativo del subcontrato — accedido via QR.
    POST se procesa primero y siempre redirige.
    GET muestra el estado actual.
    """
    subcontract = get_object_or_404(
        Subcontract,
        uid=subcontract_uid,
        status='ACTIVE',
    )
    site = subcontract.site

    # Verificar acceso a la obra
    has_access = SiteMembership.objects.filter(
        user=request.user,
        site=site,
        is_active=True,
    ).exists() or request.user.actor_type == 'PROVIDER'

    if not has_access:
        return render(request, 'subcontracts/subcontract_no_access.html', {
            'subcontract': subcontract,
            'site':        site,
        })

    # ── POST ──────────────────────────────────────────────────────────────
    if request.method == 'POST':
        action = request.POST.get('action', '')

        active_session = SubcontractSession.objects.filter(
            subcontract=subcontract,
            status='OPEN',
        ).first()

        if action == 'iniciar' and not active_session:
            return _handle_start(request, subcontract, site)
        elif action == 'guardar' and active_session:
            return _handle_update(request, subcontract, site, active_session)
        elif action == 'terminar' and active_session:
            return _handle_end(request, subcontract, site, active_session)
        else:
            messages.error(request, 'Accion no valida.')
            return redirect('subcontract_form_qr', subcontract_uid=subcontract.uid)

    # ── GET ───────────────────────────────────────────────────────────────
    active_session = SubcontractSession.objects.filter(
        subcontract=subcontract,
        status='OPEN',
    ).prefetch_related(
        'details__task',
        'details__personnel_slots',
    ).first()

    tasks = _get_tasks(subcontract, site)
    perms_ctx = get_user_context_permissions(request.user, site)

    if active_session:
        # Preparar datos de la sesion para el template
        session_details = []
        for detail in active_session.details.all():
            active_slot = detail.personnel_slots.filter(ended_at__isnull=True).first()
            session_details.append({
                'detail':    detail,
                'task':      detail.task,
                'quantity':  active_slot.quantity if active_slot else 0,
                'slot':      active_slot,
            })

        return render(request, 'subcontracts/subcontract_active.html', {
            'subcontract':    subcontract,
            'site':           site,
            'active_session': active_session,
            'session_details': session_details,
            'tasks':          tasks,
            'page_title':     subcontract.name,
            'perms_ctx':      perms_ctx,
        })

    return render(request, 'subcontracts/subcontract_new_session.html', {
        'subcontract': subcontract,
        'site':        site,
        'tasks':       tasks,
        'page_title':  subcontract.name,
        'perms_ctx':   perms_ctx,
    })


# ─────────────────────────────────────────────────────────────────────────────
# MANEJADORES DE ACCIONES
# ─────────────────────────────────────────────────────────────────────────────

def _get_tasks(subcontract, site):
    """Retorna las partidas disponibles para el subcontrato."""
    if not subcontract.reserved_stage:
        return []
    return list(
        StageTask.objects.filter(
            site=site,
            stage=subcontract.reserved_stage,
            is_active=True,
            task__status='ACTIVE',
        ).select_related('task').order_by('task__name')
    )


def _handle_start(request, subcontract, site):
    """Inicia una nueva sesion con sus partidas y slots iniciales."""
    task_ids   = request.POST.getlist('task_id')
    quantities = request.POST.getlist('quantity')

    # Validar que haya al menos una partida
    valid_pairs = []
    for task_id, qty in zip(task_ids, quantities):
        try:
            qty = int(qty)
            if qty < 1 or not task_id:
                continue
            task = TaskCatalog.objects.filter(
                id=task_id, company=site.company, status='ACTIVE'
            ).first()
            if task:
                valid_pairs.append((task, qty))
        except (ValueError, TypeError):
            continue

    if not valid_pairs:
        messages.error(request, 'Debes agregar al menos una partida con cantidad valida.')
        return redirect('subcontract_form_qr', subcontract_uid=subcontract.uid)

    now = timezone.now()

    with transaction.atomic():
        session = SubcontractSession.objects.create(
            company    = site.company,
            site       = site,
            subcontract = subcontract,
            started_at  = now,
            status      = 'OPEN',
            started_by  = request.user,
        )

        for task, qty in valid_pairs:
            detail = SubcontractSessionDetail.objects.create(
                session   = session,
                task      = task,
                unit_code = 'personas',
            )
            # Primer slot: desde el inicio de la sesion
            SubcontractPersonnelSlot.objects.create(
                detail     = detail,
                quantity   = qty,
                started_at = now,
                created_by = request.user,
            )

        # Registrar en historial
        SubcontractSessionHistory.objects.create(
            session     = session,
            changed_by  = request.user,
            change_type = 'START',
            after_json  = {
                'partidas': [
                    {'task_id': t.id, 'task_name': t.name, 'quantity': q}
                    for t, q in valid_pairs
                ]
            },
        )

    messages.success(request, 'Sesion iniciada correctamente.')
    return redirect('subcontract_form_qr', subcontract_uid=subcontract.uid)


def _handle_update(request, subcontract, site, session):
    """
    Guarda cambios en la sesion activa.
    Para cada partida existente, si la cantidad cambio:
      - cierra el slot activo con ended_at = ahora
      - crea un nuevo slot con la nueva cantidad
    Tambien permite agregar nuevas partidas y eliminar existentes (qty=0).
    """
    detail_ids     = request.POST.getlist('detail_id')
    quantities     = request.POST.getlist('quantity')
    new_task_ids   = request.POST.getlist('new_task_id')
    new_quantities = request.POST.getlist('new_quantity')

    now = timezone.now()

    with transaction.atomic():

        # ── Actualizar partidas existentes ────────────────────────────────
        for detail_id, qty_str in zip(detail_ids, quantities):
            try:
                qty = int(qty_str)
            except (ValueError, TypeError):
                continue

            try:
                detail = SubcontractSessionDetail.objects.get(
                    id=detail_id, session=session
                )
            except SubcontractSessionDetail.DoesNotExist:
                continue

            active_slot = detail.personnel_slots.filter(ended_at__isnull=True).first()
            current_qty = active_slot.quantity if active_slot else 0

            if qty == 0:
                # Registrar historial antes de borrar
                SubcontractSessionHistory.objects.create(
                    session     = session,
                    changed_by  = request.user,
                    change_type = 'TASK_REMOVED',
                    before_json = {
                        'detail_id': int(detail_id),
                        'task_name': detail.task.name,
                        'quantity':  current_qty,
                    },
                )
                # Borrar slots primero, luego el detalle
                detail.personnel_slots.all().delete()
                detail.delete()

            elif qty != current_qty:
                # Cantidad cambio: cerrar slot activo y abrir uno nuevo
                if active_slot:
                    active_slot.ended_at = now
                    active_slot.save()

                SubcontractPersonnelSlot.objects.create(
                    detail     = detail,
                    quantity   = qty,
                    started_at = now,
                    created_by = request.user,
                )

                SubcontractSessionHistory.objects.create(
                    session     = session,
                    changed_by  = request.user,
                    change_type = 'QUANTITY_CHANGE',
                    before_json = {
                        'detail_id': int(detail_id),
                        'task_name': detail.task.name,
                        'quantity':  current_qty,
                    },
                    after_json  = {
                        'detail_id': int(detail_id),
                        'task_name': detail.task.name,
                        'quantity':  qty,
                    },
                )
            # Si qty == current_qty, no se hace nada

        # ── Agregar nuevas partidas ────────────────────────────────────────
        for task_id, qty_str in zip(new_task_ids, new_quantities):
            try:
                qty = int(qty_str)
                if qty < 1 or not task_id:
                    continue
            except (ValueError, TypeError):
                continue

            task = TaskCatalog.objects.filter(
                id=task_id, company=site.company, status='ACTIVE'
            ).first()
            if not task:
                continue

            already_exists = SubcontractSessionDetail.objects.filter(
                session=session, task=task
            ).exists()
            if already_exists:
                continue

            detail = SubcontractSessionDetail.objects.create(
                session   = session,
                task      = task,
                unit_code = 'personas',
            )
            SubcontractPersonnelSlot.objects.create(
                detail     = detail,
                quantity   = qty,
                started_at = now,
                created_by = request.user,
            )

            SubcontractSessionHistory.objects.create(
                session     = session,
                changed_by  = request.user,
                change_type = 'TASK_ADDED',
                after_json  = {
                    'task_id':   task.id,
                    'task_name': task.name,
                    'quantity':  qty,
                },
            )

        # Verificar que queden partidas
        remaining = SubcontractSessionDetail.objects.filter(session=session).count()
        if remaining == 0:
            _close_session(session, request.user, now, force=True)
            messages.warning(request, 'Todas las partidas eliminadas. Sesion cerrada.')
        else:
            messages.success(request, 'Cambios guardados.')

    return redirect('subcontract_form_qr', subcontract_uid=subcontract.uid)


def _handle_end(request, subcontract, site, session):
    """Cierra la sesion activa y todos sus slots."""
    now = timezone.now()

    with transaction.atomic():
        _close_session(session, request.user, now)

    messages.success(request, 'Sesion cerrada correctamente.')
    return redirect('subcontract_form_qr', subcontract_uid=subcontract.uid)


def _close_session(session, user, now, force=False):
    """
    Cierra todos los slots activos y marca la sesion como cerrada.
    Llama esto siempre dentro de un transaction.atomic().
    """
    for detail in session.details.prefetch_related('personnel_slots').all():
        active_slot = detail.personnel_slots.filter(ended_at__isnull=True).first()
        if active_slot:
            active_slot.ended_at = now
            active_slot.save()

    session.status   = 'CLOSED'
    session.ended_at = now
    session.ended_by = user
    session.save()

    SubcontractSessionHistory.objects.create(
        session     = session,
        changed_by  = user,
        change_type = 'FORCE_CLOSE' if force else 'CLOSE',
        after_json  = {'ended_at': now.isoformat()},
    )
