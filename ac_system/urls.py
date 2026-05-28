# -*- coding: utf-8 -*-
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect
from subcontracts import views as subcontracts_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('', include('core.urls')),
    path('work/', include('work.urls')),
    path('resources/', include('resources.urls')),
    path('tracking/', include('tracking.urls')),
    # Ruta publica del QR — corta y memorable para imprimir en credenciales
    path('r/<str:uid>/', include('resources.urls_qr')),
    path('', lambda request: redirect('dashboard'), name='home'),
    path('access/', include('access.urls')),
    path('subcontracts/', include('subcontracts.urls')),
    path('subcontratos/<str:subcontract_uid>/', subcontracts_views.subcontract_form, name='subcontract_form_qr'),
]
