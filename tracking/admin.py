# -*- coding: utf-8 -*-
from django.contrib import admin
from .models import NoOnSiteEvent


@admin.register(NoOnSiteEvent)
class NoOnSiteEventAdmin(admin.ModelAdmin):
    list_display = ('resource', 'site', 'event_date', 'reason_code', 'status', 'marked_by')
    list_filter = ('status', 'reason_code', 'site')
    search_fields = ('resource__display_name',)
    readonly_fields = ('created_at', 'updated_at')
