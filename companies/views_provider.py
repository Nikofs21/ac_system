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
from django.utils.crypto import get_random_string
from django.utils import timezone
from django.urls import reverse
from django.conf import settings

from .models import (
    Company, CompanyConfig, CompanyMembership,
    Site, SiteConfig, SiteMembership, SiteWorkdayConfig,
)
from notifications.models import SiteUnassignedAlertSchedule, SiteAlertConfig
from notifications.services import ensure_unassigned_check_periodic_task
from access.models import Role, Permission, RolePermission, SiteMembershipPermissionOverride, ManagementTitle
from core.permissions import is_novus_super, is_provider_actor, MOI_EXCLUDED_ROLE_CODES
from core.rut_utils import find_rut_conflict

User = get_user_model()


def _build_workday_rows(site=None, post_data=None):
    """
    Arma las 7 filas (Lunes..Domingo) para la seccion "Horario semanal" del
    formulario de obra. Cada fila trae 'mode' en LABORABLE/NO_LABORABLE/None
    — None significa "sin decision tomada todavia", que es justamente lo
    que la validacion de _handle_site_save no deja pasar al guardar.

    Con post_data (reintento tras error de validacion): relee lo que el
    usuario habia tipeado, para no hacerlo repetir todo.
    Sin post_data pero con site (pantalla de edicion): prellena con la
    jornada vigente hoy de cada dia, si existe. Una obra creada antes de
    este formulario (o cuyo dia nunca se configuro) simplemente aparece
    con mode=None — fuerza a decidir de nuevo, no asume nada en su nombre.
    """
    rows = []
    existing_by_weekday = {}
    if site is not None and post_data is None:
        hoy = timezone.localdate()
        for weekday in range(7):
            existing_by_weekday[weekday] = SiteWorkdayConfig.objects.filter(
                site=site, weekday=weekday, is_active=True,
            ).order_by('-effective_from').first()

    for weekday, label in SiteWorkdayConfig.Weekday.choices:
        if post_data is not None:
            prefix = f'workday_{weekday}_'
            rows.append({
                'weekday':          weekday,
                'label':            label,
                'mode':             post_data.get(prefix + 'mode', ''),
                'work_start_time':  post_data.get(prefix + 'start', ''),
                'work_end_time':    post_data.get(prefix + 'end', ''),
                'lunch_start_time': post_data.get(prefix + 'lunch_start', ''),
                'lunch_end_time':   post_data.get(prefix + 'lunch_end', ''),
                'deduct_lunch':     post_data.get(prefix + 'deduct_lunch') == 'on',
                'all_day_overtime': post_data.get(prefix + 'overtime') == 'on',
            })
        else:
            cfg = existing_by_weekday.get(weekday)
            rows.append({
                'weekday':          weekday,
                'label':            label,
                'mode':             'LABORABLE' if cfg else '',
                'work_start_time':  cfg.work_start_time.strftime('%H:%M') if cfg else '',
                'work_end_time':    cfg.work_end_time.strftime('%H:%M') if cfg else '',
                'lunch_start_time': cfg.lunch_start_time.strftime('%H:%M') if cfg and cfg.lunch_start_time else '',
                'lunch_end_time':   cfg.lunch_end_time.strftime('%H:%M') if cfg and cfg.lunch_end_time else '',
                'deduct_lunch':     cfg.deduct_lunch_from_icc if cfg else True,
                'all_day_overtime': cfg.all_day_overtime if cfg else False,
            })
    return rows


def _validate_and_parse_workdays(post_data):
    """
    Valida las 7 filas de horario semanal. Devuelve (parsed, error) donde
    error es un string listo para mostrar, o None si todo esta correcto.
    parsed es una lista de dicts solo con los datos ya convertidos a time(),
    lista para pasar directo a SiteWorkdayConfig.objects.update_or_create.

    Regla no negociable: las 7 filas deben tener una decision explicita
    (LABORABLE o NO_LABORABLE). No hay default silencioso — si al usuario
    se le olvida un dia, se le dice cual falta en vez de asumir algo.
    """
    from datetime import datetime as dt

    parsed = []
    dias_sin_decidir = []

    for weekday, label in SiteWorkdayConfig.Weekday.choices:
        prefix = f'workday_{weekday}_'
        mode = post_data.get(prefix + 'mode', '')

        if mode not in ('LABORABLE', 'NO_LABORABLE'):
            dias_sin_decidir.append(label)
            continue

        if mode == 'NO_LABORABLE':
            parsed.append({'weekday': weekday, 'mode': 'NO_LABORABLE'})
            continue

        start_str = post_data.get(prefix + 'start', '').strip()
        end_str   = post_data.get(prefix + 'end', '').strip()

        if not start_str or not end_str:
            return None, f'Falta la hora de entrada o salida para {label}.'

        try:
            work_start = dt.strptime(start_str, '%H:%M').time()
            work_end   = dt.strptime(end_str, '%H:%M').time()
        except ValueError:
            return None, f'Hora invalida en {label}.'

        if work_end <= work_start:
            return None, f'{label}: la hora de salida debe ser posterior a la de entrada.'

        lunch_start_str = post_data.get(prefix + 'lunch_start', '').strip()
        lunch_end_str   = post_data.get(prefix + 'lunch_end', '').strip()
        lunch_start = lunch_end = None

        if lunch_start_str or lunch_end_str:
            if not (lunch_start_str and lunch_end_str):
                return None, f'{label}: si defines colación, indica ambas horas (inicio y término).'
            try:
                lunch_start = dt.strptime(lunch_start_str, '%H:%M').time()
                lunch_end   = dt.strptime(lunch_end_str, '%H:%M').time()
            except ValueError:
                return None, f'Hora de colación inválida en {label}.'
            if lunch_end <= lunch_start:
                return None, f'{label}: el término de colación debe ser posterior al inicio.'

        parsed.append({
            'weekday':           weekday,
            'mode':              'LABORABLE',
            'work_start_time':   work_start,
            'work_end_time':     work_end,
            'lunch_start_time':  lunch_start,
            'lunch_end_time':    lunch_end,
            'deduct_lunch_from_icc': post_data.get(prefix + 'deduct_lunch') == 'on',
            'all_day_overtime':      post_data.get(prefix + 'overtime') == 'on',
        })

    if dias_sin_decidir:
        return None, (
            'Debes indicar si estos días son laborables o no: '
            + ', '.join(dias_sin_decidir) + '.'
        )

    return parsed, None


