# -*- coding: utf-8 -*-
from django.contrib import admin
from .models import SiteAlertConfig, AlertLog


@admin.register(SiteAlertConfig)
class SiteAlertConfigAdmin(admin.ModelAdmin):
    list_display = ('site', 'alert_type', 'is_enabled')
    list_filter = ('alert_type', 'is_enabled', 'site')
    search_fields = ('site__name',)


@admin.register(AlertLog)
class AlertLogAdmin(admin.ModelAdmin):
    list_display = ('site', 'alert_type', 'status', 'sent_at')
    list_filter = ('status', 'alert_type', 'site')
    readonly_fields = ('sent_at',)
