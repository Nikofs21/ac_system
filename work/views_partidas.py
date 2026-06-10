# -*- coding: utf-8 -*-
"""
Gestión de partidas y etapas por obra.
Solo accesible para prestadores.
"""
import io
import pandas as pd

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.db import transaction
from django.contrib import messages

from companies.models import Site
from work.models import Stage, TaskCatalog, StageTask


def require_provider(view_func):
    from functools import wraps
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.actor_type != 'PROVIDER':
            return redirect('access_denied')
        return view_func(request, *args, **kwargs)
    return wrapper


# ─────────────────────────────────────────────────────────────────────────────
# LISTADO / PANEL PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

@require_provider
def partidas_panel(request):
    """Panel de gestión de partidas — selección de empresa/obra."""
    from companies.models import Company
    companies = Company.objects.exclude(status='ARCHIVED').order_by('name')

    site_id = request.GET.get('site')
    selected_site = None
    stage_tasks = []

    if site_id:
        selected_site = get_object_or_404(Site, id=site_id)
        stage_tasks = StageTask.objects.filter(
            site=selected_site
        ).select_related(
            'stage', 'task'
        ).order_by('stage__name', 'display_order', 'task__code')

    return render(request, 'work/partidas_panel.html', {
        'companies':     companies,
        'selected_site': selected_site,
        'stage_tasks':   stage_tasks,
        'page_title':    'Gestión de partidas',
        'total':         len(stage_tasks),
        'activas':       sum(1 for st in stage_tasks if st.estado_partida == 'activa'),
        'casa':          sum(1 for st in stage_tasks if st.tipo == 'casa'),
        'subcontrato':   sum(1 for st in stage_tasks if st.tipo == 'subcontrato'),
    })


# ─────────────────────────────────────────────────────────────────────────────
# CARGA MASIVA POR EXCEL
# ─────────────────────────────────────────────────────────────────────────────

@require_provider
def partidas_upload(request, site_id):
    """Carga masiva de partidas desde Excel."""
    site = get_object_or_404(Site, id=site_id)

    if request.method == 'POST':
        return _handle_upload(request, site)
    
    formato_cols = [
        ('etapa',          'Nombre de la etapa',                       True),
        ('subetapa',       'Nombre de la subetapa',                    False),
        ('partida',        'Nombre de la partida',                     True),
        ('cantidad',       'Cantidad presupuestada',                   False),
        ('unidad_medida',  'Unidad de medida (m2, ml, un...)',         False),
        ('presupuesto_mo', 'Presupuesto mano obra directa en pesos',   False),
        ('tipo',           'casa o subcontrato (default: casa)',        False),
        ('estado',         'activa o inactiva (default: activa)',       False),
    ]

    return render(request, 'work/partidas_upload.html', {
        'site':       site,
        'page_title': f'Cargar partidas — {site.name}',
    })