def _save_workdays(site, parsed_workdays):
    """
    Aplica las 7 filas ya validadas a SiteWorkdayConfig. Reemplazo completo
    por dia: se borran las filas vigentes de ese weekday y se crea una
    nueva — este formulario es "la config actual", no un historial de
    excepciones por fecha (eso, si hace falta a futuro, es una pantalla
    aparte para ajustes puntuales, no esta).
    """
    effective_from = site.start_date or timezone.localdate()

    for row in parsed_workdays:
        SiteWorkdayConfig.objects.filter(
            site=site, weekday=row['weekday'],
        ).delete()

        if row['mode'] == 'NO_LABORABLE':
            continue

        SiteWorkdayConfig.objects.create(
            site=site,
            weekday=row['weekday'],
            work_start_time=row['work_start_time'],
            work_end_time=row['work_end_time'],
            lunch_start_time=row['lunch_start_time'],
            lunch_end_time=row['lunch_end_time'],
            deduct_lunch_from_icc=row['deduct_lunch_from_icc'],
            all_day_overtime=row['all_day_overtime'],
            is_active=True,
            effective_from=effective_from,
        )


def require_provider(view_func):
    from functools import wraps
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.actor_type != 'PROVIDER':
            return redirect('access_denied')
        return view_func(request, *args, **kwargs)
    return wrapper


def require_novus_super(view_func):
    from functools import wraps
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not is_novus_super(request.user):
            return redirect('access_denied')
        return view_func(request, *args, **kwargs)
    return wrapper


