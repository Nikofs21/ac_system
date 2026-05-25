# -*- coding: utf-8 -*-
from django.urls import path
from . import views
from . import views_crud

app_name = 'resources'

urlpatterns = [
    # Listado
    path('trabajadores/', views.worker_list, name='worker_list'),

    # QR
    path('qr/<int:resource_id>/', views.resource_qr_view, name='resource_qr'),

    # CRUD recursos
    path('trabajadores/nuevo/', views_crud.resource_create, name='resource_create'),
    path('trabajadores/<int:resource_id>/editar/', views_crud.resource_edit, name='resource_edit'),
    path('trabajadores/<int:resource_id>/baja/', views_crud.resource_deactivate, name='resource_deactivate'),
    path('trabajadores/<int:resource_id>/reactivar/', views_crud.resource_reactivate, name='resource_reactivate'),

    # Cargo inline
    path('cargos/crear/', views_crud.job_title_create_inline, name='job_title_create'),
]
