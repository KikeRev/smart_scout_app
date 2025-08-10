#from django.contrib.auth.decorators import login_required
from django.shortcuts import render
import logging
from django.contrib.auth.decorators import login_required
from django.contrib.staticfiles import finders
import os, random

from .chats.models import ChatSession
from .models import FootballNews     

from django.views.decorators.csrf import csrf_exempt

from django.http import HttpResponseBadRequest, HttpResponse, HttpResponseBadRequest, HttpResponseNotAllowed

from apps.agent_service.viz_tools import (
    radar_chart,
    pizza_comparison_chart
)
from apps.agent_service.utils import compare_stats_to_html_table

import requests
from django.urls import reverse
import json, urllib.parse
from typing import Annotated

logger = logging.getLogger(__name__)

DEFAULT_METRICS = ["goals", "assists","goals_per90", "assists_per90",
                   "expected_goals_per90", "passes_pct",
                   "interceptions", "tackles_won"]

@login_required
def home(request):

    # 1) sesiones recientes
    recent_sessions = (ChatSession.objects
                       .filter(user=request.user)
                       .order_by('-created_at')[:6])

    # 2) galería de fotos
    gallery = []
    pics_dir = finders.find("img/soccer_pictures")
    if pics_dir and os.path.isdir(pics_dir):
        all_pics = [f for f in os.listdir(pics_dir)
                    if os.path.isfile(os.path.join(pics_dir, f))]
        gallery = random.sample(all_pics, min(6, len(all_pics)))

    # 3) titulares (PostgreSQL)
    headlines_qs = (FootballNews.objects
                    .values_list("title", "published_at", "source_id")
                    .order_by("?")[:30])
    headlines = [f"{s}: {t} | {p.strftime('%d %b %Y %H:%M')}" for t, p, s in headlines_qs]

    context = {
        "sessions":  recent_sessions,
        "gallery":   gallery,
        "headlines": headlines,
    }
    return render(request, "dashboard/home.html", context)

# ───────────────── build context ──────────────────
...
API_HOST = os.getenv("API_HOST", "http://api:8001")  # si tu FastAPI sigue viva

def _fetch_stats(ids: list[int]) -> dict[int, dict]:
    """Devuelve {id: stats_dict} usando /players/batch."""
    r = requests.post(
        f"{API_HOST}/players/batch",
        json={"ids": ids},
        timeout=30,
    )
    r.raise_for_status()
    return {p["id"]: p for p in r.json()}

def _context(base_id: int, cand_id: int, cand_ids: list[int], metrics: list[str]):
    # ── 1) obtener stats una sola vez ─────────────────────
    stats_map = _fetch_stats([base_id] + cand_ids)

    base_stats = stats_map.get(base_id)
    cand_stats = stats_map.get(cand_id)
    if not (base_stats and cand_stats):
        raise ValueError("IDs no encontrados en la API")

    # ── 2) gráficos usando stats directamente ─────────────
    radar_base = radar_chart(
        player_name=base_stats["full_name"],
        stats=base_stats,
        team=base_stats["club"],
        position=base_stats["position"],
        nationality=base_stats["nationality"],
    )

    radar_cand = radar_chart(
        player_name=cand_stats["full_name"],
        stats=cand_stats,
        team=cand_stats["club"],
        position=cand_stats["position"],
        nationality=cand_stats["nationality"],
    )

    pizza_cmp = pizza_comparison_chart(
        player1_name=base_stats["full_name"],
        player2_name=cand_stats["full_name"],
        role=None,           # la función lo detecta por position
    )

    table_html = compare_stats_to_html_table(base_stats, cand_stats)

    players = list(stats_map.values())

    return {
        "base_id": base_id,
        "cand_id": cand_id,
        "cand_ids": cand_ids,
        "players": players,
        "metrics": metrics,
        "radar_base": radar_base["attachments"][0]["url"],
        "radar_cand": radar_cand["attachments"][0]["url"],
        "pizza_cmp":  pizza_cmp["attachments"][0]["url"],
        "table_html": table_html,
    }


# ───────── GET: navegación normal / tras el redirect ──────────
@csrf_exempt
def inline_view(request):
    """
    • POST  → genera HX-Redirect   (sin cambios)
    • GET   → renderiza el dashboard
    """
    # ---------- BLOQUE POST (tal cual lo tenías) ----------
    if request.method == "POST":
        try:
            data      = json.loads(request.body.decode())
            base_id   = int(data["base_id"])
            cand_ids  = [int(i) for i in data["candidate_ids"]]
        except (json.JSONDecodeError, KeyError, ValueError):
            return HttpResponseBadRequest("IDs missing")

        qs  = urllib.parse.urlencode(
                {"base_id": base_id, "candidate_ids": cand_ids}, doseq=True
              )
        url = f"{reverse('dashboard:dashboard_inline')}?{qs}"

        response = HttpResponse(status=204)
        response["HX-Redirect"] = url
        return response

    # ---------- BLOQUE GET (ajustes mínimos) -------------
    if request.method == "GET":
        try:
            base_id   = int(request.GET["base_id"])

            # ① cuando llega desde el agente
            raw = request.GET.getlist("candidate_ids")
            cand_ids = [int(v) for v in raw if v and v.isdigit()]

            if not cand_ids:
                cand_sel = request.GET.get("cand_id")
                if cand_sel and cand_sel.isdigit():
                    cand_ids = [int(cand_sel)]

        except (KeyError, ValueError):
            return HttpResponseBadRequest("IDs missing")

        if not cand_ids:                                   # lista vacía → 400
            return HttpResponseBadRequest("No candidate_ids given")

        # Métricas: o las que vengan del formulario, o las de siempre
        metrics = request.GET.getlist("metrics") or DEFAULT_METRICS

        ctx = _context(base_id, cand_ids[0], cand_ids, metrics)      # pasa la lista nueva
        ctx["players_dict"] = {p["id"]: p for p in ctx["players"]}
        ctx["cand_players"] = [ctx["players_dict"][i]
                                for i in cand_ids
                                if i in ctx["players_dict"]]
        
        return render(request, "dashboard/inline.html", ctx)

    # ------------------------------------------------------
    return HttpResponseNotAllowed(["GET", "POST"])


# ───────────────── HTMX refresh ──────────────────
@csrf_exempt
def refresh_dash(request):
    """Refresca tabla + gráficos al cambiar candidato o métricas (HTMX)."""
    base = int(request.POST["base_id"])
    cand = int(request.POST["cand_id"])
    metrics = request.POST.getlist("metrics[]") or DEFAULT_METRICS
    cand_ids = [int(v) for v in request.POST.getlist("cand_ids[]") if v.isdigit()]
    ctx = _context(base, cand, cand_ids, metrics)
    return render(request, "dashboard/_dash_body.html", ctx)