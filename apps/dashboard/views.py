#from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.shortcuts import render, redirect
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
import logging
from django.contrib.auth.decorators import login_required
from django.shortcuts      import render
from django.contrib.staticfiles import finders
from django.conf           import settings
from django.db             import connection      # para SQL puro (alternativa)
from pathlib               import Path
import os, random

from .chats.models import ChatSession
from .models import FootballNews     

logger = logging.getLogger(__name__)

@login_required


def home(request):

    # 1) sesiones recientes
    recent_sessions = (ChatSession.objects
                       .filter(user=request.user)
                       .order_by('-created_at')[:6])

    # 2) galería de fotos (igual que antes)
    gallery = []
    pics_dir = finders.find("img/soccer_pictures")
    if pics_dir and os.path.isdir(pics_dir):
        all_pics = [f for f in os.listdir(pics_dir)
                    if os.path.isfile(os.path.join(pics_dir, f))]
        gallery = random.sample(all_pics, min(6, len(all_pics)))

    # 3) titulares (PostgreSQL)
    # --- Opción A: vía ORM (recomendado)
    headlines_qs = (FootballNews.objects
                    .values_list("title", "published_at", "source_id")
                    .order_by("?")[:30])
    headlines = [f"{s}: {t} | {p.strftime('%d %b %Y %H:%M')}" for t, p, s in headlines_qs]

    # ▸ Opción B: SQL crudo (si prefieres no definir modelo)
    # with connection.cursor() as cur:
    #     cur.execute("""
    #         SELECT title || ' | ' ||
    #                TO_CHAR(published_at, 'DD Mon YYYY HH24:MI')
    #         FROM football_news
    #         ORDER BY RANDOM()
    #         LIMIT 30
    #     """)
    #     headlines = [row[0] for row in cur.fetchall()]

    context = {
        "sessions":  recent_sessions,
        "gallery":   gallery,
        "headlines": headlines,
    }
    return render(request, "dashboard/home.html", context)
