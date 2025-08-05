from django.urls import path
from .views import LoginView, LogoutView, SignUpView, ProfileView, ProfileUpdateView

app_name = "users"                     

urlpatterns = [
    path("login/",  LoginView.as_view(),  name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("signup/", SignUpView.as_view(), name="signup"),

    path("profile/",        ProfileView.as_view(),        name="profile"),
    path("profile/edit/",   ProfileUpdateView.as_view(),  name="profile_edit"),
]