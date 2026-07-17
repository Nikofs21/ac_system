# Generated manually — corrige RUTs existentes sin normalizar

from django.db import migrations


def normalize_existing_ruts(apps, schema_editor):
    Resource = apps.get_model('resources', 'Resource')

    def normalize(rut_str):
        if not rut_str:
            return rut_str
        clean = rut_str.replace('.', '').replace(' ', '').upper()
        if '-' in clean:
            parts = clean.split('-')
            return f'{parts[0]}-{parts[1]}'
        if len(clean) >= 2:
            return f'{clean[:-1]}-{clean[-1]}'
        return clean

    updated = 0
    for resource in Resource.objects.exclude(person_rut__isnull=True).exclude(person_rut__exact=''):
        normalized = normalize(resource.person_rut)
        if normalized != resource.person_rut:
            resource.person_rut = normalized
            resource.save(update_fields=['person_rut'])
            updated += 1

    if updated:
        print(f'  {updated} RUT(s) renormalizados.')


def noop_reverse(apps, schema_editor):
    pass  # no tiene sentido "desnormalizar" — es una limpieza de datos, no reversible


class Migration(migrations.Migration):

    dependencies = [
        ('resources', '0003_remove_jobtitle_unique_job_title_per_company'),
    ]

    operations = [
        migrations.RunPython(normalize_existing_ruts, noop_reverse),
    ]
