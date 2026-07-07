# -*- coding: utf-8 -*-
"""
Comando para generar (backfill) los DailyProductivitySnapshot de dias
historicos que quedaron sin generar.

Caso tipico: una obra con sesiones migradas desde el Sheet via
core.management.commands.migrate_sessions (WorkSession con status=CLOSED
y fechas reales), pero sin fila en analytics_daily_productivity_snapshot
para esos dias — porque ese comando migra sesiones, no snapshots.

En operacion normal los snapshots se generan solos: work/tasks.py
(auto_close_sessions_task) dispara analytics.tasks.generate_daily_snapshot_task
apenas se cierra el dia de una obra. Este comando cubre unicamente los dias
que ese disparador automatico nunca vio (dias anteriores a la migracion,
o a que este modulo se activara para la obra).

Usa la misma funcion (analytics.calculator.calculate_daily_data) y el mismo
update_or_create que la tarea de Celery — no duplica logica de calculo.

Uso:
    python manage.py backfill_daily_snapshots --site-id 3
    python manage.py backfill_daily_snapshots --site-id 3 --from-date 2026-01-01 --to-date 2026-06-30
    python manage.py backfill_daily_snapshots --site-id 3 --dry-run
    python manage.py backfill_daily_snapshots --site-id 3 --force

Por defecto:
- Si no se indica --from-date, se usa la fecha de la WorkSession mas
  antigua de la obra (solo para acotar el rango a recorrer).
- Si no se indica --to-date, se usa ayer. El dia de hoy nunca se genera
  aca: la vista lo calcula al vuelo, igual que cualquier dia en curso, y
  --to-date >= hoy se rechaza para no romper esa regla.
- Dias sin ninguna WorkSession cerrada (trab=0) se saltan y NO generan
  fila vacia — evita ensuciar el historial con dias sin actividad.
- Dias que ya tienen snapshot guardado NO se tocan, para respetar la
  inmutabilidad de dias pasados que ya establece el diseño del modulo.
  Usar --force para regenerarlos de todas formas (por ejemplo, si se
  corrigio algo en las sesiones migradas y hay que recalcular).
"""
from datetime import date as date_cls, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_date


class Command(BaseCommand):
    help = 'Genera DailyProductivitySnapshot para dias historicos que quedaron sin generar.'

    def add_arguments(self, parser):
        parser.add_argument('--site-id', required=True, type=int, help='ID de la obra')
        parser.add_argument('--from-date', help='Fecha inicial YYYY-MM-DD (default: sesion mas antigua de la obra)')
        parser.add_argument('--to-date', help='Fecha final YYYY-MM-DD (default: ayer)')
        parser.add_argument('--force', action='store_true',
                             help='Regenerar tambien los dias que ya tienen snapshot guardado')
        parser.add_argument('--dry-run', action='store_true', help='Simular sin guardar nada')

    def handle(self, *args, **options):
        from companies.models import Site
        from work.models import WorkSession
        from analytics.models import DailyProductivitySnapshot
        from analytics.calculator import calculate_daily_data

        site_id = options['site_id']
        force   = options['force']
        dry_run = options['dry_run']

        try:
            site = Site.objects.get(id=site_id)
        except Site.DoesNotExist:
            raise CommandError(f'No existe obra con id={site_id}')

        self.stdout.write(f'Obra: {site.name} ({site.company.name})')

        today = date_cls.today()

        from_date_str = options.get('from_date')
        to_date_str   = options.get('to_date')

        from_date = parse_date(from_date_str) if from_date_str else None
        if from_date_str and not from_date:
            raise CommandError('--from-date invalida, use YYYY-MM-DD')

        to_date = parse_date(to_date_str) if to_date_str else None
        if to_date_str and not to_date:
            raise CommandError('--to-date invalida, use YYYY-MM-DD')

        if not to_date:
            to_date = today - timedelta(days=1)
        if to_date >= today:
            raise CommandError(
                '--to-date debe ser anterior a hoy: el dia de hoy se calcula al vuelo '
                'en la vista y no se persiste en snapshots.'
            )

        if not from_date:
            primera_sesion = WorkSession.objects.filter(
                site=site, status__in=['CLOSED', 'AUTO_CLOSED'], ended_at__isnull=False,
            ).order_by('started_at').values_list('started_at', flat=True).first()

            if not primera_sesion:
                self.stdout.write(self.style.WARNING('La obra no tiene sesiones cerradas. Nada que generar.'))
                return

            from_date = primera_sesion.date()

        if from_date > to_date:
            raise CommandError('--from-date no puede ser posterior a --to-date')

        total_dias = (to_date - from_date).days + 1
        self.stdout.write(f'Rango: {from_date} a {to_date} ({total_dias} dias a revisar)')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no se guardara nada'))

        existentes = set(
            DailyProductivitySnapshot.objects.filter(
                site=site, date__gte=from_date, date__lte=to_date,
            ).values_list('date', flat=True)
        )

        creados = 0
        actualizados = 0
        saltados_ya_existe = 0
        saltados_sin_datos = 0

        fecha = from_date
        while fecha <= to_date:
            ya_existe = fecha in existentes

            if ya_existe and not force:
                saltados_ya_existe += 1
                fecha += timedelta(days=1)
                continue

            data = calculate_daily_data(site, fecha)

            if data['trab'] == 0:
                saltados_sin_datos += 1
                fecha += timedelta(days=1)
                continue

            if not dry_run:
                DailyProductivitySnapshot.objects.update_or_create(
                    site=site, date=fecha, defaults=data
                )

            if ya_existe:
                actualizados += 1
                etiqueta = 'regenerado'
            else:
                creados += 1
                etiqueta = 'creado'

            self.stdout.write(
                f'  {fecha} — trab={data["trab"]}, hh={data["hh"]}, icc={data["icc"]} ({etiqueta})'
            )

            fecha += timedelta(days=1)

        self.stdout.write('')
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'DRY RUN — se crearian {creados}, se regenerarian {actualizados}, '
                f'se saltarian {saltados_ya_existe} (ya existian) y {saltados_sin_datos} (sin sesiones)'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Snapshots creados: {creados}, regenerados: {actualizados}, '
                f'saltados (ya existian): {saltados_ya_existe}, saltados (sin sesiones): {saltados_sin_datos}'
            ))
