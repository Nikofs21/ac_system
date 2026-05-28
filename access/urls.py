# -*- coding: utf-8 -*-
from django.urls import path
from . import views_moi

app_name = 'access'

urlpatterns = [
    path('moi/', views_moi.moi_list, name='moi_list'),
    path('moi/nuevo/', views_moi.moi_create, name='moi_create'),
    path('moi/<int:membership_id>/editar/', views_moi.moi_edit, name='moi_edit'),
    path('moi/<int:membership_id>/baja/', views_moi.moi_deactivate, name='moi_deactivate'),
    path('moi/<int:membership_id>/qr/', views_moi.moi_qr, name='moi_qr'),
    path('moi/<int:membership_id>/reactivar/', views_moi.moi_reactivate, name='moi_reactivate'),
]
