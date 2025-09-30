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
from apps.agent_service.dashboard_viz_tools import dashboard_radar_single
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

    # 1) recent sessions
    recent_sessions = (ChatSession.objects
                       .filter(user=request.user)
                       .order_by('-created_at')[:6])

    # 2) photo gallery
    gallery = []
    pics_dir = finders.find("img/soccer_pictures")
    if pics_dir and os.path.isdir(pics_dir):
        all_pics = [f for f in os.listdir(pics_dir)
                    if os.path.isfile(os.path.join(pics_dir, f))]
        gallery = random.sample(all_pics, min(6, len(all_pics)))

    # 3) headlines (PostgreSQL)
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
API_HOST = os.getenv("API_HOST", "http://api:8001")  # if your FastAPI is still alive

def _fetch_stats(ids: list[int]) -> dict[int, dict]:
    """Returns {id: stats_dict} using /players/batch."""
    r = requests.post(
        f"{API_HOST}/players/batch",
        json={"ids": ids},
        timeout=30,
    )
    r.raise_for_status()
    return {p["id"]: p for p in r.json()}

def _context(base_id: int, cand_id: int, cand_ids: list[int], metrics: list[str]):
    # ── 1) get stats only once ─────────────────────
    stats_map = _fetch_stats([base_id] + cand_ids)

    base_stats = stats_map.get(base_id)
    cand_stats = stats_map.get(cand_id)
    if not (base_stats and cand_stats):
        raise ValueError("IDs not found in API")

    # ── 2) charts using stats directly ─────────────
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
        role=None,           # the function detects it by position
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


# ───────── GET: normal navigation / after redirect ──────────
@csrf_exempt
def inline_view(request):
    """
    • POST  → generates HX-Redirect   (no changes)
    • GET   → renders the dashboard
    """
    # ---------- POST BLOCK (as you had it) ----------
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

    # ---------- GET BLOCK (minimal adjustments) -------------
    if request.method == "GET":
        try:
            base_id   = int(request.GET["base_id"])

            # ① when it comes from the agent
            raw = request.GET.getlist("candidate_ids")
            cand_ids = [int(v) for v in raw if v and v.isdigit()]

            if not cand_ids:
                cand_sel = request.GET.get("cand_id")
                if cand_sel and cand_sel.isdigit():
                    cand_ids = [int(cand_sel)]

        except (KeyError, ValueError):
            return HttpResponseBadRequest("IDs missing")

        if not cand_ids:                                   # empty list → 400
            return HttpResponseBadRequest("No candidate_ids given")

        # Metrics: either from the form, or the usual ones
        metrics = request.GET.getlist("metrics") or DEFAULT_METRICS

        ctx = _context(base_id, cand_ids[0], cand_ids, metrics)      # pass the new list
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
    """Refreshes table + charts when changing candidate or metrics (HTMX)."""
    base = int(request.POST["base_id"])
    cand = int(request.POST["cand_id"])
    metrics = request.POST.getlist("metrics[]") or DEFAULT_METRICS
    cand_ids = [int(v) for v in request.POST.getlist("cand_ids[]") if v.isdigit()]
    ctx = _context(base, cand, cand_ids, metrics)
    return render(request, "dashboard/_dash_body.html", ctx)


# ───────────────── NEW MANUAL SEARCH DASHBOARD VIEWS ──────────────────

@login_required
def player_search(request):
    """Main player search view"""
    from .search_services import get_filter_options
    
    # Get filter options
    filter_options = get_filter_options()
    
    context = {
        'filter_options': filter_options,
    }
    
    return render(request, "dashboard/player_search.html", context)

@login_required
def comparison_dashboard(request):
    """Player comparison dashboard"""
    from .search_services import get_player_details, get_comparison_data
    from apps.agent_service.dashboard_viz_tools import dashboard_radar_single, dashboard_radar_comparison
    
    # Get selected player IDs
    player_ids = request.GET.getlist('player_ids')
    selected_metrics = request.GET.getlist('metrics')
    
    if not player_ids:
        return render(request, "dashboard/comparison.html", {
            'error': 'No players selected'
        })
    
    # Convert to integers
    try:
        player_ids = [int(pid) for pid in player_ids]
    except ValueError:
        return render(request, "dashboard/comparison.html", {
            'error': 'Invalid player IDs'
        })
    
    # Get player data
    players_data = get_player_details(player_ids)
    
    if not players_data:
        return render(request, "dashboard/comparison.html", {
            'error': 'Could not load player data'
        })
    
    # Prepare data for comparison
    comparison_data = get_comparison_data(players_data, selected_metrics)
    
    # Generate chart
    if len(players_data) == 1:
        chart_result = dashboard_radar_single(players_data[0], selected_metrics)
    else:
        chart_result = dashboard_radar_comparison(players_data, selected_metrics)
    
    chart_url = None
    if chart_result.get('attachments') and len(chart_result['attachments']) > 0:
        chart_url = chart_result['attachments'][0]['url']
    
    context = {
        'players': players_data,
        'chart_url': chart_url,
        'selected_metrics': selected_metrics,
        'player_count': len(players_data)
    }
    
    return render(request, "dashboard/comparison.html", context)

