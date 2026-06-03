# -*- coding: utf-8 -*-
from django.contrib import admin
from .models import (
    Stage, TaskCatalog, StageTask, SupervisorTaskPermission,
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
    list_display  = ('site', 'get_weekday_display', 'normal_end_time', 'auto_close_time', 'all_day_overtime', 'is_active')
    list_filter   = ('is_active', 'site')
    ordering      = ('site', 'weekday')

    def get_weekday_display(self, obj):
        dias = ['Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado', 'Domingo']
        return dias[obj.weekday] if 0 <= obj.weekday <= 6 else str(obj.weekday)
    get_weekday_display.short_description = 'Dia'

class SupervisorTaskPermissionInline(admin.TabularInline):
    model = SupervisorTaskPermission
    extra = 1
    fields = ('task', 'is_active')


@admin.register(SupervisorTaskPermission)
class SupervisorTaskPermissionAdmin(admin.ModelAdmin):
    list_display  = ('get_supervisor', 'get_site', 'task', 'is_active')
    list_filter   = ('is_active', 'site_membership__site')
    search_fields = ('site_membership__user__email', 'task__name')

    def get_supervisor(self, obj):
        return obj.site_membership.user.get_full_name() or obj.site_membership.user.email
    get_supervisor.short_description = 'Supervisor'

    def get_site(self, obj):
        return obj.site_membership.site.name
    get_site.short_description = 'Obra'