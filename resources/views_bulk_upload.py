# -*- coding: utf-8 -*-
"""
Carga masiva de trabajadores desde Excel.
Solo accesible para prestadores.
"""
import pandas as pd

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone

from companies.models import Site
from resources.models import Resource, ResourceCategory, JobTitle, ResourceSiteAssignment
from core.rut_utils import find_rut_conflict


def require_provider(view_func):
    from functools import wraps
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.actor_type != 'PROVIDER':
            return redirect('access_denied')
        return view_func(request, *args, **kwargs)
    return wrapper


def _normalize_rut(rut_str):
    if not rut_str:
        return None
    clean = str(rut_str).replace('.', '').replace(' ', '').upper().strip()
    if '-' in clean:
        parts = clean.split('-')
        return f'{parts[0]}-{parts[1]}'
    if len(clean) >= 2:
        return f'{clean[:-1]}-{clean[-1]}'
    return clean


@require_provider
def workers_bulk_upload(request, site_id):
    site = get_object_or_404(Site, id=site_id)

    if request.method == 'POST':
        return _handle_workers_upload(request, site)

    formato_cols = [
        ('nombre',         'Nombre(s)',                           True),
        ('apellido',       'Apellido(s)',                         False),
        ('rut',            'RUT (cualquier formato)',             True),
        ('cargo',          'Cargo operativo',                     True),
        ('tipo',           'persona o maquinaria',                True),
        ('codigo_interno', 'Codigo interno opcional',             False),
        ('patente',        'Patente (solo maquinarias)',          False),
        ('estado',         'activo o inactivo (default: activo)', False),
    ]

    return render(request, 'resources/workers_bulk_upload.html', {
        'site':         site,
        'page_title':   f'Carga masiva trabajadores — {site.name}',
        'formato_cols': formato_cols,
    })


