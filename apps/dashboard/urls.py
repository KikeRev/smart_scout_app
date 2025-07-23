from django.urls import path, include
from .views import home

app_name = "dashboard"

urlpatterns = [
    path("", home, name="home"),   #  <- landing
    
]
