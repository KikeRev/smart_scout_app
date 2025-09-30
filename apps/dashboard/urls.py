from django.urls import path
from .views import home, refresh_dash, inline_view, player_search, comparison_dashboard, search_api, saved_searches_api, player_profile
from django.views.decorators.csrf import csrf_exempt

app_name = "dashboard"

urlpatterns = [
    path("",             home,              name="home"),      # landing "/"
    path("refresh/",     refresh_dash,      name="refresh"),   # HTMX
    path("inline/", csrf_exempt(inline_view), name="dashboard_inline"),
    
    # New manual search dashboard routes
    path("search/",      player_search,     name="player_search"),
    path("compare/",     comparison_dashboard, name="comparison"),
    path("api/search/",  csrf_exempt(search_api), name="search_api"),
    path("api/saved-searches/", csrf_exempt(saved_searches_api), name="saved_searches_api"),
    path("player/<int:player_id>/", player_profile, name="player_profile"),
]
