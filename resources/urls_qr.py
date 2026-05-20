# -*- coding: utf-8 -*-
# URLs publicas del QR — montadas en /r/<uid>/
# Separadas de resources/urls.py para mantener limpio el namespace
from django.urls import path
from resources import views

urlpatterns = [
    path('', views.resource_qr_page, name='resource_qr_page'),
]