def _handle_workers_upload(request, site):
    archivo = request.FILES.get('archivo')

    if not archivo:
        messages.error(request, 'Debes seleccionar un archivo Excel.')
        return redirect(f'/resources/carga-masiva/{site.id}/')

    if not archivo.name.endswith(('.xlsx', '.xls')):
        messages.error(request, 'El archivo debe ser .xlsx o .xls.')
        return redirect(f'/resources/carga-masiva/{site.id}/')

    try:
        df = pd.read_excel(archivo, sheet_name='Trabajadores', header=0)
    except Exception:
        try:
            df = pd.read_excel(archivo, header=0)
        except Exception as e:
            messages.error(request, f'Error al leer el archivo: {e}')
            return redirect(f'/resources/carga-masiva/{site.id}/')

    # Saltar fila descriptiva si existe
    if len(df) > 0:
        first_val = str(df.iloc[0, 0]).lower()
        if any(x in first_val for x in ['nombre', 'trabaj', 'col']):
            df = df.iloc[1:].reset_index(drop=True)

    df.columns = [str(c).strip().lower() for c in df.columns]

    col_map = {
        'nombre':         ['nombre', 'nombres', 'name'],
        'apellido':       ['apellido', 'apellidos', 'last_name'],
        'rut':            ['rut', 'rut/patente', 'documento'],
        'cargo':          ['cargo', 'cargo_operativo', 'job_title'],
        'tipo':           ['tipo', 'type', 'categoria'],
        'codigo_interno': ['codigo_interno', 'codigo', 'code', 'cod'],
        'patente':        ['patente', 'license_plate', 'placa'],
        'estado':         ['estado', 'status', 'estado_recurso'],
    }

    def find_col(df, candidates):
        for c in candidates:
            if c in df.columns:
                return c
        return None

    col_nombre   = find_col(df, col_map['nombre'])
    col_apellido = find_col(df, col_map['apellido'])
    col_rut      = find_col(df, col_map['rut'])
    col_cargo    = find_col(df, col_map['cargo'])
    col_tipo     = find_col(df, col_map['tipo'])
    col_cod      = find_col(df, col_map['codigo_interno'])
    col_patente  = find_col(df, col_map['patente'])
    col_estado   = find_col(df, col_map['estado'])

    if not col_nombre or not col_rut or not col_cargo or not col_tipo:
        messages.error(request, 'El archivo debe tener columnas: nombre, rut, cargo, tipo.')
        return redirect(f'/resources/carga-masiva/{site.id}/')

    category_cache  = {}
    job_title_cache = {}
    created  = 0
    updated  = 0
    assigned = 0
    errors   = []

    with transaction.atomic():
        for i, row in df.iterrows():
            linea = i + 3

            nombre   = str(row.get(col_nombre,   '') or '').strip()
            apellido = str(row.get(col_apellido, '') or '').strip() if col_apellido else ''
            if apellido.lower() == 'nan':
                apellido = ''
            rut_raw  = str(row.get(col_rut,      '') or '').strip()
            cargo    = str(row.get(col_cargo,    '') or '').strip().upper()
            tipo_raw = str(row.get(col_tipo,     '') or '').strip().lower()
            cod      = str(row.get(col_cod,      '') or '').strip() if col_cod     else ''
            patente  = str(row.get(col_patente,  '') or '').strip() if col_patente else ''
            estado   = str(row.get(col_estado,   '') or '').strip().lower() if col_estado else 'activo'

            if not nombre or not rut_raw or not cargo:
                continue

            rut = _normalize_rut(rut_raw)
            if not rut:
                errors.append(f'Fila {linea}: RUT invalido ({rut_raw})')
                continue

            display_name  = f'{nombre} {apellido}'.strip() if apellido else nombre
            resource_type = 'MACHINERY' if 'maq' in tipo_raw else 'PERSON'
            status        = 'ACTIVE' if estado in ('activo', 'active', '') else 'INACTIVE'

            try:
                cat_key = resource_type
                if cat_key not in category_cache:
                    category_cache[cat_key] = ResourceCategory.objects.filter(
                        resource_type=resource_type, is_active=True
                    ).first()
                category = category_cache[cat_key]
                if not category:
                    errors.append(f'Fila {linea}: No existe categoria para tipo "{tipo_raw}".')
                    continue

                jt_key = cargo
                if jt_key not in job_title_cache:
                    jt, _ = JobTitle.objects.get_or_create(
                        company=site.company,
                        name=cargo,
                        defaults={
                            'code':          cargo[:40],
                            'resource_type': resource_type,
                            'is_active':     True,
                        }
                    )
                    job_title_cache[jt_key] = jt
                job_title = job_title_cache[jt_key]

                existing = Resource.objects.filter(
                    company=site.company,
                    person_rut=rut,
                ).first()

                if existing:
                    existing.display_name    = display_name
                    existing.normalized_name = display_name.lower().strip()
                    existing.job_title       = job_title
                    existing.status          = status
                    if cod:
                        existing.internal_code = cod
                    if patente:
                        existing.license_plate = patente
                    existing.updated_by = request.user
                    existing.save()
                    resource = existing
                    updated += 1
                else:
                    conflict = find_rut_conflict(rut)
                    if conflict:
                        errors.append(f'Fila {linea}: {conflict}')
                        continue
                    resource = Resource.objects.create(
                        company=site.company,
                        resource_category=category,
                        display_name=display_name,
                        normalized_name=display_name.lower().strip(),
                        person_rut=rut if resource_type == 'PERSON' else None,
                        license_plate=patente or None,
                        internal_code=cod or None,
                        job_title=job_title,
                        status=status,
                        is_trackable=True,
                        created_by=request.user,
                        updated_by=request.user,
                    )
                    created += 1

                already_assigned = ResourceSiteAssignment.objects.filter(
                    resource=resource,
                    site=site,
                    status='ACTIVE',
                ).exists()

                if not already_assigned:
                    ResourceSiteAssignment.objects.create(
                        resource=resource,
                        site=site,
                        assignment_type='PRIMARY',
                        status='ACTIVE',
                        assigned_by=request.user,
                        started_at=timezone.now(),
                    )
                    assigned += 1

            except Exception as e:
                errors.append(f'Fila {linea}: {e}')
                if len(errors) > 10:
                    errors.append('... demasiados errores, se detuvo el proceso.')
                    break

    if errors:
        for err in errors:
            messages.error(request, err)
    else:
        messages.success(
            request,
            f'Carga completada: {created} trabajadores nuevos, '
            f'{updated} actualizados, {assigned} asignados a la obra.'
        )

    return redirect(f'/resources/trabajadores/?site={site.id}')

@require_provider
def workers_bulk_select_site(request):
    """Selector de empresa/obra antes de la carga masiva de trabajadores."""
    from companies.models import Company
    companies = Company.objects.exclude(status='ARCHIVED').order_by('name')

    site_id = request.GET.get('site')
    if site_id:
        return redirect(f'/resources/carga-masiva/{site_id}/')

    return render(request, 'resources/workers_bulk_select_site.html', {
        'companies':  companies,
        'page_title': 'Carga masiva de trabajadores',
    })