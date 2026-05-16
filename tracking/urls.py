from django.urls import path
from django.shortcuts import render

app_name = 'tracking'

def placeholder(request):
    return render(request, 'dashboard.html')

urlpatterns = [
    path('no-en-obra/', placeholder, name='no_on_site'),
]