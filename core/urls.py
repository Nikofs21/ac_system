# -*- coding: utf-8 -*-
from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('seleccionar-obra/', views.select_site, name='select_site'),
    path('cambiar-obra/', views.change_site, name='change_site'),
    path('acceso-denegado/', views.access_denied, name='access_denied'),
    path('no-disponible/', views.feature_disabled, name='feature_disabled'),
]
