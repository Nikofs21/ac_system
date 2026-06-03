# Agregar esta funcion a core/permissions.py
# o crear core/task_permissions.py como modulo separado


def get_allowed_tasks_for_user(user, site):
    from work.models import TaskCatalog, SupervisorTaskPermission, StageTask
    from companies.models import SiteMembership

    base_qs = TaskCatalog.objects.filter(
        stage_tasks__site=site,
        stage_tasks__is_active=True,
        status='ACTIVE',
    ).distinct()

    try:
        membership = SiteMembership.objects.select_related('role').get(
            user=user, site=site, is_active=True,
        )
    except SiteMembership.DoesNotExist:
        if user.actor_type == 'PROVIDER':
            return base_qs
        return TaskCatalog.objects.none()

    role_code = membership.role.code if membership.role else ''

    # Roles con visión completa — no aplica ninguna restricción
    if role_code != 'supervisor':
        return base_qs

    # Partidas que este supervisor tiene permitidas explícitamente
    my_permitted_ids = SupervisorTaskPermission.objects.filter(
        site_membership=membership,
        is_active=True,
    ).values_list('task_id', flat=True)

    if my_permitted_ids:
        # Supervisor con restricciones — solo sus partidas
        return base_qs.filter(id__in=my_permitted_ids)

    # Supervisor sin restricciones — ver todo EXCEPTO
    # partidas reservadas para otro supervisor específico
    reserved_for_others = SupervisorTaskPermission.objects.filter(
        site_membership__site=site,
        site_membership__is_active=True,
        is_active=True,
    ).exclude(
        site_membership=membership,
    ).values_list('task_id', flat=True)

    return base_qs.exclude(id__in=reserved_for_others)


def get_allowed_tasks_for_subcontract(subcontract):
    """
    Retorna las partidas autorizadas para un subcontrato con su etapa reservada.

    Returns:
        QuerySet de SubcontractTaskAssignment activos con task y reserved_stage
    """
    from subcontracts.models import SubcontractTaskAssignment

    return SubcontractTaskAssignment.objects.filter(
        subcontract=subcontract,
        is_active=True,
    ).select_related('task', 'reserved_stage').order_by('reserved_stage__name', 'task__name')
