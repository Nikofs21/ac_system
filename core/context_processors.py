# -*- coding: utf-8 -*-
from companies.models import SiteMembership, CompanyMembership


def active_site(request):
    if not request.user.is_authenticated:
        return {}

    context = {
        'active_site': None,
        'active_company': None,
        'active_site_membership': None,
        'active_company_membership': None,
    }

    try:
        pref = request.user.preference
    except Exception:
        return context

    if pref.last_site:
        context['active_site'] = pref.last_site
        context['active_company'] = pref.last_company

        try:
            site_membership = SiteMembership.objects.select_related('role').get(
                user=request.user,
                site=pref.last_site,
                is_active=True
            )
            context['active_site_membership'] = site_membership
        except SiteMembership.DoesNotExist:
            pass

    if pref.last_company:
        try:
            company_membership = CompanyMembership.objects.get(
                user=request.user,
                company=pref.last_company,
                is_active=True
            )
            context['active_company_membership'] = company_membership
        except CompanyMembership.DoesNotExist:
            pass

    return context
