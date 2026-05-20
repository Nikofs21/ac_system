# -*- coding: utf-8 -*-
"""
Sistema central de permisos y feature flags.

Uso basico:
    from core.permissions import require_permission, site_feature_enabled

    @require_permission('sessions.start_people')
    def mi_vista(request): ...

    if site_feature_enabled(site, 'no_on_site'):
        ...

Uso manual:
    from core.permissions import user_has_permission
    if user_has_permission(request.user, 'resources.crud_people', site):
        ...
"""

from functools import wraps
from django.shortcuts import redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required


# ─────────────────────────────────────────────────────────────────────────────
# CATALOGO DE PERMISOS
# Fuente de verdad. Cada codigo mapea a su descripcion legible.
# ─────────────────────────────────────────────────────────────────────────────

PERMISSION_CODES = {
    'sessions.start_people':       'Iniciar/terminar sesiones de personas',
    'sessions.start_machines':     'Iniciar/terminar sesiones de maquinarias',
    'sessions_review.view':        'Ver revision de partidas',
    'sessions_review.edit_today':  'Editar sesiones del dia actual',
    'partidas.finalize':           'Finalizar partidas definitivamente',
    'resources.view':              'Ver listado de recursos',
    'resources.view_qr':           'Ver/generar/descargar QR',
    'resources.crud_people':       'Crear/editar/baja/reactivar personas',
    'resources.crud_machines':     'Crear/editar/baja/reactivar maquinarias',
    'weekly_progress.view':        'Ver avance semanal',
    'weekly_progress.edit':        'Editar avance semanal',
    'no_en_obra.manage':           'Gestionar No en obra',
    'moi.view':                    'Ver Mano de Obra Indirecta',
    'moi.edit':                    'Crear/editar/baja/reactivar usuarios MOI',
    'bulk_close.own_sessions':     'Cierre masivo de sesiones propias',
    'organigram.view':             'Ver organigrama',
    'organigram.edit':             'Editar organigrama',
    'system.manage_companies':     'Crear/editar empresas y obras',
    'system.manage_users':         'Crear/asignar usuarios y roles',
}


# ─────────────────────────────────────────────────────────────────────────────
# MATRIX DE PERMISOS POR ROL
# Fuente de verdad para el seed de roles base.
# ─────────────────────────────────────────────────────────────────────────────

