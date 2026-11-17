from django.contrib import admin
from django.urls import path, include
from finance import views

urlpatterns = [path('admin/', admin.site.urls), path('health/', views.health), path('', include('finance.urls'))]