def _handle_upload(request, site):
    archivo = request.FILES.get('archivo')

    if not archivo:
        messages.error(request, 'Debes seleccionar un archivo Excel.')
        return redirect(f'/work/partidas/upload/{site.id}/')

    if not archivo.name.endswith(('.xlsx', '.xls')):
        messages.error(request, 'El archivo debe ser .xlsx o .xls.')
        return redirect(f'/work/partidas/upload/{site.id}/')

    try:
        df = pd.read_excel(archivo, sheet_name='Partidas', header=0)
    except Exception:
        try:
            df = pd.read_excel(archivo, header=0)
        except Exception as e:
            messages.error(request, f'Error al leer el archivo: {e}')
            return redirect(f'/work/partidas/upload/{site.id}/')

    # Normalizar nombres de columnas
    df.columns = [str(c).strip().lower() for c in df.columns]

    # Mapeo flexible de nombres de columnas
    col_map = {
        'etapa':             ['etapa'],
        'subetapa':          ['subetapa', 'sub etapa', 'sub_etapa'],
        'partida':           ['partida', 'nombre partida', 'nombre_partida'],
        'cantidad':          ['cantidad', 'cantidad presupuesto', 'cantidad_presupuesto'],
        'unidad_medida':     ['unidad medida', 'unidad_medida', 'um', 'unidad'],
        'presupuesto_total': ['presupuesto_total', 'presupuesto total',
                              'presupuesto total partida', 'ppto total'],
        'presupuesto_mo':    ['presupuesto para mano obra directa',
                              'presupuesto_mo', 'presupuesto mo',
                              'presupuesto mano obra', 'ppto mo'],
        'tipo':              ['tipo'],
        'estado':            ['estado', 'estado_partida', 'estado partida'],
    }

    def find_col(df, candidates):
        for c in candidates:
            if c in df.columns:
                return c
        return None

    col_etapa       = find_col(df, col_map['etapa'])
    col_subetapa    = find_col(df, col_map['subetapa'])
    col_partida     = find_col(df, col_map['partida'])
    col_cantidad    = find_col(df, col_map['cantidad'])
    col_um          = find_col(df, col_map['unidad_medida'])
    col_ppto_total  = find_col(df, col_map['presupuesto_total'])
    col_ppto_mo     = find_col(df, col_map['presupuesto_mo'])
    col_tipo        = find_col(df, col_map['tipo'])
    col_estado      = find_col(df, col_map['estado'])

    if not col_etapa or not col_partida:
        messages.error(request, 'El archivo debe tener columnas "etapa" y "partida".')
        return redirect(f'/work/partidas/upload/{site.id}/')

    created = 0
    updated = 0
    errors  = []

    with transaction.atomic():
        for i, row in df.iterrows():
            linea = i + 2

            etapa_nombre    = str(row.get(col_etapa,   '') or '').strip()
            subetapa_nombre = str(row.get(col_subetapa,'') or '').strip() if col_subetapa else ''
            partida_nombre  = str(row.get(col_partida, '') or '').strip()

            if not etapa_nombre or not partida_nombre:
                continue

            try:
                cantidad = float(row[col_cantidad]) if col_cantidad and pd.notna(row.get(col_cantidad)) else None
            except (ValueError, TypeError):
                cantidad = None

            try:
                ppto_total = float(row[col_ppto_total]) if col_ppto_total and pd.notna(row.get(col_ppto_total)) else None
            except (ValueError, TypeError):
                ppto_total = None

            try:
                ppto_mo = float(row[col_ppto_mo]) if col_ppto_mo and pd.notna(row.get(col_ppto_mo)) else None
            except (ValueError, TypeError):
                ppto_mo = None

            um     = str(row.get(col_um,    '') or '').strip() if col_um    else None
            tipo   = str(row.get(col_tipo,  '') or '').strip().lower() if col_tipo  else 'casa'
            estado = str(row.get(col_estado,'') or '').strip().lower() if col_estado else 'activa'

            if tipo not in ('casa', 'subcontrato', ''):
                tipo = 'casa'
            if not tipo:
                tipo = 'casa'

            if estado not in ('activa', 'inactiva', ''):
                estado = 'activa'
            if not estado:
                estado = 'activa'

            try:
                stage, _ = Stage.objects.get_or_create(
                    company=site.company,
                    site=site,
                    name=etapa_nombre,
                    defaults={
                        'code':       etapa_nombre[:40],
                        'stage_type': 'NORMAL',
                        'is_active':  True,
                    }
                )

                task_code = partida_nombre[:60]
                task, _ = TaskCatalog.objects.get_or_create(
                    company=site.company,
                    code=task_code,
                    defaults={
                        'name':       partida_nombre,
                        'default_um': um or None,
                        'status':     'ACTIVE',
                    }
                )

                st, was_created = StageTask.objects.get_or_create(
                    site=site,
                    stage=stage,
                    task=task,
                    defaults={
                        'subetapa':             subetapa_nombre or None,
                        'cantidad_presupuesto': cantidad,
                        'unidad_medida':        um or None,
                        'presupuesto_total':    ppto_total,
                        'presupuesto_mo':       ppto_mo,
                        'tipo':                 tipo,
                        'estado_partida':       estado,
                        'is_active':            True,
                    }
                )

                if was_created:
                    created += 1
                else:
                    st.subetapa             = subetapa_nombre or None
                    st.cantidad_presupuesto = cantidad
                    st.unidad_medida        = um or None
                    st.presupuesto_total    = ppto_total
                    st.presupuesto_mo       = ppto_mo
                    st.estado_partida       = estado
                    st.save()
                    updated += 1

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
            f'Carga completada: {created} partidas nuevas, {updated} actualizadas.'
        )

    return redirect(f'/work/partidas/?site={site.id}')


# ─────────────────────────────────────────────────────────────────────────────
# EDICIÓN INDIVIDUAL
# ─────────────────────────────────────────────────────────────────────────────

@require_provider
def partida_edit(request, stagetask_id):
    """Editar una partida individual — principalmente tipo y estado."""
    st   = get_object_or_404(StageTask, id=stagetask_id)
    site = st.site

    if request.method == 'POST':
        tipo           = request.POST.get('tipo', 'casa')
        estado_partida = request.POST.get('estado_partida', 'activa')
        cantidad       = request.POST.get('cantidad_presupuesto', '').strip()
        um             = request.POST.get('unidad_medida', '').strip()
        ppto_mo        = request.POST.get('presupuesto_mo', '').strip()
        subetapa       = request.POST.get('subetapa', '').strip()

        st.tipo           = tipo
        st.estado_partida = estado_partida
        st.subetapa       = subetapa or None
        st.unidad_medida  = um or None

        try:
            st.cantidad_presupuesto = float(cantidad) if cantidad else None
        except ValueError:
            st.cantidad_presupuesto = None

        try:
            st.presupuesto_mo = float(ppto_mo) if ppto_mo else None
        except ValueError:
            st.presupuesto_mo = None

        st.save()
        messages.success(request, f'"{st.task.name}" actualizada.')
        return redirect(f'/partidas/?site={site.id}')

    return render(request, 'work/partida_edit.html', {
        'st':         st,
        'site':       site,
        'page_title': f'Editar — {st.task.name}',
    })


# ─────────────────────────────────────────────────────────────────────────────
# CAMBIO RÁPIDO DE TIPO (AJAX)
# ─────────────────────────────────────────────────────────────────────────────

@require_provider
@require_POST
def partida_toggle_tipo(request, stagetask_id):
    """Cambia tipo casa↔subcontrato vía AJAX."""
    st = get_object_or_404(StageTask, id=stagetask_id)
    st.tipo = 'subcontrato' if st.tipo == 'casa' else 'casa'
    st.save()
    return JsonResponse({'status': 'ok', 'tipo': st.tipo})


@require_provider
@require_POST
def partida_toggle_estado(request, stagetask_id):
    """Cambia estado activa↔inactiva vía AJAX."""
    st = get_object_or_404(StageTask, id=stagetask_id)
    st.estado_partida = 'inactiva' if st.estado_partida == 'activa' else 'activa'
    st.save()
    return JsonResponse({'status': 'ok', 'estado': st.estado_partida})
