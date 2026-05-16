# -*- coding: utf-8 -*-
from django.contrib import admin
from .models import ResourceCategory, JobTitle, Resource, ResourceSiteAssignment


@admin.register(ResourceCategory)
class ResourceCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'resource_type', 'is_active')
    list_filter = ('resource_type', 'is_active')
    search_fields = ('name', 'code')


@admin.register(JobTitle)
class JobTitleAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'resource_type', 'is_active')
    list_filter = ('resource_type', 'is_active', 'company')
    search_fields = ('name', 'code')


class ResourceSiteAssignmentInline(admin.TabularInline):
    model = ResourceSiteAssignment
    extra = 0
    fields = ('site', 'assignment_type', 'status', 'started_at', 'ended_at')


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'company', 'resource_category', 'status', 'person_rut', 'resource_uid')
    list_filter = ('status', 'resource_category', 'company')
    search_fields = ('display_name', 'person_rut', 'resource_uid', 'internal_code')
    readonly_fields = ('resource_uid', 'created_at', 'updated_at')
    inlines = [ResourceSiteAssignmentInline]


@admin.register(ResourceSiteAssignment)
class ResourceSiteAssignmentAdmin(admin.ModelAdmin):
    list_display = ('resource', 'site', 'assignment_type', 'status', 'started_at')
    list_filter = ('status', 'assignment_type', 'site')
    search_fields = ('resource__display_name', 'site__name')
