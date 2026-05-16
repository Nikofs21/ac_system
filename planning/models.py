# -*- coding: utf-8 -*-
from django.db import models
from django.conf import settings


class ProgressBatch(models.Model):

    class SourceType(models.TextChoices):
        MANUAL = 'MANUAL', 'Manual'
        XLSX = 'XLSX', 'Excel'
        CSV = 'CSV', 'CSV'

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Borrador'
        APPLIED = 'APPLIED', 'Aplicado'
        VOIDED = 'VOIDED', 'Anulado'

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.PROTECT,
        related_name='progress_batches'
    )
    site = models.ForeignKey(
        'companies.Site',
        on_delete=models.PROTECT,
        related_name='progress_batches'
    )
    source_type = models.CharField(
        max_length=20,
        choices=SourceType.choices,
        default=SourceType.MANUAL
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='progress_batches'
    )
    week_start = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )
    source_file_name = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'planning_progress_batch'
        verbose_name = 'Carga de avance'
        verbose_name_plural = 'Cargas de avance'
        ordering = ['-week_start']

    def __str__(self):
        return f'{self.site.name} - Semana {self.week_start} ({self.status})'


class ProgressEntry(models.Model):

    batch = models.ForeignKey(
        ProgressBatch,
        on_delete=models.CASCADE,
        related_name='entries'
    )
    site = models.ForeignKey(
        'companies.Site',
        on_delete=models.PROTECT,
        related_name='progress_entries'
    )
    stage = models.ForeignKey(
        'work.Stage',
        on_delete=models.PROTECT,
        related_name='progress_entries'
    )
    task = models.ForeignKey(
        'work.TaskCatalog',
        on_delete=models.PROTECT,
        related_name='progress_entries'
    )
    week_start = models.DateField()
    um_code = models.CharField(max_length=20)
    progress_value = models.DecimalField(max_digits=14, decimal_places=4)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='progress_entries'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'planning_progress_entry'
        verbose_name = 'Entrada de avance'
        verbose_name_plural = 'Entradas de avance'
        ordering = ['-week_start', 'stage', 'task']

    def __str__(self):
        return f'{self.task.name} - Semana {self.week_start}: {self.progress_value} {self.um_code}'


class CompanyProgressFormat(models.Model):

    class FileType(models.TextChoices):
        XLSX = 'XLSX', 'Excel'
        CSV = 'CSV', 'CSV'

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='progress_formats'
    )
    name = models.CharField(max_length=120)
    is_default = models.BooleanField(default=False)
    file_type = models.CharField(max_length=10, choices=FileType.choices, default=FileType.XLSX)
    sheet_name_rule = models.CharField(max_length=120, blank=True, null=True)
    header_row = models.IntegerField(null=True, blank=True)
    start_row = models.IntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'planning_company_progress_format'
        verbose_name = 'Formato de avance'
        verbose_name_plural = 'Formatos de avance'

    def __str__(self):
        return f'{self.name} - {self.company.name}'


class CompanyProgressMapping(models.Model):

    format = models.ForeignKey(
        CompanyProgressFormat,
        on_delete=models.CASCADE,
        related_name='mappings'
    )
    logical_field = models.CharField(max_length=80)
    source_column = models.CharField(max_length=20)
    transform_rule = models.CharField(max_length=120, blank=True, null=True)
    is_required = models.BooleanField(default=True)

    class Meta:
        db_table = 'planning_company_progress_mapping'
        verbose_name = 'Mapeo de formato de avance'
        verbose_name_plural = 'Mapeos de formato de avance'
        constraints = [
            models.UniqueConstraint(
                fields=['format', 'logical_field'],
                name='unique_mapping_per_format'
            )
        ]

    def __str__(self):
        return f'{self.format.name} - {self.logical_field} -> {self.source_column}'
