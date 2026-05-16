# -*- coding: utf-8 -*-
from django.urls import path
from . import views

app_name = 'work'

urlpatterns = [
    path('asignar/', views.assignment_new, name='assignment_new'),
    path('asignar/escanear/', views.assignment_scan, name='assignment_scan'),
    path('asignar/confirmar/', views.assignment_confirm, name='assignment_confirm'),
    path('asignar/qr/', views.scan_qr, name='scan_qr'),
    path('asignar/quitar/', views.remove_from_group, name='remove_from_group'),
    path('activos/', views.active_workers, name='active_workers'),
    path('cerrar/<int:session_id>/', views.close_session, name='close_session'),
    path('cierre-masivo/', views.mass_close, name='mass_close'),
]
