# -*- coding: utf-8 -*-
"""
CRUD de recursos operativos (personas y maquinarias).
Agregar estas funciones a resources/views.py o importar desde aquí.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db import transaction
from django.db.models import Q

from .models import Resource, ResourceSiteAssignment, JobTitle, ResourceCategory
from core.permissions import user_has_permission, get_user_context_permissions


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


def _normalize_rut(rut_str):
    """Normaliza RUT al formato 12345678-9 (sin puntos, con guión)."""
    if not rut_str:
        return ''
    clean = rut_str.replace('.', '').replace(' ', '').upper().strip()
    if '-' in clean:
        parts = clean.split('-')
        return f'{parts[0]}-{parts[1]}'
    if len(clean) >= 2:
        return f'{clean[:-1]}-{clean[-1]}'
    return clean


# ─────────────────────────────────────────────────────────────────────────────
# CREAR RECURSO
# ─────────────────────────────────────────────────────────────────────────────

@require_active_site
def resource_create(request):
    """
    Formulario de creación de recurso (persona o maquinaria).
    Dinámico según tipo seleccionado.
    Permite crear un cargo nuevo inline sin salir del formulario.
    """
    site = get_active_site(request)

    can_people   = user_has_permission(request.user, 'resources.crud_people', site)
    can_machines = user_has_permission(request.user, 'resources.crud_machines', site)

    if not can_people and not can_machines:
        return redirect('access_denied')

    # Categorías disponibles según permisos
    categories = []
    if can_people:
        cat = ResourceCategory.objects.filter(code='PERSON', is_active=True).first()
        if cat:
            categories.append(cat)
    if can_machines:
        for cat in ResourceCategory.objects.filter(
            resource_type='MACHINERY', is_active=True
        ):
            categories.append(cat)

    # Cargos disponibles para la obra (empresa + propios de la obra)
    job_titles = JobTitle.for_site(site).filter(
        Q(resource_type='PERSON') | Q(resource_type='BOTH')
    ) if can_people else JobTitle.objects.none()

    machine_titles = JobTitle.for_site(site).filter(
        Q(resource_type='MACHINERY') | Q(resource_type='BOTH')
    ) if can_machines else JobTitle.objects.none()

    if request.method == 'POST':
        return _handle_resource_create(request, site, can_people, can_machines)

    return render(request, 'resources/resource_form.html', {
        'mode':           'create',
        'site':           site,
        'categories':     categories,
        'job_titles':     job_titles,
        'machine_titles': machine_titles,
        'can_people':     can_people,
        'can_machines':   can_machines,
        'page_title':     'Agregar trabajador',
        'perms_ctx':      get_user_context_permissions(request.user, site),
    })


def _handle_resource_create(request, site, can_people, can_machines):
    """Procesa el POST de creación."""
    resource_type = request.POST.get('resource_type', '')
    display_name  = request.POST.get('display_name', '').strip()
    job_title_id  = request.POST.get('job_title_id', '')
    person_rut    = request.POST.get('person_rut', '').strip()
    license_plate = request.POST.get('license_plate', '').strip().upper()

    errors = {}

    # Validar permisos por tipo
    if resource_type == 'PERSON' and not can_people:
        return redirect('access_denied')
    if resource_type == 'MACHINERY' and not can_machines:
        return redirect('access_denied')

    if not display_name:
        errors['display_name'] = 'El nombre es obligatorio.'

    if resource_type == 'PERSON' and person_rut:
        person_rut = _normalize_rut(person_rut)
        # Verificar duplicado de RUT en la empresa
        existing = Resource.objects.filter(
            company=site.company,
            person_rut=person_rut,
        ).exclude(status='ARCHIVED').first()
        if existing:
            errors['person_rut'] = f'El RUT {person_rut} ya existe en el sistema.'

    if resource_type == 'MACHINERY' and license_plate:
        existing = Resource.objects.filter(
            company=site.company,
            license_plate=license_plate,
        ).exclude(status='ARCHIVED').first()
        if existing:
            errors['license_plate'] = f'La patente {license_plate} ya existe en el sistema.'

    if errors:
        # Re-renderizar con errores
        categories = []
        if can_people:
            cat = ResourceCategory.objects.filter(code='PERSON', is_active=True).first()
            if cat:
                categories.append(cat)
        if can_machines:
            for cat in ResourceCategory.objects.filter(resource_type='MACHINERY', is_active=True):
                categories.append(cat)

        return render(request, 'resources/resource_form.html', {
            'mode':           'create',
            'site':           site,
            'categories':     categories,
            'job_titles':     JobTitle.for_site(site).filter(Q(resource_type='PERSON') | Q(resource_type='BOTH')),
            'machine_titles': JobTitle.for_site(site).filter(Q(resource_type='MACHINERY') | Q(resource_type='BOTH')),
            'can_people':     can_people,
            'can_machines':   can_machines,
            'errors':         errors,
            'post_data':      request.POST,
            'page_title':     'Agregar trabajador',
            'perms_ctx':      get_user_context_permissions(request.user, site),
        })

    # Obtener categoría
    if resource_type == 'PERSON':
        category = ResourceCategory.objects.filter(code='PERSON').first()
    else:
        category = ResourceCategory.objects.filter(
            resource_type='MACHINERY', is_active=True
        ).first()

    job_title = None
    if job_title_id:
        try:
            job_title = JobTitle.objects.get(id=job_title_id, company=site.company)
        except JobTitle.DoesNotExist:
            pass

    with transaction.atomic():
        resource = Resource.objects.create(
            company=site.company,
            resource_category=category,
            display_name=display_name,
            normalized_name=display_name.lower().strip(),
            person_rut=person_rut if resource_type == 'PERSON' else None,
            license_plate=license_plate if resource_type == 'MACHINERY' else None,
            job_title=job_title,
            status='ACTIVE',
            is_trackable=True,
            created_by=request.user,
        )

        # Asignar a la obra activa
        ResourceSiteAssignment.objects.create(
            resource=resource,
            site=site,
            assignment_type='PRIMARY',
            status='ACTIVE',
            started_at=timezone.now(),
            assigned_by=request.user,
        )

    from django.contrib import messages
    messages.success(request, f'{display_name} agregado correctamente.')
    return redirect('resources:worker_list')


# ─────────────────────────────────────────────────────────────────────────────
# EDITAR RECURSO
# ─────────────────────────────────────────────────────────────────────────────

@require_active_site
def resource_edit(request, resource_id):
    """Editar datos de un recurso existente."""
    site = get_active_site(request)

    resource = get_object_or_404(Resource, id=resource_id, company=site.company)

    is_person    = resource.resource_category.resource_type == 'PERSON'
    is_machinery = resource.resource_category.resource_type == 'MACHINERY'

    if is_person and not user_has_permission(request.user, 'resources.crud_people', site):
        return redirect('access_denied')
    if is_machinery and not user_has_permission(request.user, 'resources.crud_machines', site):
        return redirect('access_denied')

    can_people   = user_has_permission(request.user, 'resources.crud_people', site)
    can_machines = user_has_permission(request.user, 'resources.crud_machines', site)

    job_titles = JobTitle.for_site(site).filter(
        Q(resource_type=resource.resource_category.resource_type) | Q(resource_type='BOTH')
    )

    if request.method == 'POST':
        display_name  = request.POST.get('display_name', '').strip()
        job_title_id  = request.POST.get('job_title_id', '')
        person_rut    = request.POST.get('person_rut', '').strip()
        license_plate = request.POST.get('license_plate', '').strip().upper()

        errors = {}

        if not display_name:
            errors['display_name'] = 'El nombre es obligatorio.'

        if is_person and person_rut:
            person_rut = _normalize_rut(person_rut)
            existing = Resource.objects.filter(
                company=site.company,
                person_rut=person_rut,
            ).exclude(id=resource.id).exclude(status='ARCHIVED').first()
            if existing:
                errors['person_rut'] = f'El RUT {person_rut} ya existe en otro trabajador.'

        if is_machinery and license_plate:
            existing = Resource.objects.filter(
                company=site.company,
                license_plate=license_plate,
            ).exclude(id=resource.id).exclude(status='ARCHIVED').first()
            if existing:
                errors['license_plate'] = f'La patente {license_plate} ya existe en otra maquinaria.'

        if not errors:
            job_title = None
            if job_title_id:
                try:
                    job_title = JobTitle.objects.get(id=job_title_id, company=site.company)
                except JobTitle.DoesNotExist:
                    pass

            resource.display_name    = display_name
            resource.normalized_name = display_name.lower().strip()
            resource.job_title       = job_title
            resource.updated_by      = request.user
            if is_person:
                resource.person_rut = person_rut or None
            if is_machinery:
                resource.license_plate = license_plate or None
            resource.save()

            from django.contrib import messages
            messages.success(request, f'{display_name} actualizado correctamente.')
            return redirect('resources:worker_list')

        return render(request, 'resources/resource_form.html', {
            'mode':        'edit',
            'resource':    resource,
            'site':        site,
            'job_titles':  job_titles,
            'can_people':  can_people,
            'can_machines': can_machines,
            'errors':      errors,
            'post_data':   request.POST,
            'page_title':  f'Editar — {resource.display_name}',
            'perms_ctx':   get_user_context_permissions(request.user, site),
        })

    return render(request, 'resources/resource_form.html', {
        'mode':        'edit',
        'resource':    resource,
        'site':        site,
        'job_titles':  job_titles,
        'can_people':  can_people,
        'can_machines': can_machines,
        'page_title':  f'Editar — {resource.display_name}',
        'perms_ctx':   get_user_context_permissions(request.user, site),
    })


# ─────────────────────────────────────────────────────────────────────────────
# DAR DE BAJA Y REACTIVAR
# ─────────────────────────────────────────────────────────────────────────────

@require_active_site
@require_POST
def resource_deactivate(request, resource_id):
    """Da de baja un recurso. Cambia status a INACTIVE, no borra."""
    site     = get_active_site(request)
    resource = get_object_or_404(Resource, id=resource_id, company=site.company)

    is_person    = resource.resource_category.resource_type == 'PERSON'
    is_machinery = resource.resource_category.resource_type == 'MACHINERY'

    if is_person and not user_has_permission(request.user, 'resources.crud_people', site):
        return JsonResponse({'error': 'Sin permiso.'}, status=403)
    if is_machinery and not user_has_permission(request.user, 'resources.crud_machines', site):
        return JsonResponse({'error': 'Sin permiso.'}, status=403)

    reason = request.POST.get('reason', '').strip()

    with transaction.atomic():
        # Cerrar asignacion activa a la obra
        ResourceSiteAssignment.objects.filter(
            resource=resource,
            site=site,
            status='ACTIVE',
        ).update(
            status='ENDED',
            ended_at=timezone.now(),
        )

        resource.status     = 'INACTIVE'
        resource.updated_by = request.user
        resource.save()

    return JsonResponse({
        'status': 'ok',
        'resource_id': resource.id,
        'message': f'{resource.display_name} dado de baja.',
    })


@require_active_site
@require_POST
def resource_reactivate(request, resource_id):
    """Reactiva un recurso inactivo y lo re-asigna a la obra activa."""
    site     = get_active_site(request)
    resource = get_object_or_404(Resource, id=resource_id, company=site.company)

    is_person    = resource.resource_category.resource_type == 'PERSON'
    is_machinery = resource.resource_category.resource_type == 'MACHINERY'

    if is_person and not user_has_permission(request.user, 'resources.crud_people', site):
        return JsonResponse({'error': 'Sin permiso.'}, status=403)
    if is_machinery and not user_has_permission(request.user, 'resources.crud_machines', site):
        return JsonResponse({'error': 'Sin permiso.'}, status=403)

    with transaction.atomic():
        resource.status     = 'ACTIVE'
        resource.updated_by = request.user
        resource.save()

        # Crear nueva asignación a la obra activa
        # (puede que antes estuviera en otra obra)
        already = ResourceSiteAssignment.objects.filter(
            resource=resource,
            site=site,
            status='ACTIVE',
        ).exists()

        if not already:
            ResourceSiteAssignment.objects.create(
                resource=resource,
                site=site,
                assignment_type='PRIMARY',
                status='ACTIVE',
                started_at=timezone.now(),
                assigned_by=request.user,
            )

    return JsonResponse({
        'status': 'ok',
        'resource_id': resource.id,
        'message': f'{resource.display_name} reactivado.',
    })


# ─────────────────────────────────────────────────────────────────────────────
# CREAR CARGO INLINE (AJAX)
# ─────────────────────────────────────────────────────────────────────────────

@require_active_site
@require_POST
def job_title_create_inline(request):
    """
    Crea un cargo nuevo desde el formulario de recurso sin recargar la página.
    El cargo queda asociado a la obra activa (scope de obra).
    """
    site = get_active_site(request)

    can_people   = user_has_permission(request.user, 'resources.crud_people', site)
    can_machines = user_has_permission(request.user, 'resources.crud_machines', site)

    if not can_people and not can_machines:
        return JsonResponse({'error': 'Sin permiso.'}, status=403)

    name          = request.POST.get('name', '').strip()
    resource_type = request.POST.get('resource_type', 'PERSON')

    if not name:
        return JsonResponse({'error': 'El nombre del cargo es obligatorio.'}, status=400)

    if len(name) > 120:
        return JsonResponse({'error': 'El nombre no puede superar 120 caracteres.'}, status=400)

    # Verificar que no exista ya en empresa o en esta obra
    exists = JobTitle.objects.filter(
        company=site.company,
        name__iexact=name,
    ).filter(
        Q(site__isnull=True) | Q(site=site)
    ).exists()

    if exists:
        return JsonResponse({'error': f'El cargo "{name}" ya existe.'}, status=400)

    job_title = JobTitle.objects.create(
        company=site.company,
        site=site,           # Scope de obra
        name=name,
        resource_type=resource_type,
        is_active=True,
    )

    return JsonResponse({
        'status': 'ok',
        'id':   job_title.id,
        'name': job_title.name,
    })
