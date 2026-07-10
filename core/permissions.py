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
# Cada entrada incluye nombre, modulo y nivel.
# seed_roles lee directamente de aqui — no hay mapas manuales separados.
# Para agregar un permiso nuevo: solo agregar una entrada aqui y en ROLE_PERMISSIONS.
# ─────────────────────────────────────────────────────────────────────────────

PERMISSION_CODES = {
    'sessions.start_people': {
        'name':   'Iniciar/terminar sesiones de personas',
        'module': 'OPERACION',
        'level':  'OPERATE',
    },
    'sessions.start_machines': {
        'name':   'Iniciar/terminar sesiones de maquinarias',
        'module': 'OPERACION',
        'level':  'OPERATE',
    },
    'sessions_review.view': {
        'name':   'Ver revision de partidas',
        'module': 'OPERACION',
        'level':  'VIEW',
    },
    'sessions_review.edit_today': {
        'name':   'Editar sesiones del dia actual',
        'module': 'OPERACION',
        'level':  'SENSITIVE',
    },
    'partidas.finalize': {
        'name':   'Finalizar partidas definitivamente',
        'module': 'OPERACION',
        'level':  'SENSITIVE',
    },
    'resources.view': {
        'name':   'Ver listado de recursos',
        'module': 'RECURSOS',
        'level':  'VIEW',
    },
    'resources.view_qr': {
        'name':   'Ver/generar/descargar QR',
        'module': 'RECURSOS',
        'level':  'VIEW',
    },
    'resources.crud_people': {
        'name':   'Crear/editar/baja/reactivar personas',
        'module': 'RECURSOS',
        'level':  'ADMIN',
    },
    'resources.crud_machines': {
        'name':   'Crear/editar/baja/reactivar maquinarias',
        'module': 'RECURSOS',
        'level':  'ADMIN',
    },
    'weekly_progress.view': {
        'name':   'Ver avance semanal',
        'module': 'PLANIFICACION',
        'level':  'VIEW',
    },
    'weekly_progress.edit': {
        'name':   'Editar avance semanal',
        'module': 'PLANIFICACION',
        'level':  'OPERATE',
    },
    'no_en_obra.manage': {
        'name':   'Gestionar No en obra',
        'module': 'OPERACION',
        'level':  'OPERATE',
    },
    'moi.view': {
        'name':   'Ver Mano de Obra Indirecta',
        'module': 'USUARIOS',
        'level':  'VIEW',
    },
    'moi.edit': {
        'name':   'Crear/editar/baja/reactivar usuarios MOI',
        'module': 'USUARIOS',
        'level':  'ADMIN',
    },
    'bulk_close.own_sessions': {
        'name':   'Cierre masivo de sesiones propias',
        'module': 'OPERACION',
        'level':  'SENSITIVE',
    },
    'organigram.view': {
        'name':   'Ver organigrama',
        'module': 'ORGANIGRAMA',
        'level':  'VIEW',
    },
    'organigram.edit': {
        'name':   'Editar organigrama',
        'module': 'ORGANIGRAMA',
        'level':  'ADMIN',
    },
    'system.manage_companies': {
        'name':   'Crear/editar empresas y obras',
        'module': 'CONFIGURACION_ESTRUCTURAL',
        'level':  'SENSITIVE',
    },
    'system.manage_users': {
        'name':   'Crear/asignar usuarios y roles',
        'module': 'CONFIGURACION_ESTRUCTURAL',
        'level':  'SENSITIVE',
    },
    'subcontracts.view_list': {
        'name':   'Ver listado de subcontratos',
        'module': 'SUBCONTRATOS',
        'level':  'VIEW',
    },
    'subcontracts.operate': {
        'name':   'Operar formulario de subcontrato',
        'module': 'SUBCONTRATOS',
        'level':  'OPERATE',
    },
    'dashboard.productivity': {
        'name':   'Ver informe diario de productividad',
        'module': 'DASHBOARDS',
        'level':  'VIEW',
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# MATRIX DE PERMISOS POR ROL
# Define los permisos estandar de cada rol.
# Puede sobrescribirse por obra via SiteMembershipPermissionOverride.
#
# NOTA: novus_super ya NO se resuelve via esta matriz — es un flag de User
# (user.is_novus_super) evaluado directamente en is_novus_super(). Se deja
# 'novus_super' en el dict de roles porque SiteMembership.role todavia
# referencia este codigo para las membresias operativas existentes, pero
# is_novus_super() nunca consulta ROLE_PERMISSIONS para resolver el acceso.
# ─────────────────────────────────────────────────────────────────────────────

ROLE_PERMISSIONS = {
    'novus_super':    list(PERMISSION_CODES.keys()),
    'novus_consultor': list(PERMISSION_CODES.keys()),

    'gerencia': [
        'weekly_progress.view',
        'organigram.view',
        'dashboard.productivity',
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
        'subcontracts.view_list',
        'subcontracts.operate',
        'dashboard.productivity',
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
        'subcontracts.view_list',
        'subcontracts.operate',
        'dashboard.productivity',
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
        'subcontracts.view_list',
        'subcontracts.operate',
        'dashboard.productivity',
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# JERARQUIA DE OTORGAMIENTO DE ROLES
#
# Roles que SOLO pueden ser otorgados/asignados por usuarios novus_super
# (ver is_novus_super()). Ningun otro rol -- ni siquiera admin_obra a otro
# admin_obra -- puede crear o editar una membresia hacia estos roles.
#
# Esto es independiente de los permisos operativos del rol (ROLE_PERMISSIONS);
# un admin_obra puede tener moi.edit y administrar MOI normalmente, pero el
# <select> de roles disponibles para asignar excluye estos codigos salvo que
# quien esta operando la pantalla sea novus_super.
#
# Usar get_assignable_roles_queryset() en vistas que muestren un selector de
# roles, en vez de filtrar manualmente — asi la regla queda en un solo lugar.
# ─────────────────────────────────────────────────────────────────────────────

ROLES_GRANTABLE_ONLY_BY_NOVUS = [
    'admin_obra',
    'gerencia',
    'aac',
]

# Roles de prestador — nunca asignables desde pantallas de MOI/usuarios cliente,
# independiente de quien este operando (ni siquiera novus_super los asigna ahi;
# esos se gestionan por fuera, a nivel de User.is_novus_super / Role directo).
PROVIDER_ONLY_ROLE_CODES = [
    'novus_super',
    'novus_consultor',
]


def get_assignable_roles_queryset(user):
    """
    Retorna el queryset de Roles que `user` puede asignar a otra persona
    desde pantallas de gestion de usuarios (ej: MOI).

    Reglas:
    - Los roles de prestador (PROVIDER_ONLY_ROLE_CODES) nunca se incluyen aqui.
    - Los roles en ROLES_GRANTABLE_ONLY_BY_NOVUS solo se incluyen si
      is_novus_super(user) es True.
    - El resto de roles activos GLOBAL_BASE se incluyen siempre.
    """
    from access.models import Role

    excluded_codes = list(PROVIDER_ONLY_ROLE_CODES)
    if not is_novus_super(user):
        excluded_codes += ROLES_GRANTABLE_ONLY_BY_NOVUS

    return Role.objects.filter(
        is_active=True,
        scope_type='GLOBAL_BASE',
    ).exclude(
        code__in=excluded_codes
    ).order_by('name')


def can_user_edit_membership(user, membership):
    """
    Determina si `user` puede editar/dar de baja una SiteMembership especifica
    (pantallas de MOI). Esto es distinto de "puede asignar este rol" — aqui se
    evalua sobre una membresia que YA existe.

    Regla: si el rol actual de la membresia esta en ROLES_GRANTABLE_ONLY_BY_NOVUS,
    solo un novus_super puede editarla o darla de baja. Cualquier otro usuario
    con moi.edit puede VER esa fila en el listado, pero no tocarla.

    Los roles de prestador (PROVIDER_ONLY_ROLE_CODES) nunca deberian aparecer
    en SiteMembership de MOI en la practica, pero por defensiva se tratan
    igual de protegidos si llegaran a existir.
    """
    if is_novus_super(user):
        return True

    protected_codes = set(ROLES_GRANTABLE_ONLY_BY_NOVUS) | set(PROVIDER_ONLY_ROLE_CODES)
    return membership.role.code not in protected_codes


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE FLAGS
# ─────────────────────────────────────────────────────────────────────────────

SITE_FEATURE_FLAGS = {
    'no_on_site':         'enable_no_on_site_tracking',
    'subcontracts':       'use_subcontracts',
    'planning':           'use_planning',
    'orgchart':           'use_orgchart',
    'assistance':         'use_assistance',
    'internal_dashboard': 'use_internal_dashboard',
    'machinery':          'use_machinery',
    'people':             'use_people',
}

COMPANY_FEATURE_FLAGS = {
    'subcontracts':       'allow_subcontracts',
    'planning':           'allow_planning',
    'orgchart':           'allow_orgchart',
    'assistance':         'allow_assistance',
    'payroll':            'allow_payroll',
    'google_export':      'allow_google_sheet_export',
    'internal_dashboard': 'allow_internal_dashboard',
    'machinery':          'allow_machinery',
    'people':             'allow_people',
}


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES PRINCIPALES
# ─────────────────────────────────────────────────────────────────────────────

def is_novus_super(user):
    """
    Acceso total al sistema: todas las empresas y obras, sin excepcion.

    Se resuelve con dos flags a nivel de User, NUNCA por membresia:
    - user.is_superuser    (flag nativo de Django)
    - user.is_novus_super  (flag propio del sistema, ver access.models.User)

    Esto es deliberado: novus_super no es un rol que pueda variar por obra.
    Si necesitas otorgarlo/quitarlo, hazlo sobre el User directamente
    (admin de Django o pantalla de gestion de usuarios), no sobre una
    membresia especifica.
    """
    if not user or not user.is_authenticated:
        return False
    return bool(user.is_superuser or user.is_novus_super)


def get_user_role_for_site(user, site):
    if not user or not user.is_authenticated or not site:
        return None
    try:
        membership = user.site_memberships.select_related('role').get(
            site=site, is_active=True,
        )
        return membership.role
    except Exception:
        return None


def get_user_permissions_for_site(user, site):
    """
    Retorna el set de codigos de permisos del usuario en una obra.

    Orden de resolucion:
    1. novus_super → todos los permisos (no requiere membresia)
    2. Permisos del rol base (via RolePermission)
    3. Overrides de la membresia (SiteMembershipPermissionOverride)
       - granted=True  → agrega aunque el rol no lo tenga
       - granted=False → quita aunque el rol lo tenga
    """
    if not user or not user.is_authenticated:
        return set()

    if is_novus_super(user):
        return set(PERMISSION_CODES.keys())

    role = get_user_role_for_site(user, site)
    if not role:
        return set()

    # Permisos base del rol
    from access.models import RolePermission
    granted = RolePermission.objects.filter(
        role=role,
        granted=True,
        permission__is_active=True,
    ).values_list('permission__code', flat=True)

    perms = set(granted)

    # Aplicar overrides de la membresia si existen
    try:
        from access.models import SiteMembershipPermissionOverride
        from companies.models import SiteMembership
        membership = SiteMembership.objects.get(
            user=user, site=site, is_active=True,
        )
        overrides = SiteMembershipPermissionOverride.objects.filter(
            site_membership=membership,
            permission__is_active=True,
        ).values_list('permission__code', 'granted')

        for code, is_granted in overrides:
            if is_granted:
                perms.add(code)
            else:
                perms.discard(code)
    except Exception:
        pass

    return perms


def user_has_permission(user, permission_code, site):
    if not user or not user.is_authenticated:
        return False
    if is_novus_super(user):
        return True
    perms = get_user_permissions_for_site(user, site)
    return permission_code in perms


def site_feature_enabled(site, feature_code):
    if not site:
        return False

    company_flag = COMPANY_FEATURE_FLAGS.get(feature_code)
    if company_flag:
        try:
            company_config = site.company.config
            if not getattr(company_config, company_flag, True):
                return False
        except Exception:
            pass

    site_flag = SITE_FEATURE_FLAGS.get(feature_code)
    if site_flag:
        try:
            site_config = site.config
            return getattr(site_config, site_flag, False)
        except Exception:
            return False

    return True


def get_user_context_permissions(user, site):
    perms = get_user_permissions_for_site(user, site)
    _role = get_user_role_for_site(user, site)

    return {
        'can_start_people':      'sessions.start_people'      in perms,
        'can_start_machines':    'sessions.start_machines'    in perms,
        'can_review_sessions':   'sessions_review.view'       in perms,
        'can_edit_today':        'sessions_review.edit_today' in perms,
        'can_finalize':          'partidas.finalize'          in perms,
        'can_view_resources':    'resources.view'             in perms,
        'can_view_qr':           'resources.view_qr'          in perms,
        'can_crud_people':       'resources.crud_people'      in perms,
        'can_crud_machines':     'resources.crud_machines'    in perms,
        'can_view_progress':     'weekly_progress.view'       in perms,
        'can_edit_progress':     'weekly_progress.edit'       in perms,
        'can_manage_nos':        'no_en_obra.manage'          in perms,
        'can_view_moi':          'moi.view'                   in perms,
        'can_edit_moi':          'moi.edit'                   in perms,
        'can_bulk_close':        'bulk_close.own_sessions'    in perms,
        'can_view_orgchart':     'organigram.view'            in perms,
        'can_edit_orgchart':     'organigram.edit'            in perms,
        'can_manage_companies':  'system.manage_companies'    in perms,
        'can_manage_users':      'system.manage_users'        in perms,
        'can_view_subcontracts': 'subcontracts.view_list'     in perms,
        'can_view_productivity_dashboard': 'dashboard.productivity' in perms,
        'is_novus_super':        is_novus_super(user),
        'role_code':             _role.code if _role else '',
        'role_name':             _role.name if _role else '',
    }


# ─────────────────────────────────────────────────────────────────────────────
# DECORADORES
# ─────────────────────────────────────────────────────────────────────────────

def require_permission(permission_code, json_response=False):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
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
