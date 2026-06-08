# -*- coding: utf-8 -*-
"""
Comando para sembrar roles y permisos base en la base de datos.
Uso: python manage.py seed_roles

Idempotente: puede correrse multiples veces sin duplicar datos.
Lee modulo y nivel directamente de PERMISSION_CODES — sin mapas manuales.
"""
from django.core.management.base import BaseCommand
from access.models import Role, Permission, RolePermission
from core.permissions import PERMISSION_CODES, ROLE_PERMISSIONS


class Command(BaseCommand):
    help = 'Siembra roles base y permisos en la base de datos'

    def handle(self, *args, **options):
        self.stdout.write('Sembrando permisos...')
        self._seed_permissions()

        self.stdout.write('Sembrando roles base...')
        self._seed_roles()

        self.stdout.write(self.style.SUCCESS('\nRoles y permisos sembrados correctamente.'))

    def _seed_permissions(self):
        """Crea o actualiza todos los permisos del catalogo."""
        created = 0
        updated = 0

        for code, meta in PERMISSION_CODES.items():
            perm, was_created = Permission.objects.update_or_create(
                code=code,
                defaults={
                    'name':      meta['name'],
                    'module':    meta['module'],
                    'level':     meta['level'],
                    'is_active': True,
                }
            )
            if was_created:
                created += 1
                self.stdout.write(f'  + Permiso creado: {code}')
            else:
                updated += 1

        self.stdout.write(f'  Permisos: {created} creados, {updated} actualizados.')

    def _seed_roles(self):
        """Crea roles base y asigna sus permisos segun la matriz."""
        role_names = {
            'novus_super':     'Superadmin Novus',
            'novus_consultor': 'Consultor Prestador',
            'gerencia':        'Gerencia',
            'admin_obra':      'Administrador de obra',
            'administrativo':  'Administrativo',
            'supervisor':      'Supervisor',
            'bodeguero':       'Bodeguero',
            'planificador':    'Planificador',
            'jefe_terreno':    'Jefe de terreno',
            'aac':             'Administrador A&C',
        }

        for code, name in role_names.items():
            role, created = Role.objects.get_or_create(
                code=code,
                defaults={
                    'name':        name,
                    'scope_type':  'GLOBAL_BASE',
                    'is_active':   True,
                    'description': f'Rol base: {name}',
                }
            )

            if created:
                self.stdout.write(f'  + Rol creado: {code}')
            else:
                self.stdout.write(f'  ~ Rol existente: {code} (actualizando permisos)')

            permission_codes = ROLE_PERMISSIONS.get(code, [])
            self._sync_role_permissions(role, permission_codes)

        self.stdout.write(f'  Roles: {len(role_names)} procesados.')

    def _sync_role_permissions(self, role, permission_codes):
        """Sincroniza permisos del rol con la matriz."""
        all_permissions = {
            p.code: p for p in Permission.objects.filter(is_active=True)
        }
        granted_codes = set(permission_codes)

        for perm_code, perm_obj in all_permissions.items():
            should_grant = perm_code in granted_codes
            rp, created = RolePermission.objects.get_or_create(
                role=role,
                permission=perm_obj,
                defaults={'granted': should_grant}
            )
            if not created and rp.granted != should_grant:
                rp.granted = should_grant
                rp.save()
