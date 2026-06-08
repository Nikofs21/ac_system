# -*- coding: utf-8 -*-
"""
Panel de gestion del prestador.
Permite crear/editar empresas, obras, feature flags, usuarios y overrides de permisos.
Solo accesible para usuarios con actor_type=PROVIDER.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.db import transaction
from django.contrib import messages
from django.contrib.auth import get_user_model

from .models import (
    Company, CompanyConfig, CompanyMembership,
    Site, SiteConfig, SiteMembership,
)
from access.models import Role, Permission, SiteMembershipPermissionOverride

User = get_user_model()


def require_provider(view_func):
    from functools import wraps
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.actor_type != 'PROVIDER':
            return redirect('access_denied')
        return view_func(request, *args, **kwargs)
    return wrapper


def _company_module_flags(config=None):
    return [
        ('allow_subcontracts', 'Subcontratos', config.allow_subcontracts if config else True),
        ('allow_machinery',    'Maquinarias',  config.allow_machinery    if config else False),
        ('allow_planning',     'Planificación', config.allow_planning    if config else False),
        ('allow_orgchart',     'Organigrama',   config.allow_orgchart    if config else False),
        ('allow_assistance',   'Asistencia',    config.allow_assistance  if config else False),
    ]


def _site_module_flags(config=None):
    return [
        ('use_subcontracts',           'Subcontratos', config.use_subcontracts            if config else True),
        ('use_machinery',              'Maquinarias',  config.use_machinery               if config else False),
        ('use_planning',               'Planificación', config.use_planning               if config else False),
        ('use_orgchart',               'Organigrama',   config.use_orgchart               if config else False),
        ('enable_no_on_site_tracking', 'No en obra',    config.enable_no_on_site_tracking if config else True),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# PANEL PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

@require_provider
def provider_panel(request):
    companies = Company.objects.exclude(status='ARCHIVED').order_by('name')

    company_id = request.GET.get('company')
    selected_company = None
    sites = []
    company_config = None

    if company_id:
        selected_company = get_object_or_404(Company, id=company_id)
        sites = Site.objects.filter(
            company=selected_company
        ).exclude(status='ARCHIVED').order_by('name')
        try:
            company_config = selected_company.config
        except CompanyConfig.DoesNotExist:
            company_config = None
    elif companies.exists():
        selected_company = companies.first()
        return redirect(f'/prestador/?company={selected_company.id}')

    return render(request, 'companies/provider_panel.html', {
        'companies':        companies,
        'selected_company': selected_company,
        'sites':            sites,
        'company_config':   company_config,
        'page_title':       'Panel del prestador',
        'active_tab':       request.GET.get('tab', 'obras'),
    })


# ─────────────────────────────────────────────────────────────────────────────
# EMPRESAS
# ─────────────────────────────────────────────────────────────────────────────

@require_provider
def company_create(request):
    if request.method == 'POST':
        return _handle_company_save(request, None)

    return render(request, 'companies/company_form.html', {
        'mode':           'create',
        'page_title':     'Nueva empresa',
        'status_choices': Company.Status.choices,
        'module_flags':   _company_module_flags(),
    })


@require_provider
def company_edit(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    try:
        config = company.config
    except CompanyConfig.DoesNotExist:
        config = None

    if request.method == 'POST':
        return _handle_company_save(request, company)

    return render(request, 'companies/company_form.html', {
        'mode':           'edit',
        'company':        company,
        'config':         config,
        'page_title':     f'Editar — {company.name}',
        'status_choices': Company.Status.choices,
        'module_flags':   _company_module_flags(config),
    })


def _handle_company_save(request, company):
    name          = request.POST.get('name', '').strip()
    code          = request.POST.get('code', '').strip().upper()
    tax_id        = request.POST.get('tax_id', '').strip()
    contact_email = request.POST.get('contact_email', '').strip()
    contact_phone = request.POST.get('contact_phone', '').strip()
    status        = request.POST.get('status', 'ACTIVE')

    allow_subcontracts = request.POST.get('allow_subcontracts') == 'on'
    allow_machinery    = request.POST.get('allow_machinery') == 'on'
    allow_planning     = request.POST.get('allow_planning') == 'on'
    allow_orgchart     = request.POST.get('allow_orgchart') == 'on'
    allow_assistance   = request.POST.get('allow_assistance') == 'on'

    errors = {}
    if not name: errors['name'] = 'El nombre es obligatorio.'
    if not code: errors['code'] = 'El código es obligatorio.'
    elif company is None and Company.objects.filter(code=code).exists():
        errors['code'] = 'Ya existe una empresa con ese código.'
    elif company and Company.objects.filter(code=code).exclude(id=company.id).exists():
        errors['code'] = 'Ya existe una empresa con ese código.'

    if errors:
        try:
            config = company.config if company else None
        except Exception:
            config = None
        return render(request, 'companies/company_form.html', {
            'mode':           'create' if company is None else 'edit',
            'company':        company,
            'errors':         errors,
            'post_data':      request.POST,
            'page_title':     'Nueva empresa' if company is None else f'Editar — {company.name}',
            'status_choices': Company.Status.choices,
            'module_flags':   _company_module_flags(config),
        })

    with transaction.atomic():
        if company is None:
            company = Company.objects.create(
                name=name, code=code, status=status,
                tax_id=tax_id or None,
                contact_email=contact_email or None,
                contact_phone=contact_phone or None,
                created_by=request.user,
            )
        else:
            company.name          = name
            company.code          = code
            company.status        = status
            company.tax_id        = tax_id or None
            company.contact_email = contact_email or None
            company.contact_phone = contact_phone or None
            company.save()

        config, _ = CompanyConfig.objects.get_or_create(company=company)
        config.allow_subcontracts = allow_subcontracts
        config.allow_machinery    = allow_machinery
        config.allow_planning     = allow_planning
        config.allow_orgchart     = allow_orgchart
        config.allow_assistance   = allow_assistance
        config.save()

        CompanyMembership.objects.get_or_create(
            user=request.user,
            company=company,
            defaults={'membership_type': 'PROVIDER', 'is_active': True}
        )

    messages.success(request, f'Empresa "{company.name}" guardada.')
    return redirect(f'/prestador/?company={company.id}')


@require_provider
@require_POST
def company_deactivate(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    company.status = 'INACTIVE'
    company.save()
    return JsonResponse({'status': 'ok', 'message': f'"{company.name}" desactivada.'})


@require_provider
@require_POST
def company_activate(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    company.status = 'ACTIVE'
    company.save()
    return JsonResponse({'status': 'ok', 'message': f'"{company.name}" activada.'})


# ─────────────────────────────────────────────────────────────────────────────
# OBRAS
# ─────────────────────────────────────────────────────────────────────────────

@require_provider
def site_create(request, company_id):
    company = get_object_or_404(Company, id=company_id)

    if request.method == 'POST':
        return _handle_site_save(request, company, None)

    return render(request, 'companies/site_form.html', {
        'mode':       'create',
        'company':    company,
        'page_title': f'Nueva obra — {company.name}',
        'site_flags': _site_module_flags(),
    })


@require_provider
def site_edit(request, site_id):
    site = get_object_or_404(Site, id=site_id)
    try:
        config = site.config
    except SiteConfig.DoesNotExist:
        config = None

    if request.method == 'POST':
        return _handle_site_save(request, site.company, site)

    return render(request, 'companies/site_form.html', {
        'mode':       'edit',
        'company':    site.company,
        'site':       site,
        'config':     config,
        'page_title': f'Editar — {site.name}',
        'site_flags': _site_module_flags(config),
    })


def _handle_site_save(request, company, site):
    name       = request.POST.get('name', '').strip()
    code       = request.POST.get('code', '').strip().upper()
    status     = request.POST.get('status', 'PLANNED')
    address    = request.POST.get('address', '').strip()
    start_date = request.POST.get('start_date', '').strip() or None
    end_date   = request.POST.get('end_date', '').strip() or None

    use_subcontracts  = request.POST.get('use_subcontracts') == 'on'
    use_machinery     = request.POST.get('use_machinery') == 'on'
    use_planning      = request.POST.get('use_planning') == 'on'
    use_orgchart      = request.POST.get('use_orgchart') == 'on'
    enable_no_on_site = request.POST.get('enable_no_on_site_tracking') == 'on'

    errors = {}
    if not name: errors['name'] = 'El nombre es obligatorio.'
    if not code: errors['code'] = 'El código es obligatorio.'
    elif site is None and Site.objects.filter(company=company, code=code).exists():
        errors['code'] = 'Ya existe una obra con ese código en esta empresa.'
    elif site and Site.objects.filter(company=company, code=code).exclude(id=site.id).exists():
        errors['code'] = 'Ya existe una obra con ese código en esta empresa.'

    if errors:
        try:
            config = site.config if site else None
        except Exception:
            config = None
        return render(request, 'companies/site_form.html', {
            'mode':       'create' if site is None else 'edit',
            'company':    company,
            'site':       site,
            'errors':     errors,
            'post_data':  request.POST,
            'page_title': f'Nueva obra — {company.name}' if site is None else f'Editar — {site.name}',
            'site_flags': _site_module_flags(config),
        })

    with transaction.atomic():
        if site is None:
            site = Site.objects.create(
                company=company,
                name=name, code=code, status=status,
                address=address or None,
                start_date=start_date,
                end_date=end_date,
            )
        else:
            site.name       = name
            site.code       = code
            site.status     = status
            site.address    = address or None
            site.start_date = start_date
            site.end_date   = end_date
            site.save()

        config, _ = SiteConfig.objects.get_or_create(site=site)
        config.use_subcontracts           = use_subcontracts
        config.use_machinery              = use_machinery
        config.use_planning               = use_planning
        config.use_orgchart               = use_orgchart
        config.enable_no_on_site_tracking = enable_no_on_site
        config.save()

        novus_role = Role.objects.filter(code='novus_super').first()
        if novus_role:
            SiteMembership.objects.get_or_create(
                user=request.user,
                site=site,
                defaults={
                    'role':        novus_role,
                    'is_active':   True,
                    'can_operate': True,
                }
            )

    messages.success(request, f'Obra "{site.name}" guardada.')
    return redirect(f'/prestador/?company={company.id}')


# ─────────────────────────────────────────────────────────────────────────────
# USUARIOS DE UNA OBRA
# ─────────────────────────────────────────────────────────────────────────────

@require_provider
def site_users(request, site_id):
    site = get_object_or_404(Site, id=site_id)
    memberships = SiteMembership.objects.filter(
        site=site
    ).select_related('user', 'role').order_by('user__first_name')

    data = []
    for m in memberships:
        data.append({
            'membership_id': m.id,
            'user_id':       m.user.id,
            'name':          m.user.get_full_name() or m.user.email,
            'email':         m.user.email,
            'role':          m.role.name,
            'role_code':     m.role.code,
            'is_active':     m.is_active,
        })

    return JsonResponse({'users': data, 'site': site.name})


# ─────────────────────────────────────────────────────────────────────────────
# OVERRIDES DE PERMISOS
# ─────────────────────────────────────────────────────────────────────────────

@require_provider
def membership_overrides(request, membership_id):
    membership = get_object_or_404(SiteMembership, id=membership_id)
    site       = membership.site
    user       = membership.user

    from access.models import RolePermission
    role_perms = set(
        RolePermission.objects.filter(
            role=membership.role, granted=True
        ).values_list('permission__code', flat=True)
    )

    overrides = {
        o.permission.code: o.granted
        for o in SiteMembershipPermissionOverride.objects.filter(
            site_membership=membership
        ).select_related('permission')
    }

    all_permissions = Permission.objects.filter(is_active=True).order_by('module', 'name')

    if request.method == 'POST':
        return _handle_overrides_save(request, membership)

    perms_data = []
    for perm in all_permissions:
        if perm.code in overrides:
            status = 'override_on' if overrides[perm.code] else 'override_off'
        elif perm.code in role_perms:
            status = 'role_on'
        else:
            status = 'role_off'

        perms_data.append({
            'perm':   perm,
            'status': status,
        })

    return render(request, 'companies/membership_overrides.html', {
        'membership': membership,
        'site':       site,
        'user':       user,
        'perms_data': perms_data,
        'page_title': f'Permisos — {user.get_full_name()}',
    })


def _handle_overrides_save(request, membership):
    all_perms = Permission.objects.filter(is_active=True)

    with transaction.atomic():
        for perm in all_perms:
            field_value = request.POST.get(f'perm_{perm.code}', 'default')

            if field_value == 'default':
                SiteMembershipPermissionOverride.objects.filter(
                    site_membership=membership,
                    permission=perm,
                ).delete()
            elif field_value == 'on':
                SiteMembershipPermissionOverride.objects.update_or_create(
                    site_membership=membership,
                    permission=perm,
                    defaults={'granted': True, 'created_by': request.user}
                )
            elif field_value == 'off':
                SiteMembershipPermissionOverride.objects.update_or_create(
                    site_membership=membership,
                    permission=perm,
                    defaults={'granted': False, 'created_by': request.user}
                )

    messages.success(request, f'Permisos de {membership.user.get_full_name()} actualizados.')
    return redirect(f'/prestador/?company={membership.site.company.id}&tab=usuarios')
