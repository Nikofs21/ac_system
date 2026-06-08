# -*- coding: utf-8 -*-
"""
Comando para sembrar feriados nacionales de Chile.
Uso: python manage.py seed_holidays
     python manage.py seed_holidays --year 2027

Siembra feriados fijos para el año actual y siguiente.
Los feriados variables (Semana Santa) se calculan automaticamente.
Idempotente: puede correrse multiples veces sin duplicar.
"""
from datetime import date
from django.core.management.base import BaseCommand
from work.models import ChilePublicHoliday


def easter_date(year):
    """Calcula la fecha de Pascua (algoritmo de Butcher)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day   = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def get_fixed_holidays(year):
    """Feriados fijos que se repiten cada año."""
    return [
        (date(year,  1,  1), 'Año Nuevo'),
        (date(year,  5,  1), 'Día del Trabajo'),
        (date(year,  5, 21), 'Día de las Glorias Navales'),
        (date(year,  6, 20), 'Día Nacional de los Pueblos Indígenas'),
        (date(year,  6, 29), 'San Pedro y San Pablo'),
        (date(year,  7, 16), 'Día de la Virgen del Carmen'),
        (date(year,  8, 15), 'Asunción de la Virgen'),
        (date(year,  9, 18), 'Fiestas Patrias — Independencia'),
        (date(year,  9, 19), 'Fiestas Patrias — Glorias del Ejército'),
        (date(year, 10, 12), 'Encuentro de Dos Mundos'),
        (date(year, 10, 31), 'Día de las Iglesias Evangélicas y Protestantes'),
        (date(year, 11,  1), 'Día de Todos los Santos'),
        (date(year, 12,  8), 'Inmaculada Concepción'),
        (date(year, 12, 25), 'Navidad'),
        (date(year, 12, 31), 'Víspera de Año Nuevo'),
    ]


def get_variable_holidays(year):
    """Feriados variables basados en fecha de Pascua."""
    easter = easter_date(year)
    from datetime import timedelta
    return [
        (easter - timedelta(days=2), 'Viernes Santo'),
        (easter - timedelta(days=1), 'Sábado Santo'),
    ]


class Command(BaseCommand):
    help = 'Siembra feriados nacionales de Chile para el año actual y siguiente'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year', type=int, default=None,
            help='Año específico a sembrar (por defecto: año actual y siguiente)'
        )

    def handle(self, *args, **options):
        from django.utils import timezone
        current_year = timezone.now().year

        if options['year']:
            years = [options['year']]
        else:
            years = [current_year, current_year + 1]

        total_created = 0
        total_updated = 0

        for year in years:
            self.stdout.write(f'\nSembrando feriados {year}...')
            created, updated = self._seed_year(year)
            total_created += created
            total_updated += updated
            self.stdout.write(f'  {created} creados, {updated} ya existían.')

        self.stdout.write(self.style.SUCCESS(
            f'\nFeriados sembrados: {total_created} nuevos, {total_updated} existentes.'
        ))

    def _seed_year(self, year):
        created = 0
        updated = 0

        fixed    = [(d, name, True)  for d, name in get_fixed_holidays(year)]
        variable = [(d, name, False) for d, name in get_variable_holidays(year)]

        for holiday_date, name, is_recurring in fixed + variable:
            obj, was_created = ChilePublicHoliday.objects.update_or_create(
                date=holiday_date,
                defaults={
                    'name':         name,
                    'year':         year,
                    'is_recurring': is_recurring,
                }
            )
            if was_created:
                created += 1
                self.stdout.write(f'  + {holiday_date} — {name}')
            else:
                updated += 1

        return created, updated
