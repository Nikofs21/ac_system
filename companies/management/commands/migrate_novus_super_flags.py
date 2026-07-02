# -*- coding: utf-8 -*-
"""
Comando de migracion de datos — corre UNA SOLA VEZ despues de aplicar las
migraciones de modelo (User.is_novus_super y Role.is_protected).

Hace dos cosas:
1. Marca User.is_novus_super=True para todo usuario que ya tenga una
   SiteMembership activa con rol novus_super (preserva el acceso actual).
2. Marca Role.is_protected=True para los roles novus_super y novus_consultor.

Uso:
    python manage.py migrate_novus_super_flags
    python manage.py migrate_novus_super_flags --dry-run
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Migra el estado actual de novus_super (por membresia) a los nuevos flags de User/Role.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Simular sin guardar nada')

    def handle(self, *args, **options):
        from django.contrib.auth import get_user_model
        from access.models import Role
        from companies.models import SiteMembership

        User = get_user_model()
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no se guardara nada'))

        # ── 1. Usuarios con SiteMembership novus_super → User.is_novus_super ──
        user_ids = SiteMembership.objects.filter(
            role__code='novus_super',
            is_active=True,
        ).values_list('user_id', flat=True).distinct()

        users = User.objects.filter(id__in=user_ids)
        self.stdout.write(f'Usuarios encontrados con membresia novus_super: {users.count()}')

        updated_users = 0
        for user in users:
            self.stdout.write(f'  - {user.get_full_name()} ({user.email})')
            if not dry_run and not user.is_novus_super:
                user.is_novus_super = True
                user.save(update_fields=['is_novus_super'])
                updated_users += 1

        # ── 2. Marcar roles protegidos ──────────────────────────────────────
        protected_codes = ['novus_super', 'novus_consultor']
        roles = Role.objects.filter(code__in=protected_codes)
        self.stdout.write(f'\nRoles a proteger: {roles.count()}')

        updated_roles = 0
        for role in roles:
            self.stdout.write(f'  - {role.name} ({role.code})')
            if not dry_run and not role.is_protected:
                role.is_protected = True
                role.save(update_fields=['is_protected'])
                updated_roles += 1

        self.stdout.write('')
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'DRY RUN — se actualizarian {users.count()} usuarios y {roles.count()} roles'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Listo. Usuarios actualizados: {updated_users}. Roles protegidos: {updated_roles}.'
            ))
