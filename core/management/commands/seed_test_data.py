# -*- coding: utf-8 -*-
"""
Comando para cargar datos de prueba.
Uso: python manage.py seed_test_data

Usuarios de prueba:
  supervisor@prueba.cl      / prueba1234  → rol: supervisor
  administrativo@prueba.cl  / prueba1234  → rol: administrativo
  jefe@prueba.cl            / prueba1234  → rol: jefe_terreno
  aac@prueba.cl             / prueba1234  → rol: aac
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import time

from companies.models import (
    Company, CompanyConfig, Site, SiteConfig,
    SiteWorkdayConfig, CompanyMembership, SiteMembership
)
from access.models import Role
from resources.models import ResourceCategory, JobTitle, Resource, ResourceSiteAssignment
from work.models import Stage, TaskCatalog, StageTask

User = get_user_model()


class Command(BaseCommand):
    help = 'Carga datos de prueba para desarrollo'

    def handle(self, *args, **options):
        self.stdout.write('Cargando datos de prueba...')

        # ── 1. ROLES ───────────────────────────────────────────────────────────
        roles = {}
        roles_data = [
            ('supervisor',    'Supervisor'),
            ('administrativo','Administrativo'),
            ('jefe_terreno',  'Jefe de terreno'),
            ('aac',           'Administrador A&C'),
        ]
        for code, name in roles_data:
            role, _ = Role.objects.get_or_create(
                code=code,
                defaults={
                    'name':       name,
                    'scope_type': 'GLOBAL_BASE',
                    'is_active':  True,
                }
            )
            roles[code] = role
        self.stdout.write('  Roles OK')

        # ── 2. EMPRESA ─────────────────────────────────────────────────────────
        company, _ = Company.objects.get_or_create(
            code='PRUEBA',
            defaults={
                'name':          'Constructora Prueba SpA',
                'status':        'ACTIVE',
                'contact_email': 'contacto@constructoraprueba.cl',
            }
        )
        CompanyConfig.objects.get_or_create(
            company=company,
            defaults={
                'control_mode':     'PERSONAS',
                'allow_people':     True,
                'allow_subcontracts': True,
            }
        )
        self.stdout.write('  Empresa OK')

        # ── 3. OBRA ────────────────────────────────────────────────────────────
        site, _ = Site.objects.get_or_create(
            company=company,
            code='P001',
            defaults={
                'name':       'Edificio Las Condes',
                'status':     'ACTIVE',
                'address':    'Av. Apoquindo 4501, Las Condes, Santiago',
                'timezone':   'America/Santiago',
                'start_date': timezone.now().date(),
            }
        )
        SiteConfig.objects.get_or_create(
            site=site,
            defaults={
                'use_people':                   True,
                'use_subcontracts':             True,
                'enable_no_on_site_tracking':   True,
                'enable_no_on_site_alert_only': True,
                'high_risk_email_batch_minutes': 30,
            }
        )

        jornada = [
            (0, '08:00', '18:00', '13:00', '14:00'),
            (1, '08:00', '18:00', '13:00', '14:00'),
            (2, '08:00', '18:00', '13:00', '14:00'),
            (3, '08:00', '18:00', '13:00', '14:00'),
            (4, '08:00', '17:00', '13:00', '14:00'),
        ]
        for weekday, start, end, lunch_s, lunch_e in jornada:
            SiteWorkdayConfig.objects.get_or_create(
                site=site,
                weekday=weekday,
                defaults={
                    'work_start_time':  time(*[int(x) for x in start.split(':')]),
                    'work_end_time':    time(*[int(x) for x in end.split(':')]),
                    'lunch_start_time': time(*[int(x) for x in lunch_s.split(':')]),
                    'lunch_end_time':   time(*[int(x) for x in lunch_e.split(':')]),
                    'deduct_lunch_from_icc': True,
                    'is_active': True,
                }
            )
        self.stdout.write('  Obra y jornada OK')

        # ── 4. USUARIOS DE PRUEBA ──────────────────────────────────────────────
        usuarios = [
            ('supervisor@prueba.cl',     'Juan',   'Vasquez',   'CLIENT', 'supervisor'),
            ('administrativo@prueba.cl', 'Maria',  'Gonzalez',  'CLIENT', 'administrativo'),
            ('jefe@prueba.cl',           'Pedro',  'Ramirez',   'CLIENT', 'jefe_terreno'),
            ('aac@prueba.cl',            'Carlos', 'Espinoza',  'CLIENT', 'aac'),
        ]

        for email, first, last, actor_type, role_code in usuarios:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': first,
                    'last_name':  last,
                    'actor_type': actor_type,
                    'is_active':  True,
                }
            )
            if created:
                user.set_password('prueba1234')
                user.save()

            CompanyMembership.objects.get_or_create(
                user=user,
                company=company,
                defaults={
                    'membership_type': 'CLIENT_SITE',
                    'is_active':       True,
                }
            )

            # Actualizar rol si ya existia con uno distinto
            membership, _ = SiteMembership.objects.get_or_create(
                user=user,
                site=site,
                defaults={
                    'role':        roles[role_code],
                    'is_active':   True,
                    'can_operate': True,
                }
            )
            if membership.role != roles[role_code]:
                membership.role = roles[role_code]
                membership.save()

            self.stdout.write(f'  {role_code}: {email} / prueba1234')

        # ── 5. CATEGORIAS DE RECURSO ───────────────────────────────────────────
        cat_person, _ = ResourceCategory.objects.get_or_create(
            code='PERSON',
            defaults={
                'name':          'Persona',
                'resource_type': 'PERSON',
                'is_active':     True,
            }
        )

        # ── 6. CARGOS LABORALES ────────────────────────────────────────────────
        cargos_data = ['Albanil', 'Ayudante', 'Capataz', 'Gasfiter', 'Electricista']
        cargos = {}
        for cargo_name in cargos_data:
            cargo, _ = JobTitle.objects.get_or_create(
                company=company,
                name=cargo_name,
                defaults={'resource_type': 'PERSON', 'is_active': True}
            )
            cargos[cargo_name] = cargo

        # ── 7. TRABAJADORES ────────────────────────────────────────────────────
        trabajadores_data = [
            ('Carlos',  'Rojas',    '12.345.678-9', 'Albanil'),
            ('Pedro',   'Soto',     '13.456.789-0', 'Albanil'),
            ('Mario',   'Fuentes',  '14.567.890-1', 'Ayudante'),
            ('Luis',    'Herrera',  '15.678.901-2', 'Capataz'),
            ('Jorge',   'Mendez',   '16.789.012-3', 'Ayudante'),
            ('Roberto', 'Castillo', '17.890.123-4', 'Gasfiter'),
            ('Felipe',  'Morales',  '18.901.234-5', 'Electricista'),
        ]
        for nombre, apellido, rut, cargo_name in trabajadores_data:
            resource, _ = Resource.objects.get_or_create(
                company=company,
                person_rut=rut,
                defaults={
                    'display_name':    f'{nombre} {apellido}',
                    'normalized_name': f'{nombre} {apellido}'.lower(),
                    'resource_category': cat_person,
                    'job_title':       cargos[cargo_name],
                    'status':          'ACTIVE',
                    'is_trackable':    True,
                }
            )
            ResourceSiteAssignment.objects.get_or_create(
                resource=resource,
                site=site,
                status='ACTIVE',
                defaults={
                    'assignment_type': 'PRIMARY',
                    'started_at':      timezone.now(),
                }
            )
        self.stdout.write('  7 trabajadores OK')

        # ── 8. ETAPAS Y PARTIDAS ───────────────────────────────────────────────
        etapas_data = [
            {
                'code': 'TERMINACIONES',
                'name': 'Terminaciones',
                'type': 'NORMAL',
                'partidas': [
                    ('YESO-INT',       'Yeso interior',         'NORMAL',    'm2'),
                    ('PORCEL-PISO',    'Porcelanato piso',      'NORMAL',    'm2'),
                    ('TABLERO-CONTRA', 'Tablero contrachapado', 'NORMAL',    'm2'),
                ]
            },
            {
                'code': 'OBRA-GRUESA',
                'name': 'Obra gruesa',
                'type': 'NORMAL',
                'partidas': [
                    ('CUBIERTA', 'Cubierta',               'HIGH_RISK', 'm2'),
                    ('LOSAS',    'Losas',                  'HIGH_RISK', 'm3'),
                    ('RELLENOS', 'Rellenos estabilizados', 'NORMAL',    'm3'),
                ]
            },
            {
                'code': 'OTRAS',
                'name': 'Otras',
                'type': 'NORMAL',
                'partidas': [
                    ('ORDEN-ASEO',   'Orden y aseo',           'NORMAL', 'gl'),
                    ('TRASLADO-MAT', 'Traslado de materiales',  'NORMAL', 'gl'),
                ]
            },
            {
                'code': 'REPROCESOS',
                'name': 'Reprocesos',
                'type': 'REPROCESS',
                'partidas': []
            },
        ]

        for etapa_data in etapas_data:
            stage, _ = Stage.objects.get_or_create(
                company=company,
                site=site,
                code=etapa_data['code'],
                defaults={
                    'name':        etapa_data['name'],
                    'stage_type':  etapa_data['type'],
                    'is_active':   True,
                    'is_reserved': etapa_data['type'] in ['REPROCESS', 'RESERVED'],
                }
            )
            for p_code, p_name, p_risk, p_um in etapa_data['partidas']:
                task, _ = TaskCatalog.objects.get_or_create(
                    company=company,
                    code=p_code,
                    defaults={
                        'name':       p_name,
                        'risk_level': p_risk,
                        'status':     'ACTIVE',
                        'default_um': p_um,
                    }
                )
                StageTask.objects.get_or_create(
                    site=site,
                    stage=stage,
                    task=task,
                    defaults={'is_active': True}
                )

        self.stdout.write('  Etapas y partidas OK')

        self.stdout.write(self.style.SUCCESS('\nDatos de prueba cargados correctamente.'))
        self.stdout.write(self.style.SUCCESS('  supervisor@prueba.cl      / prueba1234  → Supervisor'))
        self.stdout.write(self.style.SUCCESS('  administrativo@prueba.cl  / prueba1234  → Administrativo'))
        self.stdout.write(self.style.SUCCESS('  jefe@prueba.cl            / prueba1234  → Jefe de terreno'))
        self.stdout.write(self.style.SUCCESS('  aac@prueba.cl             / prueba1234  → Administrador A&C'))
