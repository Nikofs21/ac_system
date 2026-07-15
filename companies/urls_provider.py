# -*- coding: utf-8 -*-
from django.urls import path
from . import views_provider
from companies import views_rra

app_name = 'provider'

urlpatterns = [
    # Panel principal
    path('', views_provider.provider_panel, name='panel'),

    # Empresas
    path('empresa/nueva/', views_provider.company_create, name='company_create'),
    path('empresa/<int:company_id>/editar/', views_provider.company_edit, name='company_edit'),
    path('empresa/<int:company_id>/desactivar/', views_provider.company_deactivate, name='company_deactivate'),
    path('empresa/<int:company_id>/activar/', views_provider.company_activate, name='company_activate'),

    # Obras
    path('empresa/<int:company_id>/obra/nueva/', views_provider.site_create, name='site_create'),
    path('obra/<int:site_id>/editar/', views_provider.site_edit, name='site_edit'),
    path('obra/<int:site_id>/usuarios/', views_provider.site_users, name='site_users'),

    # Permisos por membresía
    path('membresia/<int:membership_id>/permisos/', views_provider.membership_overrides, name='membership_overrides'),

    # Gestión de roles (solo novus_super)
    path('roles/', views_provider.role_list, name='role_list'),
    path('roles/<int:role_id>/permisos/', views_provider.role_permissions, name='role_permissions'),

    # Gerencia / Administrador de obra / AAC — pantalla de prestador
    # (reemplaza al viejo 'gerencia/nueva/': ahora cubre los 3 roles)
    path('gerencia-admin/', views_provider.management_users_panel, name='management_users'),
    path('gerencia-admin/titulo/nuevo/', views_provider.management_title_create, name='management_title_create'),
    path('gerencia-admin/<int:user_id>/<int:company_id>/editar/', views_provider.management_user_edit, name='management_user_edit'),

    # RRA
    path('rra/<int:site_id>/',                       views_rra.rra_config,             name='rra_config'),
    path('rra/<int:site_id>/semanas/',               views_rra.rra_week_config_save,   name='rra_week_config_save'),
    path('rra/<int:site_id>/cargo-valor/',           views_rra.rra_cargo_valor_save,   name='rra_cargo_valor_save'),
    path('rra/cargo-valor/<int:valor_id>/eliminar/', views_rra.rra_cargo_valor_delete, name='rra_cargo_valor_delete'),
    path('rra/<int:site_id>/exportar/',              views_rra.rra_export,             name='rra_export'),
]
