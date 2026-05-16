# -*- coding: utf-8 -*-
import uuid
from django.db import models
from django.conf import settings


class ResourceCategory(models.Model):

    class ResourceType(models.TextChoices):
        PERSON = 'PERSON', 'Persona'
        MACHINERY = 'MACHINERY', 'Maquinaria'

    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    resource_type = models.CharField(
        max_length=20,
        choices=ResourceType.choices
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'resources_resource_category'
        verbose_name = 'Categoria de recurso'
        verbose_name_plural = 'Categorias de recurso'
        ordering = ['resource_type', 'name']

    def __str__(self):
        return f'{self.name} ({self.code})'


class JobTitle(models.Model):

    class ResourceType(models.TextChoices):
        PERSON = 'PERSON', 'Persona'
        MACHINERY = 'MACHINERY', 'Maquinaria'
        BOTH = 'BOTH', 'Ambos'

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='job_titles'
    )
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=40, blank=True, null=True)
    resource_type = models.CharField(
        max_length=20,
        choices=ResourceType.choices,
        default=ResourceType.PERSON
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'resources_job_title'
        verbose_name = 'Cargo laboral'
        verbose_name_plural = 'Cargos laborales'
        ordering = ['company', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'name'],
                name='unique_job_title_per_company'
            )
        ]

    def __str__(self):
        return f'{self.name} - {self.company.name}'


class Resource(models.Model):

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Activo'
        INACTIVE = 'INACTIVE', 'Inactivo'
        ARCHIVED = 'ARCHIVED', 'Archivado'

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.PROTECT,
        related_name='resources'
    )
    resource_uid = models.CharField(
        max_length=64,
        unique=True,
        editable=False
    )
    resource_category = models.ForeignKey(
        ResourceCategory,
        on_delete=models.PROTECT,
        related_name='resources'
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )
    display_name = models.CharField(max_length=180)
    normalized_name = models.CharField(max_length=180, blank=True)
    person_rut = models.CharField(max_length=20, blank=True, null=True)
    license_plate = models.CharField(max_length=20, blank=True, null=True)
    internal_code = models.CharField(max_length=60, blank=True, null=True)
    job_title = models.ForeignKey(
        JobTitle,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='resources'
    )
    is_trackable = models.BooleanField(default=True)
    last_partida_cod = models.CharField(max_length=120, blank=True, null=True)
    last_partida_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='resources_created'
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='resources_updated'
    )

    class Meta:
        db_table = 'resources_resource'
        verbose_name = 'Recurso'
        verbose_name_plural = 'Recursos'
        ordering = ['company', 'display_name']

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


class ResourceSiteAssignment(models.Model):

    class AssignmentType(models.TextChoices):
        PRIMARY = 'PRIMARY', 'Principal'
        LOAN = 'LOAN', 'Prestamo'
        TEMPORARY = 'TEMPORARY', 'Temporal'

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Activa'
        ENDED = 'ENDED', 'Terminada'
        CANCELLED = 'CANCELLED', 'Cancelada'

    resource = models.ForeignKey(
        Resource,
        on_delete=models.PROTECT,
        related_name='site_assignments'
    )
    site = models.ForeignKey(
        'companies.Site',
        on_delete=models.PROTECT,
        related_name='resource_assignments'
    )
    assignment_type = models.CharField(
        max_length=20,
        choices=AssignmentType.choices,
        default=AssignmentType.PRIMARY
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='assignments_made'
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'resources_resource_site_assignment'
        verbose_name = 'Asignacion de recurso a obra'
        verbose_name_plural = 'Asignaciones de recurso a obra'
        ordering = ['-started_at']
        constraints = [
            models.UniqueConstraint(
                fields=['resource'],
                condition=models.Q(status='ACTIVE'),
                name='unique_active_assignment_per_resource'
            )
        ]

    def __str__(self):
        return f'{self.resource.display_name} -> {self.site.name} ({self.assignment_type})'
