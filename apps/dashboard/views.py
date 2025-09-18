#from django.contrib.auth.decorators import login_required
from django.shortcuts import render
import logging
from django.contrib.auth.decorators import login_required
from django.contrib.staticfiles import finders
import os, random

from .chats.models import ChatSession
from .models import FootballNews, SavedSearch     

from django.views.decorators.csrf import csrf_exempt

from django.http import HttpResponseBadRequest, HttpResponse, HttpResponseBadRequest, HttpResponseNotAllowed, JsonResponse

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


# ───────────────── NUEVAS VISTAS DEL DASHBOARD DE BÚSQUEDA MANUAL ──────────────────

@login_required
def player_search(request):
    """Vista principal de búsqueda de jugadores"""
    from .search_services import get_filter_options
    
    # Obtener opciones de filtros
    filter_options = get_filter_options()
    
    context = {
        'filter_options': filter_options,
    }
    
    return render(request, "dashboard/player_search.html", context)

@login_required
def comparison_dashboard(request):
    """Dashboard de comparación de jugadores"""
    from .search_services import get_player_details, get_comparison_data
    from apps.agent_service.dashboard_viz_tools import dashboard_radar_single, dashboard_radar_comparison
    
    # Obtener IDs de jugadores seleccionados
    player_ids = request.GET.getlist('player_ids')
    selected_metrics = request.GET.getlist('metrics')
    
    print(f"DEBUG: player_ids = {player_ids}")
    print(f"DEBUG: selected_metrics = {selected_metrics}")
    
    if not player_ids:
        return render(request, "dashboard/comparison.html", {
            'error': 'No se han seleccionado jugadores'
        })
    
    # Convertir a enteros
    try:
        player_ids = [int(pid) for pid in player_ids]
        print(f"DEBUG: player_ids convertidos = {player_ids}")
    except ValueError:
        return render(request, "dashboard/comparison.html", {
            'error': 'IDs de jugadores inválidos'
        })
    
    # Obtener datos de jugadores
    print("DEBUG: Obteniendo datos de jugadores...")
    players_data = get_player_details(player_ids)
    print(f"DEBUG: players_data = {players_data}")
    
    if not players_data:
        return render(request, "dashboard/comparison.html", {
            'error': 'No se pudieron cargar los datos de los jugadores'
        })
    
    # Preparar datos para la comparación
    comparison_data = get_comparison_data(players_data, selected_metrics)
    
    # Generar gráfico
    print("DEBUG: Generando gráfico...")
    if len(players_data) == 1:
        chart_result = dashboard_radar_single(players_data[0], selected_metrics)
    else:
        chart_result = dashboard_radar_comparison(players_data, selected_metrics)
    
    print(f"DEBUG: Resultado del gráfico: {chart_result}")
    
    chart_url = None
    if chart_result.get('attachments') and len(chart_result['attachments']) > 0:
        chart_url = chart_result['attachments'][0]['url']
        print(f"DEBUG: URL del gráfico: {chart_url}")
    else:
        print("DEBUG: No se generó el gráfico")
    
    context = {
        'players': players_data,
        'chart_url': chart_url,
        'selected_metrics': selected_metrics,
        'player_count': len(players_data)
    }
    
    return render(request, "dashboard/comparison.html", context)

@login_required
def search_api(request):
    """API para búsqueda de jugadores"""
    from .search_services import search_players, build_search_filters, get_all_players, get_filter_options, get_available_metrics
    import json
    
    if request.method == 'GET':
        action = request.GET.get('action')
        
        if action == 'filter_options':
            # Devolver opciones de filtros
            try:
                results = get_filter_options()
                return JsonResponse(results)
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=400)
        
        elif action == 'metrics':
            # Devolver métricas disponibles
            try:
                results = get_available_metrics()
                return JsonResponse({'metrics': results})
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=400)
        
        else:
            # Devolver todos los jugadores para el filtrado dinámico
            try:
                results = get_all_players()
                return JsonResponse(results)
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=400)
    
    elif request.method == 'POST':
        # Búsqueda con filtros
        try:
            data = json.loads(request.body)
            filters = build_search_filters(data)
            results = search_players(**filters)
            return JsonResponse(results)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)

@login_required
def saved_searches_api(request):
    """API para gestionar búsquedas guardadas"""
    import json
    
    if request.method == 'GET':
        search_id = request.GET.get('id')
        
        if search_id:
            # Obtener una búsqueda específica
            try:
                search = SavedSearch.objects.get(id=search_id, user=request.user)
                from .search_services import serialize_saved_search
                return JsonResponse(serialize_saved_search(search))
            except SavedSearch.DoesNotExist:
                return JsonResponse({'error': 'Búsqueda no encontrada'}, status=404)
        else:
            # Obtener todas las búsquedas guardadas del usuario
            searches = SavedSearch.objects.filter(user=request.user)
            from .search_services import serialize_saved_search
            data = [serialize_saved_search(search) for search in searches]
            return JsonResponse({'searches': data})
    
    elif request.method == 'POST':
        # Guardar nueva búsqueda
        try:
            data = json.loads(request.body)
            print(f"DEBUG: Datos recibidos: {data}")
            print(f"DEBUG: Usuario: {request.user}")
            
            search = SavedSearch.objects.create(
                user=request.user,
                name=data['name'],
                search_params=data['search_params'],
                selected_players=data['selected_players'],
                selected_metrics=data['selected_metrics']
            )
            print(f"DEBUG: Búsqueda creada con ID: {search.id}")
            
            from .search_services import serialize_saved_search
            return JsonResponse(serialize_saved_search(search))
        except Exception as e:
            print(f"DEBUG: Error al guardar búsqueda: {e}")
            return JsonResponse({'error': str(e)}, status=400)
    
    elif request.method == 'DELETE':
        # Eliminar búsqueda
        try:
            data = json.loads(request.body)
            search_id = data['id']
            search = SavedSearch.objects.get(id=search_id, user=request.user)
            search.delete()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)