def _check_company_access(request, company):
    """Verifica que el prestador tenga membresía en esta empresa."""
    if is_novus_super(request.user):
        return True
    return CompanyMembership.objects.filter(
        user=request.user,
        company=company,
        is_active=True,
    ).exists()


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
    # novus_super ve todas las empresas; el resto solo las suyas via membresia.
    if is_novus_super(request.user):
        companies = Company.objects.exclude(status='ARCHIVED').order_by('name')
    else:
        companies = Company.objects.filter(
            memberships__user=request.user,
            memberships__is_active=True,
        ).exclude(status='ARCHIVED').order_by('name')

    company_id = request.GET.get('company')
    selected_company = None
    sites = []
    company_config = None
    pending_review_count = 0

    if company_id:
        selected_company = get_object_or_404(Company, id=company_id)
        if not _check_company_access(request, selected_company):
            return redirect('access_denied')
        sites = list(
            Site.objects.filter(company=selected_company)
            .exclude(status='ARCHIVED')
            .prefetch_related('unassigned_alert_schedules', 'alert_configs')
            .order_by('name')
        )

        # Indicadores "sin configurar" — solo lo que se puede detectar sin
        # ambigüedad (existe la fila o no existe). El horario semanal
        # queda fuera a propósito: SiteWorkdayConfig no distingue "día
        # marcado explícitamente como no laborable" de "día nunca tocado",
        # así que no hay forma confiable de avisar sin falsos positivos.
        for site in sites:
            gaps = []
            if not site.unassigned_alert_schedules.all():
                gaps.append('Activos sin partida')
            if not any(ac.alert_type == 'HIGH_RISK_START' for ac in site.alert_configs.all()):
                gaps.append('Alto riesgo')
            site.config_gaps = gaps

        try:
            company_config = selected_company.config
        except CompanyConfig.DoesNotExist:
            company_config = None

        from work.models import WorkSession
        pending_review_count = WorkSession.objects.filter(
            site__company=selected_company, needs_review=True,
        ).count()
    elif companies.exists():
        selected_company = companies.first()
        return redirect(f'/prestador/?company={selected_company.id}')

    return render(request, 'companies/provider_panel.html', {
        'companies':            companies,
        'selected_company':     selected_company,
        'sites':                sites,
        'company_config':       company_config,
        'page_title':           'Panel del prestador',
        'active_tab':           request.GET.get('tab', 'obras'),
        'is_novus_super':       is_novus_super(request.user),
        'pending_review_count': pending_review_count,
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

    if not _check_company_access(request, company):
        return redirect('access_denied')

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
            # NOTA: al crear, companies.signals.grant_novus_super_access_on_company_create
            # otorga CompanyMembership automaticamente a todos los User.is_novus_super=True
            # (incluyendo a request.user si corresponde). No es necesario hacerlo aqui.
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

        # Si quien crea la empresa NO es novus_super, igual necesita su propio
        # acceso (la señal solo cubre a los novus_super existentes).
        if not is_novus_super(request.user):
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
    if not _check_company_access(request, company):
        return JsonResponse({'error': 'Sin acceso a esta empresa.'}, status=403)
    company.status = 'INACTIVE'
    company.save()
    return JsonResponse({'status': 'ok', 'message': f'"{company.name}" desactivada.'})


@require_provider
@require_POST
def company_activate(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    if not _check_company_access(request, company):
        return JsonResponse({'error': 'Sin acceso a esta empresa.'}, status=403)
    company.status = 'ACTIVE'
    company.save()
    return JsonResponse({'status': 'ok', 'message': f'"{company.name}" activada.'})


# ─────────────────────────────────────────────────────────────────────────────
# OBRAS
# ─────────────────────────────────────────────────────────────────────────────

@require_provider
def site_create(request, company_id):
    company = get_object_or_404(Company, id=company_id)

    if not _check_company_access(request, company):
        return redirect('access_denied')

    if request.method == 'POST':
        return _handle_site_save(request, company, None)

    return render(request, 'companies/site_form.html', {
        'mode':         'create',
        'company':      company,
        'page_title':   f'Nueva obra — {company.name}',
        'site_flags':   _site_module_flags(),
        'workday_rows': _build_workday_rows(),
    })


@require_provider
def site_edit(request, site_id):
    site = get_object_or_404(Site, id=site_id)

    if not _check_company_access(request, site.company):
        return redirect('access_denied')

    try:
        config = site.config
    except SiteConfig.DoesNotExist:
        config = None

    if request.method == 'POST':
        return _handle_site_save(request, site.company, site)

    return render(request, 'companies/site_form.html', {
        'mode':         'edit',
        'company':      site.company,
        'site':         site,
        'config':       config,
        'page_title':   f'Editar — {site.name}',
        'site_flags':   _site_module_flags(config),
        'workday_rows': _build_workday_rows(site=site),
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

    parsed_workdays, workday_error = _validate_and_parse_workdays(request.POST)
    if workday_error:
        errors['workdays'] = workday_error

    if errors:
        try:
            config = site.config if site else None
        except Exception:
            config = None
        return render(request, 'companies/site_form.html', {
            'mode':         'create' if site is None else 'edit',
            'company':      company,
            'site':         site,
            'errors':       errors,
            'post_data':    request.POST,
            'page_title':   f'Nueva obra — {company.name}' if site is None else f'Editar — {site.name}',
            'site_flags':   _site_module_flags(config),
            'workday_rows': _build_workday_rows(post_data=request.POST),
        })

    with transaction.atomic():
        if site is None:
            # NOTA: al crear, companies.signals.grant_novus_super_access_on_site_create
            # otorga SiteMembership (rol novus_super) automaticamente a todos los
            # User.is_novus_super=True. Ya no se otorga manualmente aqui.
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

        _save_workdays(site, parsed_workdays)

        # Si quien crea la obra NO es novus_super, igual necesita su propio
        # acceso operativo (la señal solo cubre a los novus_super existentes).
        if site.pk and not is_novus_super(request.user):
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

    if not _check_company_access(request, site.company):
        return JsonResponse({'error': 'Sin acceso a esta empresa.'}, status=403)

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
# OVERRIDES DE PERMISOS POR MEMBRESÍA
# ─────────────────────────────────────────────────────────────────────────────

@require_provider
def membership_overrides(request, membership_id):
    membership = get_object_or_404(SiteMembership, id=membership_id)
    site       = membership.site
    user       = membership.user

    if not _check_company_access(request, site.company):
        return redirect('access_denied')

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


# ─────────────────────────────────────────────────────────────────────────────
# GESTIÓN DE ROLES (solo novus_super)
# ─────────────────────────────────────────────────────────────────────────────

@require_novus_super
def role_list(request):
    """Lista todos los roles base con resumen de permisos."""
    roles = Role.objects.filter(
        is_active=True,
        scope_type='GLOBAL_BASE',
    ).order_by('name')

    roles_data = []
    for role in roles:
        perm_count = RolePermission.objects.filter(role=role, granted=True).count()
        roles_data.append({
            'role':       role,
            'perm_count': perm_count,
        })

    return render(request, 'companies/role_list.html', {
        'roles_data': roles_data,
        'page_title': 'Gestión de roles',
    })


@require_novus_super
def role_permissions(request, role_id):
    """Editar permisos de un rol base. Roles protegidos (is_protected=True) son de solo lectura."""
    role = get_object_or_404(Role, id=role_id, scope_type='GLOBAL_BASE')

    all_permissions = Permission.objects.filter(is_active=True).order_by('module', 'name')

    current_perms = set(
        RolePermission.objects.filter(
            role=role, granted=True
        ).values_list('permission__code', flat=True)
    )

    if request.method == 'POST':
        if role.is_protected:
            messages.error(request, f'"{role.name}" es un rol protegido del sistema y no puede modificarse.')
            return redirect('provider:role_permissions', role_id=role.id)
        return _handle_role_permissions_save(request, role, all_permissions)

    perms_data = []
    for perm in all_permissions:
        perms_data.append({
            'perm':    perm,
            'granted': perm.code in current_perms,
        })

    return render(request, 'companies/role_permissions.html', {
        'role':       role,
        'perms_data': perms_data,
        'page_title': f'Permisos — {role.name}',
    })


def _handle_role_permissions_save(request, role, all_permissions):
    # Defensa adicional por si se llega aqui sin pasar por la verificacion de la vista.
    if role.is_protected:
        messages.error(request, f'"{role.name}" es un rol protegido del sistema y no puede modificarse.')
        return redirect('provider:role_permissions', role_id=role.id)

    with transaction.atomic():
        for perm in all_permissions:
            checked = request.POST.get(f'perm_{perm.code}') == 'on'
            RolePermission.objects.update_or_create(
                role=role,
                permission=perm,
                defaults={'granted': checked},
            )

    messages.success(request, f'Permisos de "{role.name}" actualizados.')
    return redirect('provider:role_permissions', role_id=role.id)


# ─────────────────────────────────────────────────────────────────────────────
# GERENCIA / ADMINISTRADOR DE OBRA / AAC — pantalla exclusiva de prestador
#
# Estos 3 roles (ver core.permissions.MOI_EXCLUDED_ROLE_CODES) ya no se
# otorgan desde MOI para nadie. Se gestionan aqui porque:
# - Solo un prestador (is_provider_actor: actor_type=PROVIDER o novus_super)
#   puede darlos de alta.
# - 'admin_obra' solo puede tener UNA obra activa a la vez.
# - 'gerencia' puede abarcar varias obras de la misma empresa y tiene un
#   sub-cargo propio de la empresa (ManagementTitle: Gerente de proyecto,
#   Gerente de operaciones, etc.). 'admin_obra' y 'aac' no usan sub-cargo.
# - Activar/desactivar y editar las obras de un usuario se resuelve en un
#   solo formulario de "checkboxes de obra" (management_user_edit), en vez
#   de un boton de toggle por fila.
# ─────────────────────────────────────────────────────────────────────────────

def _management_scope_companies(request):
    if is_novus_super(request.user):
        return Company.objects.exclude(status='ARCHIVED').order_by('name')
    return Company.objects.filter(
        memberships__user=request.user,
        memberships__is_active=True,
    ).exclude(status='ARCHIVED').order_by('name')


@require_provider
def management_users_panel(request):
    """
    Lista + alta de usuarios con rol admin_obra / gerencia / aac, filtrados
    por empresa. El formulario de alta vive en la misma pantalla (igual que
    el viejo gerencia_create).
    """
    companies = _management_scope_companies(request)

    if request.method == 'POST':
        return _handle_management_user_create(request, companies)

    company_id = request.GET.get('company_id', '')
    company = companies.filter(id=company_id).first() if company_id else companies.first()

    management_titles = ManagementTitle.for_company(company) if company else ManagementTitle.objects.none()
    all_sites = Site.objects.filter(company=company).exclude(status='ARCHIVED').order_by('name') if company else Site.objects.none()

    memberships = SiteMembership.objects.filter(
        site__company=company,
        role__code__in=MOI_EXCLUDED_ROLE_CODES,
    ).select_related('user', 'site', 'role').order_by('user__first_name', 'user__last_name', 'site__name') if company else SiteMembership.objects.none()

    users_map = {}
    for m in memberships:
        key = m.user_id
        if key not in users_map:
            company_membership = CompanyMembership.objects.filter(user=m.user, company=company).first()
            users_map[key] = {
                'user':              m.user,
                'role':              m.role,
                'management_title':  company_membership.management_title if company_membership else None,
                'memberships':       [],
                'active_count':      0,
            }
        users_map[key]['memberships'].append(m)
        if m.is_active:
            users_map[key]['active_count'] += 1

    return render(request, 'companies/management_users.html', {
        'companies':         companies,
        'company':           company,
        'all_sites':         all_sites,
        'management_titles': management_titles,
        'users':             list(users_map.values()),
        'page_title':        'Gerencia y Administración de obra',
    })


def _handle_management_user_create(request, companies):
    from access.views_moi import _normalize_rut  # reutiliza el normalizador existente
    from access.models import UserPreference

    role_code            = request.POST.get('role_code', '')
    company_id           = request.POST.get('company_id', '')
    site_ids              = request.POST.getlist('site_ids')
    first_name            = request.POST.get('first_name', '').strip()
    last_name             = request.POST.get('last_name', '').strip()
    email                  = request.POST.get('email', '').strip().lower()
    rut                    = request.POST.get('rut', '').strip()
    management_title_id   = request.POST.get('management_title_id', '')
    notes                  = request.POST.get('notes', '').strip()

    errors = {}
    if role_code not in MOI_EXCLUDED_ROLE_CODES:
        errors['role_code'] = 'Rol invalido.'
    if not company_id:
        errors['company_id'] = 'Selecciona una empresa.'
    if not site_ids:
        errors['site_ids'] = 'Selecciona al menos una obra.'
    if role_code == 'admin_obra' and len(site_ids) > 1:
        errors['site_ids'] = 'Administrador de obra solo puede tener una obra asignada.'
    if not first_name:
        errors['first_name'] = 'El nombre es obligatorio.'
    if not last_name:
        errors['last_name'] = 'El apellido es obligatorio.'
    if not email:
        errors['email'] = 'El correo es obligatorio.'

    company = companies.filter(id=company_id).first() if company_id else None
    if company_id and not company:
        errors['company_id'] = 'Empresa invalida o sin acceso.'

    sites = Site.objects.filter(id__in=site_ids, company=company) if company else Site.objects.none()
    if site_ids and company and sites.count() != len(set(site_ids)):
        errors['site_ids'] = 'Una o mas obras seleccionadas no pertenecen a esta empresa.'

    management_title = None
    if role_code == 'gerencia' and management_title_id and company:
        management_title = ManagementTitle.objects.filter(id=management_title_id, company=company).first()

    if rut:
        rut = _normalize_rut(rut)
        existing_user_by_email = User.objects.filter(email=email).first() if email else None
        conflict = find_rut_conflict(
            rut,
            exclude_user_id=existing_user_by_email.id if existing_user_by_email else None,
        )
        if conflict:
            errors['rut'] = conflict

    if errors:
        return render(request, 'companies/management_users.html', {
            'companies':          companies,
            'company':            company,
            'all_sites':          Site.objects.filter(company=company).exclude(status='ARCHIVED').order_by('name') if company else Site.objects.none(),
            'management_titles':  ManagementTitle.for_company(company) if company else ManagementTitle.objects.none(),
            'users':              [],
            'errors':             errors,
            'post_data':          request.POST,
            'selected_site_ids':  site_ids,
            'page_title':         'Gerencia y Administración de obra',
        })

    role = Role.objects.filter(code=role_code, is_active=True).first()
    if not role:
        messages.error(request, f'El rol "{role_code}" no esta configurado en el sistema. Corre seed_roles primero.')
        return redirect(f'{reverse("provider:management_users")}?company_id={company.id}')

    omitted_sites = []

    with transaction.atomic():
        existing_user = User.objects.filter(email=email).first()

        if existing_user:
            user = existing_user
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
            user = User.objects.create_user(
                email=email,
                password=get_random_string(32),
                first_name=first_name,
                last_name=last_name,
                rut=rut or None,
                actor_type='CLIENT',
                is_active=True,
            )

        company_membership, _created = CompanyMembership.objects.get_or_create(
            user=user,
            company=company,
            defaults={'membership_type': 'CLIENT_COMPANY', 'is_active': True}
        )
        if role_code == 'gerencia':
            company_membership.management_title = management_title
            company_membership.save(update_fields=['management_title'])

        for site in sites:
            already = SiteMembership.objects.filter(user=user, site=site).first()
            if already and already.is_active:
                omitted_sites.append(site.name)
                continue

            if already:
                already.role        = role
                already.is_active   = True
                already.ended_at    = None
                already.notes       = notes or None
                already.granted_by  = request.user
                already.save()
            else:
                SiteMembership.objects.create(
                    user=user,
                    site=site,
                    role=role,
                    is_active=True,
                    can_operate=True,
                    notes=notes or None,
                    granted_by=request.user,
                )

        UserPreference.objects.get_or_create(
            user=user,
            defaults={'last_site': sites.first(), 'last_company': company}
        )

    granted_count = sites.count() - len(omitted_sites)
    if granted_count > 0:
        messages.success(
            request,
            f'{user.get_full_name()} agregado como {role.name} en {granted_count} obra(s) de {company.name}.'
        )
    if omitted_sites:
        messages.warning(
            request,
            f'Se omitieron estas obras porque el usuario ya tenia acceso activo: {", ".join(omitted_sites)}.'
        )

    return redirect(f'{reverse("provider:management_users")}?company_id={company.id}')


@require_provider
@require_POST
def management_title_create(request):
    """Crea (o reactiva) un sub-cargo de gerencia para una empresa, sin recargar la pagina."""
    company_id = request.POST.get('company_id', '')
    name = request.POST.get('name', '').strip()

    if not name:
        return JsonResponse({'error': 'El nombre del cargo es obligatorio.'}, status=400)
    if len(name) > 120:
        return JsonResponse({'error': 'El nombre no puede superar 120 caracteres.'}, status=400)

    companies = _management_scope_companies(request)
    company = companies.filter(id=company_id).first()
    if not company:
        return JsonResponse({'error': 'Empresa invalida o sin acceso.'}, status=403)

    existing = ManagementTitle.objects.filter(company=company, name__iexact=name).first()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            existing.save(update_fields=['is_active'])
        return JsonResponse({'status': 'ok', 'id': existing.id, 'name': existing.name})

    title = ManagementTitle.objects.create(company=company, name=name, is_active=True)
    return JsonResponse({'status': 'ok', 'id': title.id, 'name': title.name})


@require_provider
def management_user_edit(request, user_id, company_id):
    """
    Activa/desactiva y edita las obras de un usuario admin_obra/gerencia/aac
    dentro de una empresa: un solo formulario de checkboxes de obra. Marcar
    una obra que no tenia membresia la crea; desmarcar una obra activa la
    desactiva (no la elimina — se puede volver a marcar despues).
    """
    companies = _management_scope_companies(request)
    company = get_object_or_404(companies, id=company_id)
    target_user = get_object_or_404(User, id=user_id)

    memberships = SiteMembership.objects.filter(
        user=target_user, site__company=company, role__code__in=MOI_EXCLUDED_ROLE_CODES,
    ).select_related('site', 'role')
    if not memberships.exists():
        messages.error(request, 'No se encontro membresia de gerencia/admin obra/aac para este usuario en esta empresa.')
        return redirect(f'{reverse("provider:management_users")}?company_id={company.id}')

    role = memberships.first().role
    all_sites = Site.objects.filter(company=company).exclude(status='ARCHIVED').order_by('name')
    current_site_ids = set(memberships.filter(is_active=True).values_list('site_id', flat=True))

    company_membership = CompanyMembership.objects.filter(user=target_user, company=company).first()
    management_titles = ManagementTitle.for_company(company) if role.code == 'gerencia' else ManagementTitle.objects.none()

    if request.method == 'POST':
        new_site_ids = set(int(x) for x in request.POST.getlist('site_ids') if x)

        if role.code == 'admin_obra' and len(new_site_ids) > 1:
            messages.error(request, 'Administrador de obra solo puede tener una obra asignada.')
            return redirect(request.path)

        with transaction.atomic():
            existing_site_ids = set(memberships.values_list('site_id', flat=True))

            for m in memberships:
                should_be_active = m.site_id in new_site_ids
                if m.is_active != should_be_active:
                    m.is_active = should_be_active
                    m.ended_at  = timezone.localdate() if not should_be_active else None
                    m.save()

            for site_id in new_site_ids - existing_site_ids:
                site = all_sites.filter(id=site_id).first()
                if site:
                    SiteMembership.objects.create(
                        user=target_user, site=site, role=role,
                        is_active=True, can_operate=True, granted_by=request.user,
                    )

            if role.code == 'gerencia' and company_membership:
                mt_id = request.POST.get('management_title_id', '')
                company_membership.management_title = management_titles.filter(id=mt_id).first() if mt_id else None
                company_membership.save(update_fields=['management_title'])

        messages.success(request, f'Obras de {target_user.get_full_name()} actualizadas.')
        return redirect(f'{reverse("provider:management_users")}?company_id={company.id}')

    return render(request, 'companies/management_user_edit.html', {
        'company':                     company,
        'target_user':                 target_user,
        'role':                        role,
        'all_sites':                   all_sites,
        'current_site_ids':            current_site_ids,
        'management_titles':           management_titles,
        'current_management_title_id': company_membership.management_title_id if company_membership else None,
        'page_title':                  f'Editar obras — {target_user.get_full_name()}',
    })


# ─────────────────────────────────────────────────────────────────────────────
# ALERTAS — ACTIVOS SIN PARTIDA ASIGNADA
# ─────────────────────────────────────────────────────────────────────────────

def _parse_email_list(raw):
    """
    Convierte un textarea (correos separados por coma, punto y coma o
    salto de linea) en una lista limpia. Devuelve (lista, error) — error
    es None si todo esta bien formado.
    """
    import re
    if not raw or not raw.strip():
        return [], None

    items  = re.split(r'[,\n;]+', raw)
    emails = [e.strip() for e in items if e.strip()]
    email_re = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
    invalidos = [e for e in emails if not email_re.match(e)]

    if invalidos:
        return None, f'Correo(s) con formato invalido: {", ".join(invalidos)}'
    return emails, None


@require_provider
def unassigned_alert_list(request, site_id):
    """
    Lista + formulario de alta para los horarios de alerta "activos sin
    partida" de una obra. Opcional — una obra puede no tener ninguno.
    """
    site = get_object_or_404(Site, id=site_id)
    if not _check_company_access(request, site.company):
        return redirect('access_denied')

    schedules = SiteUnassignedAlertSchedule.objects.filter(site=site).order_by('send_time')

    return render(request, 'companies/unassigned_alert_list.html', {
        'site':        site,
        'schedules':   schedules,
        'page_title':  f'Alertas — Activos sin partida — {site.name}',
    })


@require_provider
@require_POST
def unassigned_alert_save(request, site_id):
    """
    Crea o actualiza un horario de alerta. update_or_create por
    (site, send_time) — si ya existe un horario a esa hora, lo actualiza
    en vez de duplicar (coincide con la UniqueConstraint del modelo).
    """
    site = get_object_or_404(Site, id=site_id)
    if not _check_company_access(request, site.company):
        return redirect('access_denied')

    send_time_str = request.POST.get('send_time', '').strip()
    to_raw        = request.POST.get('to_emails', '')
    cc_raw        = request.POST.get('cc_emails', '')
    is_enabled    = request.POST.get('is_enabled') == 'on'

    if not send_time_str:
        messages.error(request, 'Debes indicar una hora.')
        return redirect('provider:unassigned_alert_list', site_id=site.id)

    from datetime import datetime as dt
    try:
        send_time = dt.strptime(send_time_str, '%H:%M').time()
    except ValueError:
        messages.error(request, 'Hora invalida.')
        return redirect('provider:unassigned_alert_list', site_id=site.id)

    to_emails, to_error = _parse_email_list(to_raw)
    if to_error:
        messages.error(request, f'Destinatarios (TO): {to_error}')
        return redirect('provider:unassigned_alert_list', site_id=site.id)
    if not to_emails:
        messages.error(request, 'Debes indicar al menos un destinatario (TO).')
        return redirect('provider:unassigned_alert_list', site_id=site.id)

    cc_emails, cc_error = _parse_email_list(cc_raw)
    if cc_error:
        messages.error(request, f'Destinatarios (CC): {cc_error}')
        return redirect('provider:unassigned_alert_list', site_id=site.id)

    SiteUnassignedAlertSchedule.objects.update_or_create(
        site=site, send_time=send_time,
        defaults={
            'to_emails':  to_emails,
            'cc_emails':  cc_emails,
            'is_enabled': is_enabled,
        }
    )

    # Sincroniza el crontab exacto de Celery Beat para esta hora — si ya
    # existia (otra obra la usa, o se estaba editando), no duplica nada.
    ensure_unassigned_check_periodic_task(send_time.hour, send_time.minute)

    messages.success(request, f'Horario {send_time.strftime("%H:%M")} guardado.')
    return redirect('provider:unassigned_alert_list', site_id=site.id)


@require_provider
@require_POST
def unassigned_alert_delete(request, schedule_id):
    schedule = get_object_or_404(SiteUnassignedAlertSchedule, id=schedule_id)
    site = schedule.site
    if not _check_company_access(request, site.company):
        return redirect('access_denied')

    schedule.delete()
    messages.success(request, 'Horario eliminado.')
    return redirect('provider:unassigned_alert_list', site_id=site.id)


# ─────────────────────────────────────────────────────────────────────────────
# ALERTAS — ALTO RIESGO (correo acumulado, opcional)
# ─────────────────────────────────────────────────────────────────────────────

@require_provider
def high_risk_alert_config(request, site_id):
    """
    Interruptor + destinatarios del correo acumulado de alto riesgo. La
    confirmacion en pantalla (checkbox EPP) NO se toca aca — esto solo
    prende/apaga el correo adicional. Un solo registro por obra (a
    diferencia de "activos sin partida", que admite varios horarios).
    """
    site = get_object_or_404(Site, id=site_id)
    if not _check_company_access(request, site.company):
        return redirect('access_denied')

    config = SiteAlertConfig.objects.filter(site=site, alert_type='HIGH_RISK_START').first()

    if request.method == 'POST':
        is_enabled = request.POST.get('is_enabled') == 'on'
        to_raw     = request.POST.get('to_emails', '')
        cc_raw     = request.POST.get('cc_emails', '')

        to_emails, to_error = _parse_email_list(to_raw)
        if to_error:
            messages.error(request, f'Destinatarios (TO): {to_error}')
            return redirect('provider:high_risk_alert_config', site_id=site.id)

        if is_enabled and not to_emails:
            messages.error(request, 'Si activas la alerta, debes indicar al menos un destinatario (TO).')
            return redirect('provider:high_risk_alert_config', site_id=site.id)

        cc_emails, cc_error = _parse_email_list(cc_raw)
        if cc_error:
            messages.error(request, f'Destinatarios (CC): {cc_error}')
            return redirect('provider:high_risk_alert_config', site_id=site.id)

        SiteAlertConfig.objects.update_or_create(
            site=site, alert_type='HIGH_RISK_START',
            defaults={
                'is_enabled': is_enabled,
                'to_emails':  to_emails,
                'cc_emails':  cc_emails,
            }
        )
        messages.success(request, 'Configuración de alerta de alto riesgo guardada.')
        return redirect('provider:high_risk_alert_config', site_id=site.id)

    return render(request, 'companies/high_risk_alert_config.html', {
        'site':        site,
        'config':      config,
        'batch_minutes': getattr(site.config, 'high_risk_email_batch_minutes', 30) if hasattr(site, 'config') else 30,
        'page_title':  f'Alertas — Alto riesgo — {site.name}',
    })


# ─────────────────────────────────────────────────────────────────────────────
# BANDEJA DE REVISIÓN — CIERRES MANUALES FUERA DE HORARIO
# ─────────────────────────────────────────────────────────────────────────────

@require_provider
def session_review_queue(request, company_id):
    """
    Lista las sesiones marcadas needs_review=True, agrupadas por obra.

    Dentro de cada obra:
    - Cierres MASS_CLOSE / TASK_CLOSE (varias personas cerradas de un
      golpe) se agrupan por partida — un solo formulario con un solo
      horario resuelve todo el grupo, en vez de ir persona por persona.
    - Cierres MANUAL (uno a la vez) se muestran individuales, porque no
      hay garantía de que compartan el mismo motivo real.

    No es una cola de "errores" — muchas de estas van a tener una
    justificación real (hora extra, por ejemplo) y no requieren ningún
    cambio. Es solo visibilidad.
    """
    from work.models import WorkSession

    company = get_object_or_404(Company, id=company_id)
    if not _check_company_access(request, company):
        return redirect('access_denied')

    sessions = WorkSession.objects.filter(
        site__company=company, needs_review=True,
    ).select_related('site', 'resource', 'ended_by').order_by(
        'site__name', 'task_name_snapshot', '-ended_at'
    )

    # site -> {'individual': [sesiones MANUAL], 'by_task': {partida: [sesiones]}}
    grouped = {}
    for s in sessions:
        bucket = grouped.setdefault(s.site, {'individual': [], 'by_task': {}})
        if s.closure_origin in ('MASS_CLOSE', 'TASK_CLOSE'):
            bucket['by_task'].setdefault(s.task_name_snapshot, []).append(s)
        else:
            bucket['individual'].append(s)

    return render(request, 'companies/session_review_queue.html', {
        'company':     company,
        'grouped':     grouped,
        'threshold':   getattr(settings, 'REVIEW_CLOSE_THRESHOLD_MINUTES', 45),
        'page_title':  f'Revisión de cierres — {company.name}',
    })


def _apply_session_review_adjust(session, new_time_str, reason, user):
    """
    Aplica el ajuste a UNA sesión — lo comparten la vista individual y la
    masiva para no duplicar el cálculo de hora/timezone. Devuelve None si
    salió bien, o un string de error si la hora venía mal formada.
    """
    from work.models import WorkSessionChangeLog
    from datetime import datetime as dt
    import pytz

    before = {
        'ended_at':         session.ended_at.isoformat() if session.ended_at else None,
        'duration_minutes': session.duration_minutes,
    }

    if new_time_str:
        try:
            site_tz = pytz.timezone(session.site.timezone or 'America/Santiago')
            local_date = timezone.localtime(session.ended_at, site_tz).date() if session.ended_at else timezone.localdate()
            new_time = dt.strptime(new_time_str, '%H:%M').time()
            new_ended_at_local = site_tz.localize(dt.combine(local_date, new_time))
            session.ended_at = new_ended_at_local.astimezone(pytz.utc)
            if session.started_at:
                session.duration_minutes = int((session.ended_at - session.started_at).total_seconds() / 60)
        except ValueError:
            return 'Hora inválida.'

    session.needs_review = False
    session.save()

    WorkSessionChangeLog.objects.create(
        session=session,
        changed_by=user,
        change_type='PROVIDER_ADJUST',
        before_json=before,
        after_json={
            'ended_at':         session.ended_at.isoformat() if session.ended_at else None,
            'duration_minutes': session.duration_minutes,
        },
        reason=reason,
    )
    return None


@require_provider
@require_POST
def session_review_adjust(request, session_id):
    """Ajusta UNA sesión (caso MANUAL, uno a la vez)."""
    from work.models import WorkSession

    session = get_object_or_404(WorkSession, id=session_id)
    if not _check_company_access(request, session.site.company):
        return redirect('access_denied')

    reason = request.POST.get('reason', '').strip()
    if not reason:
        messages.error(request, 'El motivo es obligatorio para ajustar un cierre.')
        return redirect('provider:session_review_queue', company_id=session.site.company.id)

    error = _apply_session_review_adjust(
        session, request.POST.get('new_ended_at', '').strip(), reason, request.user
    )
    if error:
        messages.error(request, error)
    else:
        messages.success(request, f'Cierre de {session.resource.display_name} revisado.')

    return redirect('provider:session_review_queue', company_id=session.site.company.id)


@require_provider
@require_POST
def session_review_bulk_adjust(request):
    """
    Ajusta VARIAS sesiones a la vez, con el mismo horario y motivo — para
    resolver de un golpe un grupo de cierre masivo agrupado por partida
    (botón "Usar mismo horario para todos" en la bandeja).
    """
    from work.models import WorkSession

    session_ids = request.POST.getlist('session_ids')
    reason      = request.POST.get('reason', '').strip()
    new_time    = request.POST.get('new_ended_at', '').strip()

    if not session_ids:
        messages.error(request, 'No se seleccionó ninguna sesión.')
        return redirect('provider:panel')

    sessions = list(WorkSession.objects.filter(id__in=session_ids).select_related('site__company', 'resource'))
    if not sessions:
        messages.error(request, 'No se encontraron las sesiones.')
        return redirect('provider:panel')

    company = sessions[0].site.company
    if not _check_company_access(request, company):
        return redirect('access_denied')

    if not reason:
        messages.error(request, 'El motivo es obligatorio para ajustar un cierre.')
        return redirect('provider:session_review_queue', company_id=company.id)

    resolved = 0
    for session in sessions:
        error = _apply_session_review_adjust(session, new_time, reason, request.user)
        if not error:
            resolved += 1

    messages.success(request, f'{resolved} sesion{"es" if resolved != 1 else ""} revisada{"s" if resolved != 1 else ""}.')
    return redirect('provider:session_review_queue', company_id=company.id)
