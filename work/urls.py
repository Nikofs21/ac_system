# -*- coding: utf-8 -*-
from django.urls import path
from . import views
from . import views_review

app_name = 'work'

urlpatterns = [
    # Flujo de asignacion
    path('asignar/', views.assignment_new, name='assignment_new'),
    path('asignar/escanear/', views.assignment_scan, name='assignment_scan'),
    path('asignar/confirmar/', views.assignment_confirm, name='assignment_confirm'),
    path('asignar/qr/', views.scan_qr, name='scan_qr'),
    path('asignar/quitar/', views.remove_from_group, name='remove_from_group'),
    path('asignar/buscar/', views.search_resources, name='search_resources'),
    path('asignar/precargar/<int:resource_id>/', views.assignment_preload, name='assignment_preload'),

    # Trabajadores activos y cierre
    path('activos/', views.active_workers, name='active_workers'),
    path('cerrar/<int:session_id>/', views.close_session, name='close_session'),
    path('cierre-masivo/', views.mass_close, name='mass_close'),

    # Revision de partidas
    path('revision/', views_review.session_review, name='session_review'),
    path('revision/editar/<int:session_id>/', views_review.session_edit, name='session_edit'),
]
