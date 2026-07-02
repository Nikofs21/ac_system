# -*- coding: utf-8 -*-
"""
Señales de la app companies.
"""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from companies.models import Company, CompanyMembership, Site, SiteMembership


# ─────────────────────────────────────────────────────────────────────────────
# Limpieza de acceso en cascada
# ─────────────────────────────────────────────────────────────────────────────

@receiver(post_delete, sender=CompanyMembership)
def eliminar_site_memberships_al_quitar_empresa(sender, instance, **kwargs):
    """
    Cuando se elimina una CompanyMembership, elimina todas las
    SiteMembership del usuario en obras de esa empresa.
    """
    SiteMembership.objects.filter(
        user=instance.user,
        site__company=instance.company,
    ).delete()


# ─────────────────────────────────────────────────────────────────────────────
# Otorgamiento automatico de acceso a novus_super
#
# Garantiza que todo usuario con User.is_novus_super=True quede con acceso
# automatico (membresia) a cada empresa y obra nueva, sin importar por donde
# se haya creado el registro (vista normal, admin de Django, shell, comando
# de management, fixtures, etc.) — post_save se dispara en TODOS esos casos.
#
# Por que aqui y no en las vistas:
# Si esta logica viviera solo en companies/views_provider.py, cualquier otra
# forma de crear una Company/Site (admin, shell, script de carga masiva futuro)
# se saltaria el otorgamiento de acceso. Conectar la señal en el modelo asegura
# el comportamiento sin importar el origen de la creacion.
# ─────────────────────────────────────────────────────────────────────────────

@receiver(post_save, sender=Company)
def grant_novus_super_access_on_company_create(sender, instance, created, **kwargs):
    """Al crear una Company, otorga CompanyMembership a todos los novus_super."""
    if not created:
        return

    from django.contrib.auth import get_user_model
    User = get_user_model()

    novus_super_users = User.objects.filter(is_novus_super=True, is_active=True)

    for user in novus_super_users:
        CompanyMembership.objects.get_or_create(
            user=user,
            company=instance,
            defaults={
                'membership_type': 'PROVIDER',
                'is_active': True,
            }
        )


@receiver(post_save, sender=Site)
def grant_novus_super_access_on_site_create(sender, instance, created, **kwargs):
    """Al crear un Site, otorga SiteMembership (rol novus_super) a todos los novus_super."""
    if not created:
        return

    from django.contrib.auth import get_user_model
    from access.models import Role
    User = get_user_model()

    novus_role = Role.objects.filter(code='novus_super').first()
    if not novus_role:
        # No deberia pasar si seed_roles ya corrio, pero no queremos que
        # la creacion del Site falle por esto.
        return

    novus_super_users = User.objects.filter(is_novus_super=True, is_active=True)

    for user in novus_super_users:
        SiteMembership.objects.get_or_create(
            user=user,
            site=instance,
            defaults={
                'role': novus_role,
                'is_active': True,
                'can_operate': True,
            }
        )
