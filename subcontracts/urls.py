# -*- coding: utf-8 -*-
from django.urls import path
from . import views

app_name = 'subcontracts'

urlpatterns = [
    # CRUD — listado y gestión
    path('', views.subcontract_list, name='subcontract_list'),
    path('nuevo/', views.subcontract_create, name='subcontract_create'),
    path('<int:subcontract_id>/editar/', views.subcontract_edit, name='subcontract_edit'),
    path('<int:subcontract_id>/inactivar/', views.subcontract_deactivate, name='subcontract_deactivate'),
    path('<int:subcontract_id>/reactivar/', views.subcontract_reactivate, name='subcontract_reactivate'),
    path('<int:subcontract_id>/qr/', views.subcontract_qr, name='subcontract_qr'),
]
