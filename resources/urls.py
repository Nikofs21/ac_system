# -*- coding: utf-8 -*-
from django.urls import path
from . import views

app_name = 'resources'

urlpatterns = [
    path('trabajadores/', views.worker_list, name='worker_list'),
    path('qr/<int:resource_id>/', views.resource_qr_view, name='resource_qr'),
]
