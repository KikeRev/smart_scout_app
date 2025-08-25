from django.urls import path
from .views import home, refresh_dash, inline_view
from django.views.decorators.csrf import csrf_exempt

app_name = "dashboard"

urlpatterns = [
    path("",             home,              name="home"),      # landing "/"
    path("refresh/",     refresh_dash,      name="refresh"),   # HTMX
    path("inline/", csrf_exempt(inline_view), name="dashboard_inline"),
    
]
