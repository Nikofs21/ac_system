# -*- coding: utf-8 -*-
from django.contrib import admin
from .models import (
    Subcontract,
    SubcontractSession,
    SubcontractSessionDetail,
    SubcontractPersonnelSlot,
    SubcontractSessionHistory,
    SubcontractTaskAssignment,
)


class SubcontractPersonnelSlotInline(admin.TabularInline):
    model = SubcontractPersonnelSlot
    extra = 0
    readonly_fields = ('started_at', 'ended_at', 'quantity', 'created_by', 'created_at')


class SubcontractSessionDetailInline(admin.StackedInline):
    model = SubcontractSessionDetail
    extra = 0
    readonly_fields = ('task', 'unit_code', 'created_at')


class SubcontractSessionHistoryInline(admin.TabularInline):
    model = SubcontractSessionHistory
    extra = 0
    readonly_fields = ('changed_by', 'change_type', 'before_json', 'after_json', 'reason', 'created_at')

class SubcontractTaskAssignmentInline(admin.TabularInline):
    model = SubcontractTaskAssignment
    extra = 1
    fields = ('task', 'reserved_stage', 'is_active')

@admin.register(Subcontract)
class SubcontractAdmin(admin.ModelAdmin):
    list_display  = ('name', 'code', 'site', 'status', 'uid')
    list_filter   = ('status', 'site')
    search_fields = ('name', 'code', 'rut')
    readonly_fields = ('uid', 'created_at', 'updated_at')
    inlines = [SubcontractTaskAssignmentInline]


@admin.register(SubcontractSession)
class SubcontractSessionAdmin(admin.ModelAdmin):
    list_display  = ('subcontract', 'started_at', 'ended_at', 'status', 'started_by')
    list_filter   = ('status', 'site')
    search_fields = ('subcontract__name',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [SubcontractSessionDetailInline, SubcontractSessionHistoryInline]


@admin.register(SubcontractSessionDetail)
class SubcontractSessionDetailAdmin(admin.ModelAdmin):
    list_display = ('session', 'task', 'unit_code')
    inlines      = [SubcontractPersonnelSlotInline]


@admin.register(SubcontractPersonnelSlot)
class SubcontractPersonnelSlotAdmin(admin.ModelAdmin):
    list_display    = ('detail', 'quantity', 'started_at', 'ended_at')
    list_filter     = ('ended_at',)
    readonly_fields = ('created_at',)

@admin.register(SubcontractTaskAssignment)
class SubcontractTaskAssignmentAdmin(admin.ModelAdmin):
    list_display = ('subcontract', 'task', 'reserved_stage', 'is_active')
    list_filter  = ('is_active', 'subcontract__site')
    search_fields = ('subcontract__name', 'task__name')