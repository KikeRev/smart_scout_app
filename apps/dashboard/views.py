#from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.shortcuts import render, redirect
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
import logging

logger = logging.getLogger(__name__)

#@login_required
def home(request):
    context = {
        "headlines": [
            "Mercado de fichajes: Mbappé al PSG",
            "LaLiga EA Sports arranca el 16-Ago",
            "Ancelotti renueva hasta 2027",
        ],
        
    }
    return render(request, "dashboard/home.html", context)
