# -*- coding: utf-8 -*-
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from companies.models import SiteMembership, CompanyMembership
from access.models import UserPreference


@login_required
def dashboard(request):
    # Si no tiene preferencia o no tiene obra activa, ir a seleccion
    try:
        pref = request.user.preference
        if not pref.last_site:
            return redirect('select_site')
    except UserPreference.DoesNotExist:
        return redirect('select_site')

    return render(request, 'dashboard.html', {
        'page_title': 'Dashboard',
    })


@login_required
def select_site(request):
    # Obtener todas las obras activas del usuario
    site_memberships = SiteMembership.objects.select_related(
        'site', 'site__company', 'role'
    ).filter(
        user=request.user,
        is_active=True,
        site__status='ACTIVE'
    ).order_by('site__company__name', 'site__name')

    if request.method == 'POST':
        site_membership_id = request.POST.get('site_membership_id')
        if site_membership_id:
            try:
                membership = site_memberships.get(id=site_membership_id)
                pref, created = UserPreference.objects.get_or_create(
                    user=request.user
                )
                pref.last_site = membership.site
                pref.last_company = membership.site.company
                pref.save()
                messages.success(
                    request,
                    f'Obra activa: {membership.site.name}'
                )
                return redirect('dashboard')
            except SiteMembership.DoesNotExist:
                messages.error(request, 'Obra no valida.')

    return render(request, 'select_site.html', {
        'site_memberships': site_memberships,
        'page_title': 'Seleccionar obra',
    })


@login_required
def change_site(request):
    # Limpiar obra activa y redirigir a seleccion
    try:
        pref = request.user.preference
        pref.last_site = None
        pref.last_company = None
        pref.save()
    except UserPreference.DoesNotExist:
        pass
    return redirect('select_site')
