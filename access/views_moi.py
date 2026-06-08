# -*- coding: utf-8 -*-
"""
CRUD de Mano de Obra Indirecta (MOI).
Usuarios del sistema (supervisores, administrativos, jefes, etc.)
en una obra específica.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db import transaction
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.utils.crypto import get_random_string

from companies.models import SiteMembership, CompanyMembership
from access.models import Role
from core.permissions import user_has_permission, get_user_context_permissions

User = get_user_model()


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
# LISTADO
# ─────────────────────────────────────────────────────────────────────────────

@require_active_site
def moi_list(request):
    """Listado de usuarios MOI de la obra activa."""
    site = get_active_site(request)

    if not user_has_permission(request.user, 'moi.view', site):
        return redirect('access_denied')

    memberships = SiteMembership.objects.filter(
        site=site,
    ).select_related(
        'user', 'role',
    ).order_by('user__first_name', 'user__last_name')

    perms_ctx = get_user_context_permissions(request.user, site)

    return render(request, 'access/moi_list.html', {
        'memberships': memberships,
        'site':        site,
        'page_title':  'Mano de obra indirecta',
        'perms_ctx':   perms_ctx,
        'total':       memberships.count(),
        'active_count': memberships.filter(is_active=True).count(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# CREAR
# ─────────────────────────────────────────────────────────────────────────────

@require_active_site
def moi_create(request):
    """Crear un nuevo usuario MOI y asignarlo a la obra."""
    site = get_active_site(request)

    if not user_has_permission(request.user, 'moi.edit', site):
        return redirect('access_denied')

    # Roles disponibles para asignar (excluir roles de prestador)
    roles = Role.objects.filter(
        is_active=True,
        scope_type='GLOBAL_BASE',
    ).exclude(
        code__in=['novus_super', 'novus_consultor']
    ).order_by('name')

    if request.method == 'POST':
        return _handle_moi_create(request, site, roles)

    return render(request, 'access/moi_form.html', {
        'mode':       'create',
        'site':       site,
        'roles':      roles,
        'page_title': 'Agregar usuario',
        'perms_ctx':  get_user_context_permissions(request.user, site),
    })


def _handle_moi_create(request, site, roles):
    first_name = request.POST.get('first_name', '').strip()
    last_name  = request.POST.get('last_name', '').strip()
    email      = request.POST.get('email', '').strip().lower()
    rut        = request.POST.get('rut', '').strip()
    role_id    = request.POST.get('role_id', '')
    notes      = request.POST.get('notes', '').strip()

    errors = {}

    if not first_name:
        errors['first_name'] = 'El nombre es obligatorio.'
    if not last_name:
        errors['last_name'] = 'El apellido es obligatorio.'
    if not email:
        errors['email'] = 'El correo es obligatorio.'
    if not role_id:
        errors['role_id'] = 'El rol es obligatorio.'

    if rut:
        rut = _normalize_rut(rut)

    # Verificar si el email ya existe
    existing_user = None
    if email and not errors.get('email'):
        existing_user = User.objects.filter(email=email).first()
        if existing_user:
            # Ya existe — verificar si ya tiene membresía en esta obra
            already = SiteMembership.objects.filter(
                user=existing_user,
                site=site,
            ).first()
            if already and already.is_active:
                errors['email'] = f'{email} ya tiene acceso activo a esta obra.'

    if errors:
        return render(request, 'access/moi_form.html', {
            'mode':      'create',
            'site':      site,
            'roles':     roles,
            'errors':    errors,
            'post_data': request.POST,
            'page_title': 'Agregar usuario',
            'perms_ctx': get_user_context_permissions(request.user, site),
        })

    role = get_object_or_404(Role, id=role_id, is_active=True)

    with transaction.atomic():
        if existing_user:
            user = existing_user
            # Actualizar datos si vinieron vacíos
            updated = False
            if not user.first_name and first_name:
                user.first_name = first_name; updated = True
            if not user.last_name and last_name:
                user.last_name = last_name; updated = True
            if not user.rut and rut:
                user.rut = rut; updated = True
            if updated:
                user.save()
        else:
            # Crear usuario nuevo con contraseña temporal
            user = User(
                email=email,
                first_name=first_name,
                last_name=last_name,
                rut=rut or None,
                actor_type='CLIENT',
                is_active=True,
            )
            user.set_unusable_password()
            user.save()

        # Asegurar membresía de empresa
        CompanyMembership.objects.get_or_create(
            user=user,
            company=site.company,
            defaults={
                'membership_type': 'CLIENT_SITE',
                'is_active': True,
            }
        )

        # Crear o reactivar membresía de obra
        membership, created = SiteMembership.objects.get_or_create(
            user=user,
            site=site,
            defaults={
                'role':        role,
                'is_active':   True,
                'can_operate': True,
                'notes':       notes or None,
                'granted_by':  request.user,
            }
        )
        if not created:
            membership.role      = role
            membership.is_active = True
            membership.notes     = notes or None
            membership.granted_by = request.user
            membership.save()

        # Crear preferencia de usuario si no existe
        from access.models import UserPreference
        UserPreference.objects.get_or_create(
            user=user,
            defaults={
                'last_site':    site,
                'last_company': site.company,
            }
        )

    messages.success(request, f'{user.get_full_name()} agregado a {site.name}.')
    return redirect('access:moi_list')


# ─────────────────────────────────────────────────────────────────────────────
# EDITAR
# ─────────────────────────────────────────────────────────────────────────────

@require_active_site
def moi_edit(request, membership_id):
    """Editar datos y rol de un usuario MOI."""
    site = get_active_site(request)

    if not user_has_permission(request.user, 'moi.edit', site):
        return redirect('access_denied')

    membership = get_object_or_404(SiteMembership, id=membership_id, site=site)
    user       = membership.user

    roles = Role.objects.filter(
        is_active=True,
        scope_type='GLOBAL_BASE',
    ).exclude(
        code__in=['novus_super', 'novus_consultor']
    ).order_by('name')

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name  = request.POST.get('last_name', '').strip()
        rut        = request.POST.get('rut', '').strip()
        role_id    = request.POST.get('role_id', '')
        notes      = request.POST.get('notes', '').strip()

        errors = {}
        if not first_name: errors['first_name'] = 'El nombre es obligatorio.'
        if not last_name:  errors['last_name']  = 'El apellido es obligatorio.'
        if not role_id:    errors['role_id']    = 'El rol es obligatorio.'

        if rut:
            rut = _normalize_rut(rut)

        if not errors:
            role = get_object_or_404(Role, id=role_id, is_active=True)

            user.first_name = first_name
            user.last_name  = last_name
            user.rut        = rut or None
            user.save()

            membership.role  = role
            membership.notes = notes or None
            membership.save()

            messages.success(request, f'{user.get_full_name()} actualizado.')
            return redirect('access:moi_list')

        return render(request, 'access/moi_form.html', {
            'mode':        'edit',
            'membership':  membership,
            'site':        site,
            'roles':       roles,
            'errors':      errors,
            'post_data':   request.POST,
            'page_title':  f'Editar — {user.get_full_name()}',
            'perms_ctx':   get_user_context_permissions(request.user, site),
        })

    return render(request, 'access/moi_form.html', {
        'mode':        'edit',
        'membership':  membership,
        'site':        site,
        'roles':       roles,
        'page_title':  f'Editar — {user.get_full_name()}',
        'perms_ctx':   get_user_context_permissions(request.user, site),
    })


# ─────────────────────────────────────────────────────────────────────────────
# DAR DE BAJA
# ─────────────────────────────────────────────────────────────────────────────

@require_active_site
@require_POST
def moi_deactivate(request, membership_id):
    """Da de baja a un usuario MOI — desactiva su membresía en esta obra."""
    site = get_active_site(request)

    if not user_has_permission(request.user, 'moi.edit', site):
        return JsonResponse({'error': 'Sin permiso.'}, status=403)

    membership = get_object_or_404(SiteMembership, id=membership_id, site=site)

    # No permitir darse de baja a uno mismo
    if membership.user == request.user:
        return JsonResponse({'error': 'No puedes darte de baja a ti mismo.'}, status=400)

    membership.is_active  = False
    membership.ended_at   = timezone.now().date()
    membership.save()

    return JsonResponse({
        'status':  'ok',
        'message': f'{membership.user.get_full_name()} dado de baja de {site.name}.',
    })


# ─────────────────────────────────────────────────────────────────────────────
# QR DE ACCESO
# ─────────────────────────────────────────────────────────────────────────────

@require_active_site
def moi_qr(request, membership_id):
    """Retorna datos para generar el QR de acceso del usuario."""
    site = get_active_site(request)

    if not user_has_permission(request.user, 'moi.view', site):
        return JsonResponse({'error': 'Sin permiso.'}, status=403)

    membership = get_object_or_404(SiteMembership, id=membership_id, site=site)
    user       = membership.user

    # QR simple — solo apunta a la URL del sistema
    qr_url = request.build_absolute_uri('/')

    return JsonResponse({
        'name':  user.get_full_name(),
        'email': user.email,
        'role':  membership.role.name,
        'qr_url': qr_url,
    })

@require_active_site
@require_POST
def moi_reactivate(request, membership_id):
    """Reactiva un usuario MOI — reactiva su membresía en esta obra."""
    site = get_active_site(request)

    if not user_has_permission(request.user, 'moi.edit', site):
        return JsonResponse({'error': 'Sin permiso.'}, status=403)

    membership = get_object_or_404(SiteMembership, id=membership_id, site=site)

    membership.is_active = True
    membership.ended_at  = None
    membership.save()

    return JsonResponse({
        'status':  'ok',
        'message': f'{membership.user.get_full_name()} reactivado en {site.name}.',
    })