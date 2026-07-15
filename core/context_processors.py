# -*- coding: utf-8 -*-
from companies.models import SiteMembership, CompanyMembership
from core.permissions import get_user_context_permissions, site_feature_enabled


def active_site(request):
    if not request.user.is_authenticated:
        return {}

    context = {
        'active_site': None,
        'active_company': None,
        'active_site_membership': None,
        'active_company_membership': None,
        'perms_ctx': {},
        'features': {},
        'user_site_count': SiteMembership.objects.filter(
            user=request.user, is_active=True, site__status='ACTIVE',
        ).count(),
    }

    try:
        pref = request.user.preference
    except Exception:
        return context

    if pref.last_site:
        context['active_site']    = pref.last_site
        context['active_company'] = pref.last_company

        try:
            site_membership = SiteMembership.objects.select_related('role').get(
                user=request.user,
                site=pref.last_site,
                is_active=True,
            )
            context['active_site_membership'] = site_membership
        except SiteMembership.DoesNotExist:
            pass

        # Permisos del usuario en la obra activa — disponibles en todos los templates
        context['perms_ctx'] = get_user_context_permissions(request.user, pref.last_site)

        # Feature flags de la obra activa — disponibles en todos los templates
        context['features'] = {
            'no_on_site':    site_feature_enabled(pref.last_site, 'no_on_site'),
            'subcontracts':  site_feature_enabled(pref.last_site, 'subcontracts'),
            'planning':      site_feature_enabled(pref.last_site, 'planning'),
            'orgchart':      site_feature_enabled(pref.last_site, 'orgchart'),
            'assistance':    site_feature_enabled(pref.last_site, 'assistance'),
            'machinery':     site_feature_enabled(pref.last_site, 'machinery'),
            'people':        site_feature_enabled(pref.last_site, 'people'),
        }

    if pref.last_company:
        try:
            company_membership = CompanyMembership.objects.get(
                user=request.user,
                company=pref.last_company,
                is_active=True,
            )
            context['active_company_membership'] = company_membership
        except CompanyMembership.DoesNotExist:
            pass

    return context
