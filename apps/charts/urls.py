# apps/charts/urls.py
from django.urls import path
from . import views

app_name = "charts" 

urlpatterns = [
    path("<uuid:pk>/",            views.serve_chart, name="chart"),
    path("<uuid:pk>/download/",   views.serve_chart, {"download": True},
         name="chart_download"),
    path("<int:pk>/", views.file, name="file"),
]