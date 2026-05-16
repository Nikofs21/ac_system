# -*- coding: utf-8 -*-
from django.contrib import admin
from .models import (
    Stage, TaskCatalog, StageTask, SupervisorStagePermission,
    WorkSession, WorkSessionChangeLog, MassCloseBatch,
    MassCloseBatchItem, OvertimePolicy
)


@admin.register(Stage)
class StageAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'company', 'site', 'stage_type', 'is_active')
    list_filter = ('stage_type', 'is_active', 'company')
    search_fields = ('name', 'code')


@admin.register(TaskCatalog)
class TaskCatalogAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'company', 'risk_level', 'status')
    list_filter = ('risk_level', 'status', 'company')
    search_fields = ('code', 'name')


@admin.register(StageTask)
class StageTaskAdmin(admin.ModelAdmin):
    list_display = ('stage', 'task', 'site', 'is_active', 'display_order')
    list_filter = ('is_active', 'site')
    search_fields = ('stage__name', 'task__name')


class WorkSessionChangeLogInline(admin.TabularInline):
    model = WorkSessionChangeLog
    extra = 0
    readonly_fields = ('changed_by', 'change_type', 'before_json', 'after_json', 'reason', 'created_at')


@admin.register(WorkSession)
class WorkSessionAdmin(admin.ModelAdmin):
    list_display = (
        'resource', 'site', 'task_name_snapshot',
        'started_at', 'ended_at', 'duration_minutes',
        'status', 'is_overtime'
    )
    list_filter = ('status', 'is_overtime', 'site', 'closure_origin')
    search_fields = ('resource__display_name', 'task_name_snapshot', 'stage_name_snapshot')
    readonly_fields = ('created_at', 'updated_at', 'duration_minutes', 'duration_productive_minutes')
    inlines = [WorkSessionChangeLogInline]


class MassCloseBatchItemInline(admin.TabularInline):
    model = MassCloseBatchItem
    extra = 0
    readonly_fields = ('session', 'closed_at_effective')


@admin.register(MassCloseBatch)
class MassCloseBatchAdmin(admin.ModelAdmin):
    list_display = ('site', 'executed_by', 'closed_count', 'executed_at')
    list_filter = ('site',)
    readonly_fields = ('executed_at',)
    inlines = [MassCloseBatchItemInline]


@admin.register(OvertimePolicy)
class OvertimePolicyAdmin(admin.ModelAdmin):
    list_display = ('site', 'weekday', 'normal_end_time', 'all_day_overtime', 'is_active')
    list_filter = ('is_active', 'site')
