# -*- coding: utf-8 -*-
"""
Comando para migrar sesiones historicas desde el Excel del Sheet a Django.

Uso:
    python manage.py migrate_sessions --file ruta/al/archivo.xlsx --site-id 3

Requisitos antes de correr:
    1. Etapas y partidas cargadas para la obra (via pantalla de partidas)
    2. Trabajadores cargados para la obra (via carga masiva)
    3. Usuarios supervisores creados con sus emails

El comando busca trabajadores por RUT, etapas por nombre y partidas por nombre.
No duplica sesiones si ya existe una con el mismo sesion_id original en notes.
"""
import pandas as pd
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import transaction
import pytz


class Command(BaseCommand):
    help = 'Migra sesiones historicas desde Excel del Sheet a Django'

    def add_arguments(self, parser):
        parser.add_argument('--file',    required=True, help='Ruta al archivo Excel')
        parser.add_argument('--site-id', required=True, type=int, help='ID de la obra en Django')
        parser.add_argument('--dry-run', action='store_true',
                            help='Simular sin guardar nada')

    def handle(self, *args, **options):
        from companies.models import Site
        from resources.models import Resource, ResourceSiteAssignment
        from work.models import Stage, TaskCatalog, StageTask, WorkSession
        from django.contrib.auth import get_user_model
        User = get_user_model()

        file_path = options['file']
        site_id   = options['site_id']
        dry_run   = options['dry_run']

        # Cargar obra
        try:
            site = Site.objects.get(id=site_id)
        except Site.DoesNotExist:
            raise CommandError(f'No existe obra con id={site_id}')

        self.stdout.write(f'Obra: {site.name} ({site.company.name})')
        site_tz = pytz.timezone(site.timezone or 'America/Santiago')

        # Cargar Excel
        try:
            df = pd.read_excel(file_path, sheet_name='Sesiones')
        except Exception:
            try:
                df = pd.read_excel(file_path)
            except Exception as e:
                raise CommandError(f'Error al leer el archivo: {e}')

        self.stdout.write(f'Sesiones en archivo: {len(df)}')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no se guardará nada'))

        # ── Cachés para evitar queries repetidas ──────────────────────────────
        # Trabajadores por RUT
        resource_cache = {}
        for r in Resource.objects.filter(company=site.company):
            if r.person_rut:
                resource_cache[r.person_rut.upper()] = r
            if r.license_plate:
                resource_cache[r.license_plate.upper()] = r
            if r.internal_code:
                resource_cache[r.internal_code.upper()] = r

        # Asignaciones activas por resource_id
        assignment_cache = {}
        for a in ResourceSiteAssignment.objects.filter(site=site, status='ACTIVE'):
            assignment_cache[a.resource_id] = a

        # Etapas por nombre (normalizado)
        stage_cache = {}
        for s in Stage.objects.filter(site=site, is_active=True):
            stage_cache[s.name.strip().lower()] = s

        # StageTask por (stage_id, task_name normalizado)
        stagetask_cache = {}
        for st in StageTask.objects.filter(site=site).select_related('stage', 'task'):
            key = (st.stage_id, st.task.name.strip().lower())
            stagetask_cache[key] = st

        # Usuarios por email
        user_cache = {}
        for u in User.objects.all():
            user_cache[u.email.lower()] = u

        # IDs de sesiones ya migradas (para evitar duplicados)
        migrated_ids = set(
            WorkSession.objects.filter(
                site=site,
                notes__startswith='migrado:'
            ).values_list('notes', flat=True)
        )
        migrated_ids = {n.replace('migrado:', '').strip() for n in migrated_ids}

        # ── Procesar filas ────────────────────────────────────────────────────
        created  = 0
        skipped  = 0
        errors   = []

        def normalize_rut(rut_str):
            if not rut_str:
                return None
            clean = str(rut_str).replace('.', '').replace(' ', '').upper().strip()
            if '-' in clean:
                parts = clean.split('-')
                return f'{parts[0]}-{parts[1]}'
            if len(clean) >= 2:
                return f'{clean[:-1]}-{clean[-1]}'
            return clean

        for i, row in df.iterrows():
            linea = i + 2

            # Estado — solo migrar terminadas
            estado = str(row.get('estado', '') or '').strip().lower()
            if estado not in ('terminado', 'closed', 'cerrado', 'cerrada_auto', 'auto_closed'):
                skipped += 1
                continue

            # ID original para evitar duplicados
            sesion_id_original = str(row.get('sesion_id', '') or '').strip()
            if sesion_id_original and sesion_id_original in migrated_ids:
                skipped += 1
                continue

            # RUT del trabajador
            rut_raw = str(row.get('rut', '') or '').strip().upper()
            rut     = rut_raw  # usar tal cual, sin normalizar
            # Solo normalizar si parece RUT (solo números y K con guión o sin)
            import re
            if re.match(r'^\d{6,8}[kK-]?\d?$', rut_raw.replace('-', '').replace('.', '')):
                rut = normalize_rut(rut_raw)
            if not rut:
                errors.append(f'Fila {linea}: RUT vacío')
                continue

            resource = resource_cache.get(rut.upper())
            if not resource:
                errors.append(f'Fila {linea}: Trabajador con RUT {rut} no encontrado en la obra')
                continue

            # Etapa
            etapa_nombre = str(row.get('etapa', '') or '').strip()
            stage = stage_cache.get(etapa_nombre.strip().lower())
            if not stage:
                errors.append(f'Fila {linea}: Etapa "{etapa_nombre}" no encontrada')
                continue

            # Partida desde partida_cod (subetapa|partida o solo partida)
            partida_cod = str(row.get('partida_cod', '') or '').strip()
            if '|' in partida_cod:
                partida_nombre = partida_cod.split('|')[1].strip()
            else:
                partida_nombre = partida_cod.strip()

            st_key    = (stage.id, partida_nombre.lower())
            stage_task = stagetask_cache.get(st_key)
            if not stage_task:
                errors.append(f'Fila {linea}: Partida "{partida_nombre}" no encontrada en etapa "{etapa_nombre}"')
                continue

            task = stage_task.task

            # Timestamps
            try:
                inicio_at = pd.to_datetime(row['inicio_at'])
                if inicio_at.tzinfo is None:
                    inicio_at = site_tz.localize(inicio_at)
                inicio_at = inicio_at.astimezone(pytz.utc)
            except Exception:
                errors.append(f'Fila {linea}: Fecha inicio inválida')
                continue

            # fin_at: usar directo si existe, sino calcular desde duracion_min
            try:
                fin_at = pd.to_datetime(row.get('fin_at'))
                if pd.isna(fin_at):
                    raise ValueError
                if fin_at.tzinfo is None:
                    fin_at = site_tz.localize(fin_at)
                fin_at = fin_at.astimezone(pytz.utc)
            except Exception:
                dur_min = row.get('duracion_min')
                if dur_min and not pd.isna(dur_min):
                    fin_at = inicio_at + timedelta(minutes=float(dur_min))
                else:
                    errors.append(f'Fila {linea}: Sin fecha fin ni duración')
                    continue

            # Duración en minutos
            duration_minutes = int((fin_at - inicio_at).total_seconds() / 60)
            if duration_minutes < 0:
                errors.append(f'Fila {linea}: Duración negativa, se omite')
                continue

            # Supervisor por email
            inicio_email = str(row.get('inicio_email', '') or '').strip().lower()
            supervisor   = user_cache.get(inicio_email)
            # Si no hay supervisor, usar el primer usuario prestador disponible
            if not supervisor:
                supervisor = user_cache.get(list(user_cache.keys())[0]) if user_cache else None

            # Asignación
            assignment = assignment_cache.get(resource.id)

            # Hora extra
            es_hora_extra = False
            he_val = row.get('es_hora_extra')
            if he_val and not pd.isna(he_val):
                es_hora_extra = str(he_val).strip().lower() in ('true', '1', 'si', 'sí', 'yes')

            if not dry_run:
                try:
                    with transaction.atomic():
                        WorkSession.objects.create(
                            company=site.company,
                            site=site,
                            resource=resource,
                            resource_assignment=assignment,
                            stage=stage,
                            task=task,
                            stage_name_snapshot=stage.name,
                            task_code_snapshot=task.code,
                            task_name_snapshot=task.name,
                            risk_level_snapshot=task.risk_level,
                            started_at=inicio_at,
                            ended_at=fin_at,
                            duration_minutes=duration_minutes,
                            status='CLOSED',
                            closure_origin='AUTO_CLOSE' if estado in ('cerrada_auto', 'auto_closed') else 'MANUAL',
                            started_by=supervisor or User.objects.filter(
                                actor_type='PROVIDER'
                            ).first(),
                            ended_by=supervisor,
                            responsible_supervisor=supervisor,
                            is_overtime=es_hora_extra,
                            notes=f'migrado:{sesion_id_original}' if sesion_id_original else 'migrado:sheet',
                        )
                        created += 1
                except Exception as e:
                    errors.append(f'Fila {linea}: {e}')
            else:
                created += 1

        # ── Resumen ───────────────────────────────────────────────────────────
        self.stdout.write('')
        if dry_run:
            self.stdout.write(self.style.WARNING(f'DRY RUN — se crearían {created} sesiones'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Sesiones migradas: {created}'))

        self.stdout.write(f'Omitidas (no terminadas o ya migradas): {skipped}')

        if errors:
            self.stdout.write(self.style.WARNING(f'\n{len(errors)} errores:'))
            for err in errors[:20]:
                self.stdout.write(f'  {err}')
            if len(errors) > 20:
                self.stdout.write(f'  ... y {len(errors) - 20} más')
        else:
            self.stdout.write(self.style.SUCCESS('Sin errores.'))
