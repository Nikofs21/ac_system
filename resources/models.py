# -*- coding: utf-8 -*-
import uuid
from django.db import models
from django.conf import settings


class ResourceCategory(models.Model):

    class ResourceType(models.TextChoices):
        PERSON   = 'PERSON',   'Persona'
        MACHINERY = 'MACHINERY', 'Maquinaria'

    code          = models.CharField(max_length=40, unique=True)
    name          = models.CharField(max_length=80)
    resource_type = models.CharField(max_length=20, choices=ResourceType.choices)
    is_active     = models.BooleanField(default=True)

    class Meta:
        db_table  = 'resources_resource_category'
        verbose_name = 'Categoria de recurso'
        verbose_name_plural = 'Categorias de recurso'
        ordering  = ['resource_type', 'name']

    def __str__(self):
        return f'{self.name} ({self.code})'


class JobTitle(models.Model):
    """
    Cargo laboral u tipo de maquinaria.

    Scope:
    - Si site es None  → cargo de empresa, visible en todas las obras
    - Si site tiene valor → cargo exclusivo de esa obra
    El prestador puede crear cargos de empresa al configurar la obra inicial.
    La obra puede crear cargos propios desde el formulario de recursos.
    """

    class ResourceType(models.TextChoices):
        PERSON    = 'PERSON',    'Persona'
        MACHINERY = 'MACHINERY', 'Maquinaria'
        BOTH      = 'BOTH',      'Ambos'

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='job_titles',
    )
    site = models.ForeignKey(
        'companies.Site',
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='job_titles',
    )
    name          = models.CharField(max_length=120)
    code          = models.CharField(max_length=40, blank=True, null=True)
    resource_type = models.CharField(
        max_length=20,
        choices=ResourceType.choices,
        default=ResourceType.PERSON,
    )
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table  = 'resources_job_title'
        verbose_name = 'Cargo laboral'
        verbose_name_plural = 'Cargos laborales'
        ordering  = ['company', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'site', 'name'],
                name='unique_job_title_per_company_site',
            )
        ]

    def __str__(self):
        scope = self.site.name if self.site else self.company.name
        return f'{self.name} — {scope}'

    @classmethod
    def for_site(cls, site):
        """
        Retorna los cargos disponibles para una obra:
        cargos de empresa (site=None) + cargos propios de la obra.
        """
        return cls.objects.filter(
            company=site.company,
            is_active=True,
        ).filter(
            models.Q(site__isnull=True) | models.Q(site=site)
        ).order_by('name')


class Resource(models.Model):

    class Status(models.TextChoices):
        ACTIVE   = 'ACTIVE',   'Activo'
        INACTIVE = 'INACTIVE', 'Inactivo'
        ARCHIVED = 'ARCHIVED', 'Archivado'

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.PROTECT,
        related_name='resources',
    )
    resource_uid = models.CharField(max_length=64, unique=True, editable=False)
    resource_category = models.ForeignKey(
        ResourceCategory,
        on_delete=models.PROTECT,
        related_name='resources',
    )
    status       = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    display_name = models.CharField(max_length=180)
    normalized_name = models.CharField(max_length=180, blank=True)
    person_rut   = models.CharField(max_length=20, blank=True, null=True)
    license_plate = models.CharField(max_length=20, blank=True, null=True)
    internal_code = models.CharField(max_length=60, blank=True, null=True)
    job_title    = models.ForeignKey(
        JobTitle,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='resources',
    )
    is_trackable = models.BooleanField(default=True)
    last_partida_cod       = models.CharField(max_length=120, blank=True, null=True)
    last_partida_updated_at = models.DateTimeField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)
    created_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='resources_created',
    )
    updated_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='resources_updated',
    )

    class Meta:
        db_table  = 'resources_resource'
        verbose_name = 'Recurso'
        verbose_name_plural = 'Recursos'
        ordering  = ['company', 'display_name']

    def save(self, *args, **kwargs):
        if not self.resource_uid:
            self.resource_uid = str(uuid.uuid4()).replace('-', '')
        if not self.normalized_name:
            self.normalized_name = self.display_name.lower().strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.display_name} ({self.company.name})'

    def get_qr_url(self):
        return f'/r/{self.resource_uid}/'

    @staticmethod
    def normalize_rut(rut_str):
        """
        Normaliza un RUT al formato estándar: sin puntos, con guión.
        Ejemplos:
          '12.345.678-9' → '12345678-9'
          '12345678-9'   → '12345678-9'
          '123456789'    → '12345678-9'  (asume ultimo char es DV)
          '12345678K'    → '12345678-K'
        """
        if not rut_str:
            return rut_str
        # Quitar puntos y espacios
        clean = rut_str.replace('.', '').replace(' ', '').upper()
        # Si ya tiene guión, retornar limpio
        if '-' in clean:
            parts = clean.split('-')
            return f'{parts[0]}-{parts[1]}'
        # Sin guión: separar DV (último caracter)
        if len(clean) >= 2:
            return f'{clean[:-1]}-{clean[-1]}'
        return clean


class ResourceSiteAssignment(models.Model):

    class AssignmentType(models.TextChoices):
        PRIMARY   = 'PRIMARY',   'Principal'
        LOAN      = 'LOAN',      'Prestamo'
        TEMPORARY = 'TEMPORARY', 'Temporal'

    class Status(models.TextChoices):
        ACTIVE    = 'ACTIVE',    'Activa'
        ENDED     = 'ENDED',     'Terminada'
        CANCELLED = 'CANCELLED', 'Cancelada'

    resource = models.ForeignKey(
        Resource,
        on_delete=models.PROTECT,
        related_name='site_assignments',
    )
    site = models.ForeignKey(
        'companies.Site',
        on_delete=models.PROTECT,
        related_name='resource_assignments',
    )
    assignment_type = models.CharField(
        max_length=20,
        choices=AssignmentType.choices,
        default=AssignmentType.PRIMARY,
    )
    status     = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    started_at = models.DateTimeField()
    ended_at   = models.DateTimeField(null=True, blank=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='assignments_made',
    )
    notes      = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table  = 'resources_resource_site_assignment'
        verbose_name = 'Asignacion de recurso a obra'
        verbose_name_plural = 'Asignaciones de recurso a obra'
        ordering  = ['-started_at']
        constraints = [
            models.UniqueConstraint(
                fields=['resource'],
                condition=models.Q(status='ACTIVE'),
                name='unique_active_assignment_per_resource',
            )
        ]

    def __str__(self):
        return f'{self.resource.display_name} → {self.site.name} ({self.assignment_type})'
