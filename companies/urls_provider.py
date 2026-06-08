# -*- coding: utf-8 -*-
from django.urls import path
from . import views_provider

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
]
