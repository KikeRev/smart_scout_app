# apps/users/views.py
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from django.contrib.auth.forms import AuthenticationForm
from django.views.generic import CreateView 
from .forms import SignUpForm

class LoginView(auth_views.LoginView):
    template_name = "users/login.html"          # usa tu plantilla
    authentication_form = AuthenticationForm    # (por defecto ya lo es)
    redirect_authenticated_user = True          # equivale a tu if-authenticated

    # Si quieres forzar un redirect fijo cuando no hay ?next=
    next_page = reverse_lazy("dashboard:home")  # ó "/"


class LogoutView(auth_views.LogoutView):
    next_page = reverse_lazy("users:login")     # ¡ojo al namespace!


class SignUpView(CreateView):
    form_class  = SignUpForm
    template_name = "users/signup.html"
    success_url   = reverse_lazy("users:login") # idem



