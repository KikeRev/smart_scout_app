# apps/users/views.py
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from django.contrib.auth.forms import AuthenticationForm
from django.views.generic import CreateView , DetailView, UpdateView
from .forms import SignUpForm, ProfileForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy

from .models import User


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



class ProfileView(LoginRequiredMixin, DetailView):
    """Muestra los datos de la cuenta del usuario autenticado."""
    model = User
    template_name = "users/profile.html"
    context_object_name = "user_obj"

    # siempre devolvemos el objeto del request
    def get_object(self, queryset=None):
        return self.request.user


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    """Formulario para que el propio usuario edite su perfil."""
    model = User
    form_class = ProfileForm          # ya lo tenías definido :contentReference[oaicite:4]{index=4}
    template_name = "users/profile_edit.html"
    success_url   = reverse_lazy("users:profile")

    def get_object(self, queryset=None):
        return self.request.user