@login_required
def search_api(request):
    """API for player search"""
    from .search_services import search_players, build_search_filters, get_all_players, get_filter_options, get_available_metrics
    import json
    
    if request.method == 'GET':
        action = request.GET.get('action')
        
        if action == 'filter_options':
            # Return filter options
            try:
                results = get_filter_options()
                return JsonResponse(results)
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=400)
        
        elif action == 'metrics':
            # Return available metrics
            try:
                results = get_available_metrics()
                return JsonResponse({'metrics': results})
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=400)
        
        else:
            # Return all players for dynamic filtering
            try:
                results = get_all_players()
                return JsonResponse(results)
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=400)
    
    elif request.method == 'POST':
        # Search with filters
        try:
            data = json.loads(request.body)
            filters = build_search_filters(data)
            results = search_players(**filters)
            return JsonResponse(results)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@login_required
def player_profile(request, player_id: int):
    """Simple player profile page with radar and key KPIs."""
    try:
        stats_map = _fetch_stats([player_id])
        player = stats_map.get(player_id)
        if not player:
            return render(request, "dashboard/profile.html", {"error": "Player not found"})

        # Default metrics depending on position (compact set ~12)
        pos = player.get("position") or "MF"
        # Exclude stats already shown in the side table (age, minutes,
        # goals, assists, goals_per90, assists_per90, passes_pct)
        # and favour informative metrics by position.
        metrics_by_pos = {
            "GK": [
                "gk_psxg",
                "gk_pens_allowed",
                "gk_free_kick_goals_against",
                "gk_corner_kick_goals_against",
                "gk_own_goals_against",
                "clearances",
                "blocks",
            ],
            "DF": [
                "tackles",
                "tackles_won",
                "tackles_interceptions",
                "interceptions",
                "blocked_shots",
                "clearances",
                "progressive_passes",
                "progressive_carries",
            ],
            "MF": [
                "expected_goals_per90",
                "expected_assists_per90",
                "goals_assists_per90",
                "progressive_passes",
                "progressive_carries",
                "progressive_passes_received",
                "interceptions",
                "tackles_won",
            ],
            "FW": [
                "expected_goals_per90",
                "expected_goals_assists_per90",
                "goals_assists_per90",
                "progressive_passes_received",
                "progressive_passes",
                "progressive_carries",
            ],
        }
        metrics = metrics_by_pos.get(pos, DEFAULT_METRICS)

        # Radar chart using dashboard tool that accepts metric list (no age)
        radar = dashboard_radar_single(player, metrics)
        radar_url = None
        if radar.get("attachments"):
            radar_url = radar["attachments"][0].get("url")

        # Select compact KPI table (subset)
        kpi_keys = ["age", "minutes", "goals", "assists", "goals_per90", "assists_per90", "passes_pct"]
        kpis = {k: player.get(k) for k in kpi_keys}

        ctx = {
            "player": player,
            "metrics": metrics,
            "radar_url": radar_url,
            "kpis": kpis,
        }
        return render(request, "dashboard/player_profile.html", ctx)
    except Exception as e:
        logger.exception("player_profile error: %s", e)
        return render(request, "dashboard/profile.html", {"error": str(e)})

@login_required
def saved_searches_api(request):
    """API for managing saved searches"""
    import json
    
    if request.method == 'GET':
        search_id = request.GET.get('id')
        
        if search_id:
            # Get a specific search
            try:
                search = SavedSearch.objects.get(id=search_id, user=request.user)
                from .search_services import serialize_saved_search
                return JsonResponse(serialize_saved_search(search))
            except SavedSearch.DoesNotExist:
                return JsonResponse({'error': 'Search not found'}, status=404)
        else:
            # Get all user's saved searches
            searches = SavedSearch.objects.filter(user=request.user)
            from .search_services import serialize_saved_search
            data = [serialize_saved_search(search) for search in searches]
            return JsonResponse({'searches': data})
    
    elif request.method == 'POST':
        # Save new search
        try:
            data = json.loads(request.body)
            
            search = SavedSearch.objects.create(
                user=request.user,
                name=data['name'],
                search_params=data['search_params'],
                selected_players=data['selected_players'],
                selected_metrics=data['selected_metrics']
            )
            
            from .search_services import serialize_saved_search
            return JsonResponse(serialize_saved_search(search))
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    elif request.method == 'DELETE':
        # Delete search
        try:
            data = json.loads(request.body)
            search_id = data['id']
            search = SavedSearch.objects.get(id=search_id, user=request.user)
            search.delete()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)