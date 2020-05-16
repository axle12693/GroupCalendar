from django.contrib import admin
from django.urls import path, include
from .views import Index as CalAppViewsIndex

urlpatterns = [
    path('', CalAppViewsIndex)
]
