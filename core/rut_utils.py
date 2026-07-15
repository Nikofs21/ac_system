# -*- coding: utf-8 -*-
"""
Verificacion de unicidad de RUT a nivel de sistema.

Un mismo RUT no puede repetirse en el sistema sin importar:
- el cargo/rol que tenga (jornal, gerencia, admin, etc.)
- si corresponde a un usuario con acceso al sistema (access.User — p.ej.
  gerencia/MOI) o a un trabajador/maquinaria en terreno (resources.Resource)
- la empresa a la que pertenezca, sea cliente o prestador

Se asume que el RUT ya viene normalizado (sin puntos, con guion) antes de
llamar a esta funcion — cada modulo ya tiene su propio normalize_rut /
_normalize_rut y no se toca esa logica existente aqui.
"""


def find_rut_conflict(rut, exclude_user_id=None, exclude_resource_id=None):
    """
    Busca si el RUT ya esta en uso en cualquier parte del sistema.

    Retorna un mensaje describiendo el conflicto (listo para mostrar en un
    formulario) o None si el RUT esta libre.
    """
    if not rut:
        return None

    from access.models import User
    from resources.models import Resource

    user_qs = User.objects.filter(rut=rut)
    if exclude_user_id:
        user_qs = user_qs.exclude(id=exclude_user_id)
    existing_user = user_qs.first()
    if existing_user:
        return (
            f'El RUT {rut} ya esta registrado para el usuario '
            f'{existing_user.get_full_name()} ({existing_user.email}).'
        )

    resource_qs = Resource.objects.filter(
        person_rut=rut
    ).exclude(status='ARCHIVED')
    if exclude_resource_id:
        resource_qs = resource_qs.exclude(id=exclude_resource_id)
    existing_resource = resource_qs.select_related('company').first()
    if existing_resource:
        return (
            f'El RUT {rut} ya esta registrado como trabajador/maquinaria '
            f'"{existing_resource.display_name}" en {existing_resource.company.name}.'
        )

    return None
