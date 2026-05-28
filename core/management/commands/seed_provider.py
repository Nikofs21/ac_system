# -*- coding: utf-8 -*-
"""
Comando para crear usuario prestador (novus_super) de prueba.
Uso: python manage.py seed_provider

Usuario creado:
  admin@novusimperium.cl / novus1234  → rol: novus_super
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone

from companies.models import Company, Site, CompanyMembership, SiteMembership
from access.models import Role, UserPreference

User = get_user_model()


class Command(BaseCommand):
    help = 'Crea usuario prestador novus_super de prueba'

    def handle(self, *args, **options):
        self.stdout.write('Creando usuario prestador...')

        # ── ROL ───────────────────────────────────────────────────────────────
        role, _ = Role.objects.get_or_create(
            code='novus_super',
            defaults={
                'name':       'Superadmin Novus',
                'scope_type': 'GLOBAL_BASE',
                'is_active':  True,
            }
        )

        # ── USUARIO ───────────────────────────────────────────────────────────
        user, created = User.objects.get_or_create(
            email='admin@novusimperium.cl',
            defaults={
                'first_name': 'Admin',
                'last_name':  'Novus',
                'actor_type': 'PROVIDER',
                'is_active':  True,
                'is_staff':   True,
            }
        )
        if created:
            user.set_password('novus1234')
            user.save()
            self.stdout.write(self.style.SUCCESS('  Usuario creado.'))
        else:
            self.stdout.write('  Usuario ya existe, actualizando...')
            user.actor_type = 'PROVIDER'
            user.is_staff   = True
            user.save()

        # ── MEMBRESÍAS EN TODAS LAS EMPRESAS Y OBRAS ACTIVAS ─────────────────
        companies = Company.objects.filter(status='ACTIVE')
        memberships_company = 0
        memberships_site    = 0

        for company in companies:
            CompanyMembership.objects.get_or_create(
                user=user,
                company=company,
                defaults={
                    'membership_type': 'PROVIDER',
                    'is_active':       True,
                }
            )
            memberships_company += 1

            # Membresía en cada obra activa de la empresa
            for site in Site.objects.filter(company=company, status='ACTIVE'):
                membership, _ = SiteMembership.objects.get_or_create(
                    user=user,
                    site=site,
                    defaults={
                        'role':        role,
                        'is_active':   True,
                        'can_operate': True,
                    }
                )
                # Actualizar rol si ya existía con otro
                if membership.role != role:
                    membership.role = role
                    membership.save()
                memberships_site += 1

        # ── PREFERENCIA — setear última obra activa ───────────────────────────
        first_site = Site.objects.filter(status='ACTIVE').first()
        pref, _ = UserPreference.objects.get_or_create(
            user=user,
            defaults={
                'last_site':    first_site,
                'last_company': first_site.company if first_site else None,
            }
        )
        if first_site and not pref.last_site:
            pref.last_site    = first_site
            pref.last_company = first_site.company
            pref.save()

        self.stdout.write(self.style.SUCCESS('\nPrestador creado correctamente.'))
        self.stdout.write(self.style.SUCCESS('  admin@novusimperium.cl / novus1234  → novus_super'))
        self.stdout.write(f'  Membresías empresa: {memberships_company}')
        self.stdout.write(f'  Membresías obra:    {memberships_site}')
        self.stdout.write('')
        self.stdout.write('  Este usuario tiene acceso total al sistema.')
        self.stdout.write('  Cambia la contraseña antes de ir a producción.')
