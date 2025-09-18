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
    template_name = "users/login.html"          # use your template
    authentication_form = AuthenticationForm    # (it's already the default)
    redirect_authenticated_user = True          # equivalent to your if-authenticated

    # If you want to force a fixed redirect when there's no ?next=
    next_page = reverse_lazy("dashboard:home")  # or "/"


class LogoutView(auth_views.LogoutView):
    next_page = reverse_lazy("users:login")     # watch the namespace!


class SignUpView(CreateView):
    form_class  = SignUpForm
    template_name = "users/signup.html"
    success_url   = reverse_lazy("users:login") # same



class ProfileView(LoginRequiredMixin, DetailView):
    """Shows the authenticated user's account data."""
    model = User
    template_name = "users/profile.html"
    context_object_name = "user_obj"

    # always return the request object
    def get_object(self, queryset=None):
        return self.request.user


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    """Form for the user to edit their own profile."""
    model = User
    form_class = ProfileForm          # you already had it defined
    template_name = "users/profile_edit.html"
    success_url   = reverse_lazy("users:profile")

    def get_object(self, queryset=None):
        return self.request.user


