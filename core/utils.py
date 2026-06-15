# -*- coding: utf-8 -*-
"""
Utilidades compartidas entre todas las apps.
"""


def get_active_site(request):
    """
    Retorna la obra activa del usuario según su preferencia.
    Verifica que el usuario siga teniendo membresía activa en esa obra.
    Si no tiene acceso, limpia la preferencia y retorna None.
    """
    try:
        site = request.user.preference.last_site
        if site is None:
            return None

        from companies.models import SiteMembership
        has_access = SiteMembership.objects.filter(
            user=request.user,
            site=site,
            is_active=True,
        ).exists()

        if not has_access:
            request.user.preference.last_site = None
            request.user.preference.save()
            return None

        return site
    except Exception:
        return None
