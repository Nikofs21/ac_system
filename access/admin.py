# -*- coding: utf-8 -*-
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, UserPreference, Role, Permission, RolePermission
from access.models import SiteMembershipPermissionOverride


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'first_name', 'last_name', 'actor_type', 'is_active')
    list_filter = ('actor_type', 'is_active', 'is_staff')
    search_fields = ('email', 'first_name', 'last_name', 'rut')
    ordering = ('email',)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Datos personales', {'fields': ('first_name', 'last_name', 'rut', 'phone')}),
        ('Permisos', {'fields': ('actor_type', 'is_active', 'is_staff', 'is_superuser')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'actor_type', 'password1', 'password2'),
        }),
    )


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'timezone', 'last_company', 'last_site')
    search_fields = ('user__email', 'user__first_name', 'user__last_name')


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'scope_type', 'company', 'is_active')
    list_filter = ('scope_type', 'is_active')
    search_fields = ('name', 'code')
    ordering = ('name',)


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ('name', 'module', 'level', 'code', 'is_active')
    list_filter = ('module', 'level', 'is_active')
    search_fields = ('name', 'code')
    ordering = ('module', 'level')


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ('role', 'permission', 'granted')
    list_filter = ('granted', 'role')
    search_fields = ('role__name', 'permission__name')

@admin.register(SiteMembershipPermissionOverride)
class SiteMembershipPermissionOverrideAdmin(admin.ModelAdmin):
    list_display  = ('get_user', 'get_site', 'permission', 'granted', 'created_by')
    list_filter   = ('granted', 'site_membership__site', 'permission__module')
    search_fields = (
        'site_membership__user__email',
        'site_membership__user__first_name',
        'permission__code',
    )
    raw_id_fields = ('site_membership', 'permission', 'created_by')

    def get_user(self, obj):
        u = obj.site_membership.user
        return u.get_full_name() or u.email
    get_user.short_description = 'Usuario'

    def get_site(self, obj):
        return obj.site_membership.site.name
    get_site.short_description = 'Obra'