ROLE_PERMISSIONS = {
    'novus_super': list(PERMISSION_CODES.keys()),  # Todo

    'novus_consultor': list(PERMISSION_CODES.keys()),  # Todo (scope limitado por membresía)

    'gerencia': [
        'weekly_progress.view',
        'organigram.view',
    ],

    'admin_obra': [
        'sessions.start_people',
        'sessions.start_machines',
        'resources.view',
        'resources.view_qr',
        'resources.crud_people',
        'resources.crud_machines',
        'sessions_review.view',
        'weekly_progress.view',
        'no_en_obra.manage',
        'moi.view',
        'moi.edit',
        'bulk_close.own_sessions',
        'organigram.view',
        'organigram.edit',
    ],

    'administrativo': [
        'resources.view',
        'resources.view_qr',
        'resources.crud_people',
        'resources.crud_machines',
        'moi.view',
        'moi.edit',
        'organigram.view',
    ],

    'supervisor': [
        'sessions.start_people',
        'sessions.start_machines',
        'resources.view',
        'resources.view_qr',
        'no_en_obra.manage',
        'bulk_close.own_sessions',
    ],

    'bodeguero': [
        'sessions.start_machines',
        'resources.view',
        'resources.view_qr',
        'resources.crud_machines',
        'bulk_close.own_sessions',
    ],

    'planificador': [
        'resources.view',
        'resources.view_qr',
        'weekly_progress.view',
        'weekly_progress.edit',
    ],

    'jefe_terreno': [
        'sessions.start_people',
        'sessions.start_machines',
        'resources.view',
        'resources.view_qr',
        'sessions_review.view',
        'sessions_review.edit_today',
        'no_en_obra.manage',
        'bulk_close.own_sessions',
    ],

    'aac': [
        'sessions.start_people',
        'sessions.start_machines',
        'resources.view',
        'resources.view_qr',
        'resources.crud_people',
        'resources.crud_machines',
        'sessions_review.view',
        'sessions_review.edit_today',
        'weekly_progress.view',
        'weekly_progress.edit',
        'no_en_obra.manage',
        'moi.view',
        'bulk_close.own_sessions',
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE FLAGS — mapeo de codigo a campo en SiteConfig / CompanyConfig
# ─────────────────────────────────────────────────────────────────────────────

SITE_FEATURE_FLAGS = {
    'no_on_site':        'enable_no_on_site_tracking',
    'subcontracts':      'use_subcontracts',
    'planning':          'use_planning',
    'orgchart':          'use_orgchart',
    'assistance':        'use_assistance',
    'internal_dashboard':'use_internal_dashboard',
    'machinery':         'use_machinery',
    'people':            'use_people',
}

COMPANY_FEATURE_FLAGS = {
    'subcontracts':      'allow_subcontracts',
    'planning':          'allow_planning',
    'orgchart':          'allow_orgchart',
    'assistance':        'allow_assistance',
    'payroll':           'allow_payroll',
    'google_export':     'allow_google_sheet_export',
    'internal_dashboard':'allow_internal_dashboard',
    'machinery':         'allow_machinery',
    'people':            'allow_people',
}


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES PRINCIPALES
# ─────────────────────────────────────────────────────────────────────────────

def is_novus_super(user):
    """
    Retorna True si el usuario es Superadmin Novus.
    Tiene acceso absoluto sin restriccion de empresa/obra.
    """
    if not user or not user.is_authenticated:
        return False
    # Verificar por actor_type PROVIDER y rol novus_super
    if user.actor_type != 'PROVIDER':
        return False
    return user.site_memberships.filter(
        role__code='novus_super',
        is_active=True,
    ).exists() or user.is_superuser


def get_user_role_for_site(user, site):
    """
    Retorna el rol activo del usuario en una obra especifica.
    Retorna None si no tiene membresia activa.
    """
    if not user or not user.is_authenticated or not site:
        return None
    try:
        membership = user.site_memberships.select_related('role').get(
            site=site,
            is_active=True,
        )
        return membership.role
    except Exception:
        return None


def get_user_permissions_for_site(user, site):
    """
    Retorna el set de codigos de permisos del usuario en una obra.
    novus_super: todos los permisos.
    Resto: permisos del rol asignado en esa obra.
    """
    if not user or not user.is_authenticated:
        return set()

    if is_novus_super(user):
        return set(PERMISSION_CODES.keys())

    role = get_user_role_for_site(user, site)
    if not role:
        return set()

    # Leer permisos desde la base de datos (RolePermission)
    from access.models import RolePermission
    granted = RolePermission.objects.filter(
        role=role,
        granted=True,
        permission__is_active=True,
    ).values_list('permission__code', flat=True)

    return set(granted)


def user_has_permission(user, permission_code, site):
    """
    Funcion central de verificacion de permisos.

    Uso:
        if user_has_permission(request.user, 'resources.crud_people', site):
            ...
    """
    if not user or not user.is_authenticated:
        return False

    # novus_super pasa siempre
    if is_novus_super(user):
        return True

    perms = get_user_permissions_for_site(user, site)
    return permission_code in perms


def site_feature_enabled(site, feature_code):
    """
    Verifica si una funcionalidad esta habilitada para una obra.
    Primero verifica CompanyConfig (marco maximo), luego SiteConfig.

    Uso:
        if site_feature_enabled(site, 'no_on_site'):
            ...
    """
    if not site:
        return False

    # Verificar en CompanyConfig si el flag existe ahi
    company_flag = COMPANY_FEATURE_FLAGS.get(feature_code)
    if company_flag:
        try:
            company_config = site.company.config
            if not getattr(company_config, company_flag, True):
                return False
        except Exception:
            pass

    # Verificar en SiteConfig
    site_flag = SITE_FEATURE_FLAGS.get(feature_code)
    if site_flag:
        try:
            site_config = site.config
            return getattr(site_config, site_flag, False)
        except Exception:
            return False

    # Si no hay flag definido para ese codigo, se asume habilitado
    return True


def get_user_context_permissions(user, site):
    """
    Retorna un dict con todos los permisos del usuario para usar en templates.
    Se pasa al contexto como 'perms_ctx' para que el frontend muestre/oculte elementos.

    Uso en vista:
        context['perms_ctx'] = get_user_context_permissions(request.user, site)

    Uso en template:
        {% if perms_ctx.can_crud_people %}
    """
    perms = get_user_permissions_for_site(user, site)

    return {
        'can_start_people':       'sessions.start_people'      in perms,
        'can_start_machines':     'sessions.start_machines'    in perms,
        'can_review_sessions':    'sessions_review.view'       in perms,
        'can_edit_today':         'sessions_review.edit_today' in perms,
        'can_finalize':           'partidas.finalize'          in perms,
        'can_view_resources':     'resources.view'             in perms,
        'can_view_qr':            'resources.view_qr'          in perms,
        'can_crud_people':        'resources.crud_people'      in perms,
        'can_crud_machines':      'resources.crud_machines'    in perms,
        'can_view_progress':      'weekly_progress.view'       in perms,
        'can_edit_progress':      'weekly_progress.edit'       in perms,
        'can_manage_nos':         'no_en_obra.manage'          in perms,
        'can_view_moi':           'moi.view'                   in perms,
        'can_edit_moi':           'moi.edit'                   in perms,
        'can_bulk_close':         'bulk_close.own_sessions'    in perms,
        'can_view_orgchart':      'organigram.view'            in perms,
        'can_edit_orgchart':      'organigram.edit'            in perms,
        'can_manage_companies':   'system.manage_companies'    in perms,
        'can_manage_users':       'system.manage_users'        in perms,
        'is_novus_super':         is_novus_super(user),
        'role_code':              get_user_role_for_site(user, site).code if get_user_role_for_site(user, site) else '',
    }


# ─────────────────────────────────────────────────────────────────────────────
# DECORADORES
# ─────────────────────────────────────────────────────────────────────────────

def require_permission(permission_code, json_response=False):
    """
    Decorador que verifica un permiso antes de ejecutar la vista.
    Obtiene el site activo desde request.user.preference.last_site.

    Si json_response=True, retorna JSON en lugar de redirigir (para endpoints AJAX).

    Uso:
        @require_permission('resources.crud_people')
        def mi_vista(request): ...

        @require_permission('sessions.start_people', json_response=True)
        def mi_endpoint(request): ...
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            # Obtener obra activa
            try:
                site = request.user.preference.last_site
            except Exception:
                site = None

            if not site:
                if json_response:
                    return JsonResponse({'error': 'Sin obra activa.'}, status=403)
                return redirect('select_site')

            if not user_has_permission(request.user, permission_code, site):
                if json_response:
                    return JsonResponse({'error': 'Sin permiso para esta accion.'}, status=403)
                return redirect('access_denied')

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def require_feature(feature_code):
    """
    Decorador que verifica que una funcionalidad este habilitada para la obra activa.

    Uso:
        @require_feature('no_on_site')
        def no_on_site_view(request): ...
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            try:
                site = request.user.preference.last_site
            except Exception:
                site = None

            if not site_feature_enabled(site, feature_code):
                return redirect('feature_disabled')

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
