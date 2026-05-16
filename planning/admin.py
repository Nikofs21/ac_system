# -*- coding: utf-8 -*-
# admin_planning.py
from django.contrib import admin
from .models import ProgressBatch, ProgressEntry, CompanyProgressFormat, CompanyProgressMapping


class ProgressEntryInline(admin.TabularInline):
    model = ProgressEntry
    extra = 0


class CompanyProgressMappingInline(admin.TabularInline):
    model = CompanyProgressMapping
    extra = 0


@admin.register(ProgressBatch)
class ProgressBatchAdmin(admin.ModelAdmin):
    list_display = ('site', 'week_start', 'source_type', 'status', 'uploaded_by')
    list_filter = ('status', 'source_type', 'site')
    search_fields = ('site__name',)
    inlines = [ProgressEntryInline]


@admin.register(CompanyProgressFormat)
class CompanyProgressFormatAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'file_type', 'is_default', 'is_active')
    list_filter = ('file_type', 'is_active', 'company')
    inlines = [CompanyProgressMappingInline]
