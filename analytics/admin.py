# -*- coding: utf-8 -*-
from django.contrib import admin
from .models import (
    TaskBudget, TaskApuMapping, IndustryBenchmark,
    WeeklySnapshot, DailyProductivitySnapshot,
)


class TaskApuMappingInline(admin.TabularInline):
    model = TaskApuMapping
    extra = 0


@admin.register(TaskBudget)
class TaskBudgetAdmin(admin.ModelAdmin):
    list_display = ('task', 'site', 'um_code', 'budget_hh_per_unit', 'budget_quantity', 'is_active')
    list_filter = ('is_active', 'site')
    search_fields = ('task__name', 'task__code')
    inlines = [TaskApuMappingInline]


@admin.register(IndustryBenchmark)
class IndustryBenchmarkAdmin(admin.ModelAdmin):
    list_display = ('task_type_code', 'region_code', 'um_code', 'industry_hh_per_unit', 'valid_from')
    list_filter = ('region_code',)
    search_fields = ('task_type_code',)


@admin.register(WeeklySnapshot)
class WeeklySnapshotAdmin(admin.ModelAdmin):
    list_display = (
        'task', 'site', 'week_start', 'week_number',
        'hh_productive', 'icc_pct', 'rendimiento_real_hh_unit', 'is_partial'
    )
    list_filter = ('is_partial', 'site')
    search_fields = ('task__name', 'stage__name')
    readonly_fields = ('computed_at',)


@admin.register(DailyProductivitySnapshot)
class DailyProductivitySnapshotAdmin(admin.ModelAdmin):
    list_display = ('site', 'date', 'trab', 'hh', 'hh_pag', 'icc', 'costo_hh', 'computed_at')
    list_filter = ('site',)
    ordering = ('-date',)
    readonly_fields = ('computed_at',)
