# -*- coding: utf-8 -*-
from django.urls import path
from . import views

app_name = 'tracking'

urlpatterns = [
    path('no-en-obra/', views.no_on_site, name='no_on_site'),
    path('no-en-obra/detalle/<int:resource_id>/', views.no_on_site_detail, name='no_on_site_detail'),
    path('no-en-obra/marcar/', views.no_on_site_mark, name='no_on_site_mark'),
    path('no-en-obra/anular/', views.no_on_site_void, name='no_on_site_void'),
]
