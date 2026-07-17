# -*- coding: utf-8 -*-
from django.contrib import admin
from .models import (
    Company, CompanyConfig, Site, SiteConfig,
    SiteWorkdayConfig, CompanyMembership, SiteMembership
)


class CompanyConfigInline(admin.StackedInline):
    model = CompanyConfig
    extra = 0


class SiteConfigInline(admin.StackedInline):
    model = SiteConfig
    extra = 0


class SiteWorkdayConfigInline(admin.TabularInline):
    model = SiteWorkdayConfig
    extra = 0
    fields = (
        'weekday', 'work_start_time', 'work_end_time',
        'lunch_start_time', 'lunch_end_time', 'deduct_lunch_from_icc',
        'all_day_overtime', 'effective_from', 'effective_to', 'is_active',
    )
    ordering = ('weekday', '-effective_from')


class CompanyMembershipInline(admin.TabularInline):
    model = CompanyMembership
    extra = 0
    fk_name = 'company'


class SiteMembershipInline(admin.TabularInline):
    model = SiteMembership
    extra = 0


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'status', 'contact_email')
    list_filter = ('status',)
    search_fields = ('name', 'code', 'tax_id')
    ordering = ('name',)
    inlines = [CompanyConfigInline, CompanyMembershipInline]


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'company', 'status', 'start_date', 'end_date')
    list_filter = ('status', 'company')
    search_fields = ('name', 'code')
    ordering = ('company', 'name')
    inlines = [SiteConfigInline, SiteWorkdayConfigInline, SiteMembershipInline]


@admin.register(CompanyMembership)
class CompanyMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'company', 'membership_type', 'is_active', 'started_at')
    list_filter = ('membership_type', 'is_active')
    search_fields = ('user__email', 'company__name')


@admin.register(SiteMembership)
class SiteMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'site', 'role', 'is_active', 'can_operate')
    list_filter = ('is_active', 'can_operate', 'role')
    search_fields = ('user__email', 'site__name')
