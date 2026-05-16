from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('', include('core.urls')),
    path('work/', include('work.urls')),
    path('resources/', include('resources.urls')),
    path('tracking/', include('tracking.urls')),
    path('', lambda request: redirect('dashboard'), name='home'),
]