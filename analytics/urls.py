# -*- coding: utf-8 -*-
from django.urls import path
from . import views

urlpatterns = [
    path('productividad/', views.productivity_dashboard, name='productivity_dashboard'),
]
