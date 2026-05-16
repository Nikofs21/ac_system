# -*- coding: utf-8 -*-
from django.contrib import admin
from .models import Subcontract, SubcontractSession, SubcontractSessionDetail, SubcontractSessionHistory


class SubcontractSessionDetailInline(admin.StackedInline):
    model = SubcontractSessionDetail
    extra = 0


class SubcontractSessionHistoryInline(admin.TabularInline):
    model = SubcontractSessionHistory
    extra = 0
    readonly_fields = ('changed_by', 'change_type', 'before_json', 'after_json', 'reason', 'created_at')


@admin.register(Subcontract)
class SubcontractAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'site', 'status')
    list_filter = ('status', 'site')
    search_fields = ('name', 'code')


@admin.register(SubcontractSession)
class SubcontractSessionAdmin(admin.ModelAdmin):
    list_display = ('subcontract', 'task', 'started_at', 'ended_at', 'status')
    list_filter = ('status', 'site')
    search_fields = ('subcontract__name', 'task__name')
    inlines = [SubcontractSessionDetailInline, SubcontractSessionHistoryInline]
