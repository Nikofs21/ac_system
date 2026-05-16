from django.urls import path
from django.shortcuts import render

app_name = 'resources'

def placeholder(request):
    return render(request, 'dashboard.html')

urlpatterns = [
    path('trabajadores/', placeholder, name='worker_list'),
]