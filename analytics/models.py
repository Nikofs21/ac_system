# -*- coding: utf-8 -*-
from django.db import models
from django.conf import settings


class TaskBudget(models.Model):

    site = models.ForeignKey(
        'companies.Site',
        on_delete=models.PROTECT,
        related_name='task_budgets'
    )
    task = models.ForeignKey(
        'work.TaskCatalog',
        on_delete=models.PROTECT,
        related_name='budgets'
    )
    um_code = models.CharField(max_length=20)
    budget_hh_per_unit = models.DecimalField(max_digits=10, decimal_places=4)
    budget_quantity = models.DecimalField(max_digits=14, decimal_places=4)
    budget_hh_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='task_budgets_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'analytics_task_budget'
        verbose_name = 'Presupuesto de partida'
        verbose_name_plural = 'Presupuestos de partida'
        ordering = ['site', 'task']

    def __str__(self):
        return f'{self.task.name} - {self.site.name} ({self.budget_hh_per_unit} HH/{self.um_code})'


class TaskApuMapping(models.Model):

    task_budget = models.ForeignKey(
        TaskBudget,
        on_delete=models.CASCADE,
        related_name='apu_mappings'
    )
    apu_code = models.CharField(max_length=120)
    apu_description = models.CharField(max_length=255)
    weight_factor = models.DecimalField(max_digits=6, decimal_places=4, default=1.0)

    class Meta:
        db_table = 'analytics_task_apu_mapping'
        verbose_name = 'Mapeo APU'
        verbose_name_plural = 'Mapeos APU'

    def __str__(self):
        return f'{self.apu_code} -> {self.task_budget.task.name}'


class IndustryBenchmark(models.Model):

    task_type_code = models.CharField(max_length=80)
    region_code = models.CharField(max_length=20, default='CL')
    um_code = models.CharField(max_length=20)
    industry_hh_per_unit = models.DecimalField(max_digits=10, decimal_places=4)
    source_notes = models.TextField(blank=True, null=True)
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='benchmarks_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'analytics_industry_benchmark'
        verbose_name = 'Benchmark de industria'
        verbose_name_plural = 'Benchmarks de industria'
        ordering = ['task_type_code', 'region_code']

    def __str__(self):
        return f'{self.task_type_code} - {self.region_code}: {self.industry_hh_per_unit} HH/{self.um_code}'


class WeeklySnapshot(models.Model):

    site = models.ForeignKey(
        'companies.Site',
        on_delete=models.PROTECT,
        related_name='weekly_snapshots'
    )
    stage = models.ForeignKey(
        'work.Stage',
        on_delete=models.PROTECT,
        related_name='weekly_snapshots'
    )
    task = models.ForeignKey(
        'work.TaskCatalog',
        on_delete=models.PROTECT,
        related_name='weekly_snapshots'
    )
    week_start = models.DateField()
    week_number = models.IntegerField()
    hh_real = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    hh_productive = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    hh_disponibles_jornada = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    icc_pct = models.DecimalField(max_digits=6, decimal_places=4, null=True, blank=True)
    avg_start_time = models.TimeField(null=True, blank=True)
    resource_count = models.IntegerField(default=0)
    physical_progress_week = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    physical_progress_acum = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    um_code = models.CharField(max_length=20, blank=True, null=True)
    rendimiento_real_hh_unit = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    rendimiento_presupuesto = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    rendimiento_industria = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    prod_real_acum = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    prod_teorica_presup = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    computed_at = models.DateTimeField(auto_now=True)
    is_partial = models.BooleanField(default=True)

    class Meta:
        db_table = 'analytics_weekly_snapshot'
        verbose_name = 'Snapshot semanal'
        verbose_name_plural = 'Snapshots semanales'
        ordering = ['-week_start', 'stage', 'task']
        constraints = [
            models.UniqueConstraint(
                fields=['site', 'stage', 'task', 'week_start'],
                name='unique_weekly_snapshot'
            )
        ]

    def __str__(self):
        return f'{self.task.name} - Semana {self.week_number} ({self.site.name})'
