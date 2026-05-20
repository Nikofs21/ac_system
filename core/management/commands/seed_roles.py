# -*- coding: utf-8 -*-
"""
Comando para sembrar roles y permisos base en la base de datos.
Uso: python manage.py seed_roles

Idempotente: puede correrse multiples veces sin duplicar datos.
Actualiza permisos de roles existentes si la matriz cambio.
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
        # Mapeo de codigo a modulo (derivado del prefijo del codigo)
        module_map = {
            'sessions':          'OPERACION',
            'sessions_review':   'OPERACION',
            'partidas':          'OPERACION',
            'resources':         'RECURSOS',
            'weekly_progress':   'PLANIFICACION',
            'no_en_obra':        'OPERACION',
            'moi':               'USUARIOS',
            'bulk_close':        'OPERACION',
            'organigram':        'ORGANIGRAMA',
            'system':            'CONFIGURACION_ESTRUCTURAL',
        }

        level_map = {
            'sessions.start_people':       'OPERATE',
            'sessions.start_machines':     'OPERATE',
            'sessions_review.view':        'VIEW',
            'sessions_review.edit_today':  'SENSITIVE',
            'partidas.finalize':           'SENSITIVE',
            'resources.view':              'VIEW',
            'resources.view_qr':           'VIEW',
            'resources.crud_people':       'ADMIN',
            'resources.crud_machines':     'ADMIN',
            'weekly_progress.view':        'VIEW',
            'weekly_progress.edit':        'OPERATE',
            'no_en_obra.manage':           'OPERATE',
            'moi.view':                    'VIEW',
            'moi.edit':                    'ADMIN',
            'bulk_close.own_sessions':     'SENSITIVE',
            'organigram.view':             'VIEW',
            'organigram.edit':             'ADMIN',
            'system.manage_companies':     'SENSITIVE',
            'system.manage_users':         'SENSITIVE',
        }

        created = 0
        updated = 0

        for code, name in PERMISSION_CODES.items():
            prefix = code.split('.')[0]
            module = module_map.get(prefix, 'CONFIGURACION')
            level = level_map.get(code, 'OPERATE')

            perm, was_created = Permission.objects.update_or_create(
                code=code,
                defaults={
                    'name': name,
                    'module': module,
                    'level': level,
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
            'novus_super':    'Superadmin Novus',
            'novus_consultor':'Consultor Prestador',
            'gerencia':       'Gerencia',
            'admin_obra':     'Administrador de obra',
            'administrativo': 'Administrativo',
            'supervisor':     'Supervisor',
            'bodeguero':      'Bodeguero',
            'planificador':   'Planificador',
            'jefe_terreno':   'Jefe de terreno',
            'aac':            'Administrador A&C',
        }

        # Roles de prestador vs cliente (para referencia)
        provider_roles = {'novus_super', 'novus_consultor'}

        for code, name in role_names.items():
            role, created = Role.objects.get_or_create(
                code=code,
                defaults={
                    'name': name,
                    'scope_type': 'GLOBAL_BASE',
                    'is_active': True,
                    'description': f'Rol base: {name}',
                }
            )

            if created:
                self.stdout.write(f'  + Rol creado: {code}')
            else:
                self.stdout.write(f'  ~ Rol existente: {code} (actualizando permisos)')

            # Sincronizar permisos del rol segun la matriz
            permission_codes = ROLE_PERMISSIONS.get(code, [])
            self._sync_role_permissions(role, permission_codes)

        self.stdout.write(f'  Roles: {len(role_names)} procesados.')

    def _sync_role_permissions(self, role, permission_codes):
        """
        Sincroniza los permisos de un rol con la matriz definida.
        - Agrega los que faltan
        - Desactiva (granted=False) los que ya no corresponden
        - No borra registros para mantener historial
        """
        # Obtener todos los permisos activos del catalogo
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
