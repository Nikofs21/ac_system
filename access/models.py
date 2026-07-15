# -*- coding: utf-8 -*-
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.conf import settings


class ActorType(models.TextChoices):
    PROVIDER = 'PROVIDER', 'Prestador'
    CLIENT = 'CLIENT', 'Cliente'


class UserManager(BaseUserManager):

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('El email es obligatorio')
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('actor_type', ActorType.PROVIDER)
        extra_fields.setdefault('is_novus_super', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):

    email = models.EmailField(max_length=254, unique=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    actor_type = models.CharField(
        max_length=20,
        choices=ActorType.choices,
        default=ActorType.CLIENT
    )
    rut = models.CharField(max_length=20, blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_novus_super = models.BooleanField(
        default=False,
        help_text=(
            'Acceso total al sistema: todas las empresas y obras, sin excepcion. '
            'Es independiente de membresias (CompanyMembership/SiteMembership) y se '
            'otorga automaticamente en cada empresa/obra nueva via signals. '
            'Otorgar solo a personal interno de Novus de maxima confianza.'
        )
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        db_table = 'access_user'
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return f'{self.first_name} {self.last_name} ({self.email})'

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'


class UserPreference(models.Model):

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='preference'
    )
    last_company = models.ForeignKey(
        'companies.Company',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='last_active_users'
    )
    last_site = models.ForeignKey(
        'companies.Site',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='last_active_users'
    )
    timezone = models.CharField(max_length=64, default='America/Santiago')
    extra_json = models.JSONField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'access_user_preference'
        verbose_name = 'Preferencia de usuario'
        verbose_name_plural = 'Preferencias de usuario'

    def __str__(self):
        return f'Preferencias de {self.user.get_full_name()}'


class Role(models.Model):

    class ScopeType(models.TextChoices):
        GLOBAL_BASE = 'GLOBAL_BASE', 'Base global'
        COMPANY_CUSTOM = 'COMPANY_CUSTOM', 'Custom por empresa'

    name = models.CharField(max_length=120)
    code = models.CharField(max_length=80, unique=True)
    scope_type = models.CharField(
        max_length=20,
        choices=ScopeType.choices,
        default=ScopeType.GLOBAL_BASE
    )
    company = models.ForeignKey(
        'companies.Company',
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='custom_roles'
    )
    is_active = models.BooleanField(default=True)
    is_protected = models.BooleanField(
        default=False,
        help_text=(
            'Rol protegido del sistema (ej: novus_super, novus_consultor). '
            'Sus permisos no pueden modificarse desde la UI de gestion de roles.'
        )
    )
    description = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='roles_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'access_role'
        verbose_name = 'Rol'
        verbose_name_plural = 'Roles'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.code})'


class Permission(models.Model):

    class Module(models.TextChoices):
        OPERACION = 'OPERACION', 'Operacion'
        RECURSOS = 'RECURSOS', 'Recursos'
        SUBCONTRATOS = 'SUBCONTRATOS', 'Subcontratos'
        CONFIGURACION = 'CONFIGURACION', 'Configuracion'
        CONFIGURACION_ESTRUCTURAL = 'CONFIGURACION_ESTRUCTURAL', 'Configuracion estructural'
        USUARIOS = 'USUARIOS', 'Usuarios y roles'
        DASHBOARDS = 'DASHBOARDS', 'Dashboards y reportes'
        ASISTENCIA = 'ASISTENCIA', 'Asistencia y remuneraciones'
        PLANIFICACION = 'PLANIFICACION', 'Planificacion y avance'
        ORGANIGRAMA = 'ORGANIGRAMA', 'Organigrama'

    class Level(models.TextChoices):
        VIEW = 'VIEW', 'Ver'
        OPERATE = 'OPERATE', 'Operar'
        ADMIN = 'ADMIN', 'Administrar'
        SENSITIVE = 'SENSITIVE', 'Accion sensible'

    module = models.CharField(max_length=40, choices=Module.choices)
    code = models.CharField(max_length=120, unique=True)
    name = models.CharField(max_length=180)
    level = models.CharField(max_length=20, choices=Level.choices)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'access_permission'
        verbose_name = 'Permiso'
        verbose_name_plural = 'Permisos'
        ordering = ['module', 'level']

    def __str__(self):
        return f'{self.module} - {self.name}'


class RolePermission(models.Model):

    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name='role_permissions'
    )
    permission = models.ForeignKey(
        Permission,
        on_delete=models.CASCADE,
        related_name='role_permissions'
    )
    granted = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'access_role_permission'
        verbose_name = 'Permiso de rol'
        verbose_name_plural = 'Permisos de rol'
        constraints = [
            models.UniqueConstraint(
                fields=['role', 'permission'],
                name='unique_role_permission'
            )
        ]

    def __str__(self):
        return f'{self.role.name} - {self.permission.name}'


class SiteMembershipPermissionOverride(models.Model):
    """
    Sobrescribe permisos del rol estandar para un usuario especifico en una obra.

    granted=True  → agrega el permiso aunque el rol no lo tenga
    granted=False → quita el permiso aunque el rol lo tenga

    Solo el prestador puede crear/editar estos overrides.
    """
    site_membership = models.ForeignKey(
        'companies.SiteMembership',
        on_delete=models.CASCADE,
        related_name='permission_overrides',
    )
    permission = models.ForeignKey(
        'access.Permission',
        on_delete=models.CASCADE,
        related_name='membership_overrides',
    )
    granted = models.BooleanField(
        help_text='True = agregar permiso, False = quitar permiso'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='permission_overrides_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'access_membership_permission_override'
        verbose_name = 'Override de permiso por membresia'
        verbose_name_plural = 'Overrides de permiso por membresia'
        constraints = [
            models.UniqueConstraint(
                fields=['site_membership', 'permission'],
                name='unique_override_per_membership_permission'
            )
        ]

    def __str__(self):
        action = 'AGREGA' if self.granted else 'QUITA'
        return f'{action} {self.permission.code} → {self.site_membership}'


class ManagementTitle(models.Model):
    """
    Sub-cargo de Gerencia (Gerente de proyecto, Gerente de operaciones,
    Gerente general, etc.). Scope por empresa, igual que resources.JobTitle
    para trabajadores — cada empresa arma su propia lista y puede agregar
    cargos nuevos desde la pantalla de gestion de Gerencia/Admin obra.

    Solo aplica al rol 'gerencia'. 'admin_obra' y 'aac' no usan sub-cargo.
    """
    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='management_titles',
    )
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'access_management_title'
        verbose_name = 'Cargo de gerencia'
        verbose_name_plural = 'Cargos de gerencia'
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'name'],
                name='unique_management_title_per_company',
            )
        ]

    def __str__(self):
        return f'{self.name} — {self.company.name}'

    @classmethod
    def for_company(cls, company):
        return cls.objects.filter(company=company, is_active=True).order_by('name')
