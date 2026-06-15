import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ac_system.settings')
django.setup()

from resources.models import Resource, ResourceSiteAssignment
from django.db.models import Count

site_id = 2

# Eliminar todas las asignaciones a la obra
deleted_a, _ = ResourceSiteAssignment.objects.filter(site_id=site_id).delete()
print(f'Asignaciones eliminadas: {deleted_a}')

# Eliminar recursos que no tienen asignaciones en ninguna otra obra
huerfanos = Resource.objects.annotate(
    total=Count('site_assignments')
).filter(total=0)
count = huerfanos.count()
huerfanos.delete()
print(f'Recursos eliminados: {count}')
print('Listo.')