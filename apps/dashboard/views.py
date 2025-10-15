#from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import FileResponse
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
    radar_comparison_chart,
    pizza_comparison_chart,
    radar_rating_chart
)
from apps.agent_service.dashboard_viz_tools import dashboard_radar_single
from apps.agent_service.utils import compare_stats_to_html_table

import requests
from django.urls import reverse
import json, urllib.parse
from typing import Annotated
from django.db import connection
from django.conf import settings
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import hashlib
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from io import BytesIO
import urllib.request
from PIL import Image

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
    # Use radar_comparison_chart instead of two individual radars
    radar_cmp = radar_comparison_chart(
        player1_name=base_stats["full_name"],
        player2_name=cand_stats["full_name"],
    )

    pizza_cmp = pizza_comparison_chart(
        player1_name=base_stats["full_name"],
        player2_name=cand_stats["full_name"],
        role=None,           # the function detects it by position
    )

    table_html = compare_stats_to_html_table(base_stats, cand_stats)

    players = list(stats_map.values())

    # ── 3) Load player ratings and generate rating radar ─────────────
    base_rating = None
    cand_rating = None
    radar_rating_url = None
    
    try:
        # Import here to avoid circular imports
        import requests
        
        # Get available seasons for ratings
        seasons_response = requests.get("http://api:8001/api/ratings/leagues")
        available_seasons = ["2024-25", "2023-24", "2022-23", "2021-22", "2020-21"]  # Fallback seasons
        
        # Get ratings for base player - try multiple seasons
        base_rating = None
        for season in available_seasons:
            base_rating_response = requests.get(f"http://api:8001/api/ratings/player/{base_id}?season={season}")
            if base_rating_response.status_code == 200:
                base_rating = base_rating_response.json()
                print(f"Found base player rating for season: {season}")
                break
        
        # Get ratings for candidate player - try multiple seasons
        cand_rating = None
        for season in available_seasons:
            cand_rating_response = requests.get(f"http://api:8001/api/ratings/player/{cand_id}?season={season}")
            if cand_rating_response.status_code == 200:
                cand_rating = cand_rating_response.json()
                print(f"Found candidate player rating for season: {season}")
                break
        
        # Generate rating radar if both ratings exist
        if base_rating and cand_rating:
            from apps.agent_service.viz_tools import radar_rating_comparison_chart
            radar_rating_result = radar_rating_comparison_chart(
                player1_name=base_stats["full_name"],
                player2_name=cand_stats["full_name"],
                rating_data1=base_rating,
                rating_data2=cand_rating
            )
            radar_rating_url = radar_rating_result
            print(f"""
            base_rating: {base_rating}
            cand_rating: {cand_rating}
            """)
            
    except Exception as e:
        print(f"Error loading ratings: {e}")
        # Continue without ratings

    return {
        "base_id": base_id,
        "cand_id": cand_id,
        "cand_ids": cand_ids,
        "players": players,
        "base_player": base_stats,
        "cand_player": cand_stats,
        "base_rating": base_rating,
        "cand_rating": cand_rating,
        "metrics": metrics,
        "radar_cmp": radar_cmp["attachments"][0]["url"],
        "pizza_cmp":  pizza_cmp["attachments"][0]["url"],
        "table_html": table_html,
        "radar_rating_url": radar_rating_url,
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
    
    # Load FIFA-style ratings for players and build ratings radar (1-3 players)
    ratings_map = {}
    radar_rating_url = None
    try:
        seasons_try = ["2024-25", "2023-24", "2022-23", "2021-22", "2020-21", "2019-20", "2018-19", "2017-18", "2016-17", "2015-16", "2014-15", "2013-14", "2012-13"]
        
        for p in players_data:
            pid = p.get('id') or p.get('player_id') or p.get('pk')
            if not pid:
                continue
            rating = None
            for season in seasons_try:
                r = requests.get(f"{API_HOST}/api/ratings/player/{pid}?season={season}", timeout=10)
                if r.status_code == 200:
                    rating = r.json()
                    break
            if rating:
                ratings_map[pid] = rating

        # Build multi radar if we have at least one rating
        from apps.agent_service.viz_tools import radar_rating_multi_chart
        players_for_radar = []
        for p in players_data:
            pid = p.get('id')
            rating = ratings_map.get(pid)
            if not rating:
                continue
            name = p.get('full_name') or p.get('name')
            pos = p.get('position')
            players_for_radar.append((name, rating, pos))
        if players_for_radar:
            radar_rating_url = radar_rating_multi_chart(players_for_radar)
    except Exception as e:
        logger.warning(f"comparison_dashboard ratings load error: {e}")

    context = {
        'players': players_data,
        'chart_url': chart_url,
        'selected_metrics': selected_metrics,
        'player_count': len(players_data),
        'ratings_map': ratings_map,
        'radar_rating_url': radar_rating_url
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

        # Fetch player rating data from API
        player_rating = None
        team_rating = None
        radar_rating_data = None
        
        try:
            # Get player rating
            rating_response = requests.get(
                f"{API_HOST}/api/ratings/player/{player_id}",
                timeout=10
            )
            if rating_response.status_code == 200:
                player_rating = rating_response.json()
            
            # Get team rating
            if player.get("club"):
                team_response = requests.get(
                    f"{API_HOST}/api/ratings/team/{player['club']}",
                    timeout=10
                )
                if team_response.status_code == 200:
                    team_rating = team_response.json()
            
            # Get radar rating data
            radar_response = requests.get(
                f"{API_HOST}/api/ratings/player/{player_id}/radar",
                timeout=10
            )
            if radar_response.status_code == 200:
                radar_rating_data = radar_response.json()
                
        except Exception as e:
            logger.warning(f"Could not fetch rating data: {e}")

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

        # Radar clásico (viz_tools) con máximos fijos predefinidos
        radar = radar_chart(
            player_name=player["full_name"],
            stats=player,
            team=player["club"],
            position=pos,
            nationality=player.get("nationality", ""),
        )
        radar_url = None
        if radar.get("attachments"):
            radar_url = radar["attachments"][0].get("url")
        
        # Generate ratings radar if rating data is available
        radar_rating_url = None
        if player_rating and radar_rating_data:
            rating_attributes = {
                "ATT": player_rating.get("att", 50),
                "PLY": player_rating.get("ply", 50),
                "DEF": player_rating.get("def_rating", 50),
                "CTR": player_rating.get("ctr", 50),
                "PHY": player_rating.get("phy", 50),
            }
            if player_rating.get("gkp"):
                rating_attributes["GKP"] = player_rating.get("gkp", 50)
            
            radar_rating = radar_rating_chart(
                player_name=player["full_name"],
                rating_data=rating_attributes,
                team=player["club"],
                position=pos,
                nationality=player.get("nationality", ""),
            )
            if radar_rating:
                radar_rating_url = radar_rating

        # Select KPI table metrics that don't overlap with radar
        # Radar has: Min/Games, Games_90s, Goals, Asist, G+A, %Pass, Tackles Won, Interceptions, Challenges, Progressive Passes, Progressive Passes Received
        kpi_keys_by_pos = {
            "GK": ["age", "minutes", "gk_psxg", "gk_goals_against", "gk_pens_allowed", "clearances", "blocks"],
            "DF": ["age", "minutes", "expected_goals_per90", "expected_assists_per90", "tackles", "tackles_interceptions", "blocked_shots", "clearances"],
            "MF": ["age", "minutes", "expected_goals_per90", "expected_assists_per90", "goals_assists_per90", "progressive_carries", "key_passes", "through_balls"],
            "FW": ["age", "minutes", "expected_goals_per90", "expected_goals_assists_per90", "goals_assists_per90", "progressive_carries", "key_passes", "through_balls"],
        }
        kpi_keys = kpi_keys_by_pos.get(pos, ["age", "minutes", "expected_goals_per90", "expected_assists_per90", "goals_assists_per90"])
        kpis = {k: player.get(k) for k in kpi_keys if player.get(k) is not None}

        ctx = {
            "player": player,
            "metrics": metrics,
            "radar_url": radar_url,
            "radar_rating_url": radar_rating_url,
            "kpis": kpis,
            "player_rating": player_rating,
            "team_rating": team_rating,
            "radar_rating_data": radar_rating_data,
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


@login_required
def player_history_api(request, player_name: str):
    """Return per-season historical stats for a player, as stored in player_history.
    Response: [{season, team, league, team_logo, minutes, ...metrics...}] sorted by season asc.
    """
    try:
        # Minimal set of columns used in charts; extendable
        desired_columns = [
            'player','season','team','league','team_logo','minutes','minutes_90s','games','games_starts',
            'goals','assists','expected_goals','expected_assists',
            'progressive_carries','progressive_passes','progressive_passes_received',
            'goals_per90','assists_per90','goals_assists_per90','expected_goals_per90','expected_assists_per90',
            'passes_completed','passes','passes_pct',
            'tackles','tackles_won','interceptions','blocks','clearances',
            'gk_goals_against','gk_pens_allowed','gk_psxg','gk_psnpxg_per_shot_on_target_against'
        ]
        with connection.cursor() as cur:
            # Discover existing columns to avoid selecting non-existent GK fields on some datasets
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'player_history'
                """
            )
            existing_cols = {row[0] for row in cur.fetchall()}
            # Keep order from desired_columns, filter by existence
            columns = [c for c in desired_columns if c in existing_cols]
            # Ensure mandatory keys are present
            for mandatory in ['player','season','team','league','team_logo']:
                if mandatory not in columns and mandatory in existing_cols:
                    columns.insert(0, mandatory)
            col_select = ', '.join(columns)

            # Try exact lower match first; if empty, fallback to unaccent/ILIKE if extension exists
            cur.execute(
                f"""
                SELECT {col_select}
                FROM player_history
                WHERE lower(player) = lower(%s)
                ORDER BY season ASC
                """,
                [player_name],
            )
            rows = cur.fetchall()
            # Build mapping using cursor description
            cols = [c[0] for c in cur.description]
        history = [dict(zip(cols, row)) for row in rows]
        if not history:
            try:
                with connection.cursor() as cur:
                    # ensure unaccent is available (no-op if already)
                    cur.execute("CREATE EXTENSION IF NOT EXISTS unaccent;")
                    cur.execute(
                        f"""
                        SELECT {col_select}
                        FROM player_history
                        WHERE unaccent(lower(player)) = unaccent(lower(%s))
                        ORDER BY season ASC
                        """,
                        [player_name],
                    )
                    rows = cur.fetchall()
                    cols = [c[0] for c in cur.description]
                    history = [dict(zip(cols, row)) for row in rows]
            except Exception:
                history = []
        if not history:
            with connection.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT {col_select}
                    FROM player_history
                    WHERE lower(player) LIKE '%%' || lower(%s) || '%%'
                    ORDER BY season ASC
                    """,
                    [player_name],
                )
                rows = cur.fetchall()
                cols = [c[0] for c in cur.description]
                history = [dict(zip(cols, row)) for row in rows]
        return JsonResponse({"history": history})
    except Exception as e:
        logger.exception("player_history_api error: %s", e)
        return JsonResponse({"error": str(e)}, status=400)


@login_required
def player_history_by_id_api(request, player_id: int):
    """Same as player_history_api but by joining players.id to history.player name."""
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT full_name FROM players WHERE id = %s", [player_id])
            row = cur.fetchone()
            if not row:
                return JsonResponse({"history": []})
            name = row[0]
        # Reuse name-based endpoint logic
        return player_history_api(request, name)
    except Exception as e:
        logger.exception("player_history_by_id_api error: %s", e)
        return JsonResponse({"error": str(e)}, status=400)


def _fetch_history_rows(player_name: str) -> list[dict]:
    """Return per-season rows from player_history for a given player name."""
    with connection.cursor() as cur:
        # Discover existing columns
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'player_history'
            """
        )
        existing_cols = {row[0] for row in cur.fetchall()}
        desired = [
            'player','season','team','league','team_logo','minutes','minutes_90s','games','games_starts',
            'goals','assists','expected_goals','expected_assists',
            'progressive_carries','progressive_passes','progressive_passes_received',
            'goals_per90','assists_per90','goals_assists_per90','expected_goals_per90','expected_assists_per90',
            'passes_completed','passes','passes_pct',
            'tackles','tackles_won','interceptions','blocks','clearances',
            'gk_goals_against','gk_pens_allowed','gk_psxg','gk_psnpxg_per_shot_on_target_against'
        ]
        cols = [c for c in desired if c in existing_cols]
        for mandatory in ['player','season','team']:
            if mandatory not in cols and mandatory in existing_cols:
                cols.insert(0, mandatory)
        col_select = ', '.join(cols)

        cur.execute(
            f"""
            SELECT {col_select}
            FROM player_history
            WHERE lower(player) = lower(%s)
            ORDER BY season ASC
            """,
            [player_name],
        )
        rows = cur.fetchall()
        names = [c[0] for c in cur.description]
        return [dict(zip(names, r)) for r in rows]


@login_required
def history_chart_api(request):
    """Generate and return a URL to a PNG line chart for the given metric.
    Query params: id (player_id), metric (col name), context (0/1).
    """
    try:
        player_id = int(request.GET.get('id', '0'))
        metric = request.GET.get('metric')
        show_context = request.GET.get('context', '1') in {'1', 'true', 'True'}
        if not player_id or not metric:
            return JsonResponse({'error': 'missing id or metric'}, status=400)

        # Resolve player name
        with connection.cursor() as cur:
            cur.execute("SELECT full_name FROM players WHERE id = %s", [player_id])
            row = cur.fetchone()
            if not row:
                return JsonResponse({'error': 'player not found'}, status=404)
            name = row[0]

        history = _fetch_history_rows(name)
        if not history:
            return JsonResponse({'error': 'no history'}, status=404)

        seasons = [r['season'] for r in history]
        y_raw = [r.get(metric) for r in history]
        y = [np.nan if v in (None, '') else float(v) for v in y_raw]

        # Prepare figure
        fig, ax = plt.subplots(figsize=(8, 3))
        ax.plot(range(len(seasons)), y, marker='o', linewidth=2, markersize=4)
        ax.set_xticks(range(len(seasons)))
        ax.set_xticklabels(seasons, rotation=0, fontsize=8)
        ax.set_ylabel(metric)
        ax.grid(True, axis='y', alpha=0.2)

        # Club context bands with team logos
        if show_context and 'team' in history[0]:
            start = 0
            colors = [(0.2, 0.4, 0.8, 0.12), (0.8, 0.4, 0.2, 0.12)]  # Alternating blue/orange subtle
            color_idx = 0
            ylim = ax.get_ylim()
            y_range = ylim[1] - ylim[0]
            
            for i in range(1, len(history)+1):
                changed = i == len(history) or history[i]['team'] != history[i-1]['team']
                if changed:
                    # Background band
                    ax.axvspan(start-0.5, i-0.5, color=colors[color_idx % 2], zorder=0)
                    
                    # Try to add team logo
                    mid_x = (start + i - 1) / 2
                    logo_url = history[start].get('team_logo')
                    
                    if logo_url and logo_url.strip():
                        try:
                            # Download and add logo
                            with urllib.request.urlopen(logo_url, timeout=2) as response:
                                img_data = response.read()
                            img = Image.open(BytesIO(img_data)).convert('RGBA')
                            
                            # Calculate logo size based on band width
                            band_width = i - start
                            logo_zoom = min(0.15 * band_width, 0.35)  # Scale with band width, max 0.35
                            
                            # Position logo in vertical center
                            logo_y = ylim[0] + (y_range * 0.5)  # Center vertically
                            
                            imagebox = OffsetImage(img, zoom=logo_zoom, alpha=0.6)
                            ab = AnnotationBbox(imagebox, (mid_x, logo_y), 
                                              frameon=False, zorder=1)
                            ax.add_artist(ab)
                        except Exception:
                            # Fallback: show team name if logo fails
                            team_name = history[start]['team']
                            ax.text(mid_x, ylim[1] - (y_range * 0.06), team_name[:15], 
                                   ha='center', va='top', fontsize=7, alpha=0.5)
                    
                    start = i
                    color_idx += 1

        ax.margins(x=0.02)

        # Save under media/charts
        charts_dir = Path(settings.MEDIA_ROOT) / 'charts'
        charts_dir.mkdir(parents=True, exist_ok=True)
        key = f"{player_id}|{metric}|{int(show_context)}|{seasons[0]}|{seasons[-1]}"
        h = hashlib.md5(key.encode()).hexdigest()[:12]
        out_path = charts_dir / f"history_{player_id}_{metric}_{h}.png"
        fig.tight_layout()
        fig.savefig(out_path, dpi=150, bbox_inches='tight')
        plt.close(fig)

        # Return the image file directly
        return FileResponse(open(out_path, 'rb'), content_type='image/png')
    except Exception as e:
        logger.exception('history_chart_api error: %s', e)
        return JsonResponse({'error': str(e)}, status=400)


def generate_history_chart_file(player_id: int, metric: str, show_context: bool = True) -> Path:
    """Internal helper to generate history chart file and return its Path."""
    with connection.cursor() as cur:
        cur.execute("SELECT full_name FROM players WHERE id = %s", [player_id])
        row = cur.fetchone()
        if not row:
            raise ValueError('player not found')
        name = row[0]

    history = _fetch_history_rows(name)
    if not history:
        raise ValueError('no history')

    seasons = [r['season'] for r in history]
    y_raw = [r.get(metric) for r in history]
    y = [np.nan if v in (None, '') else float(v) for v in y_raw]

    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(range(len(seasons)), y, marker='o', linewidth=2, markersize=4)
    ax.set_xticks(range(len(seasons)))
    ax.set_xticklabels(seasons, rotation=0, fontsize=8)
    ax.set_ylabel(metric)
    ax.grid(True, axis='y', alpha=0.2)

    if show_context and 'team' in history[0]:
        start = 0
        colors = [(0.2, 0.4, 0.8, 0.12), (0.8, 0.4, 0.2, 0.12)]
        color_idx = 0
        ylim = ax.get_ylim()
        y_range = ylim[1] - ylim[0]
        for i in range(1, len(history)+1):
            changed = i == len(history) or history[i]['team'] != history[i-1]['team']
            if changed:
                ax.axvspan(start-0.5, i-0.5, color=colors[color_idx % 2], zorder=0)
                mid_x = (start + i - 1) / 2
                logo_url = history[start].get('team_logo')
                if logo_url and logo_url.strip():
                    try:
                        with urllib.request.urlopen(logo_url, timeout=2) as response:
                            img_data = response.read()
                        img = Image.open(BytesIO(img_data)).convert('RGBA')
                        imagebox = OffsetImage(img, zoom=0.2, alpha=0.6)
                        ab = AnnotationBbox(imagebox, (mid_x, ylim[0] + (y_range * 0.5)), frameon=False, zorder=1)
                        ax.add_artist(ab)
                    except Exception:
                        pass
                start = i
                color_idx += 1

    ax.margins(x=0.02)
    charts_dir = Path(settings.MEDIA_ROOT) / 'charts'
    charts_dir.mkdir(parents=True, exist_ok=True)
    key = f"{player_id}|{metric}|{int(show_context)}|{seasons[0]}|{seasons[-1]}"
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    out_path = charts_dir / f"history_{player_id}_{metric}_{h}.png"
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    return out_path

@login_required
def history_chart_comparison_api(request):
    """Generate and return a PNG line chart comparing two players for the given metric.
    Query params: id1 (player_id), id2 (player_id), metric (col name).
    No club context in comparison charts to keep them clean.
    """
    try:
        player_id1 = int(request.GET.get('id1', '0'))
        player_id2 = int(request.GET.get('id2', '0'))
        metric = request.GET.get('metric')
        if not player_id1 or not player_id2 or not metric:
            return JsonResponse({'error': 'missing id1, id2 or metric'}, status=400)

        # Resolve player names
        with connection.cursor() as cur:
            cur.execute("SELECT id, full_name FROM players WHERE id IN (%s, %s)", [player_id1, player_id2])
            rows = cur.fetchall()
            if len(rows) < 2:
                return JsonResponse({'error': 'one or both players not found'}, status=404)
            names_map = {row[0]: row[1] for row in rows}
        
        name1 = names_map[player_id1]
        name2 = names_map[player_id2]

        history1 = _fetch_history_rows(name1)
        history2 = _fetch_history_rows(name2)
        
        if not history1 or not history2:
            return JsonResponse({'error': 'no history for one or both players'}, status=404)

        # Extract data
        seasons1 = [r['season'] for r in history1]
        y1_raw = [r.get(metric) for r in history1]
        y1 = [np.nan if v in (None, '') else float(v) for v in y1_raw]

        seasons2 = [r['season'] for r in history2]
        y2_raw = [r.get(metric) for r in history2]
        y2 = [np.nan if v in (None, '') else float(v) for v in y2_raw]

        # Use all unique seasons sorted
        all_seasons = sorted(set(seasons1 + seasons2))
        
        # Prepare figure
        fig, ax = plt.subplots(figsize=(8, 3))
        
        # Create indices for each player based on all_seasons
        indices1 = [all_seasons.index(s) for s in seasons1]
        indices2 = [all_seasons.index(s) for s in seasons2]
        
        # unified palette with dashboards (base green, candidate magenta)
        ax.plot(indices1, y1, marker='o', linewidth=2, markersize=4, 
                label=name1, color='#01c49d', alpha=0.9)
        ax.plot(indices2, y2, marker='s', linewidth=2, markersize=4, 
                label=name2, color='#d80499', alpha=0.9)
        
        ax.set_xticks(range(len(all_seasons)))
        ax.set_xticklabels(all_seasons, rotation=45, fontsize=7, ha='right')
        ax.set_ylabel(metric, fontsize=9)
        ax.grid(True, axis='y', alpha=0.2)
        ax.legend(loc='upper left', fontsize=8, framealpha=0.9)
        ax.margins(x=0.02)

        # Save under media/charts
        charts_dir = Path(settings.MEDIA_ROOT) / 'charts'
        charts_dir.mkdir(parents=True, exist_ok=True)
        key = f"{player_id1}|{player_id2}|{metric}|{all_seasons[0]}|{all_seasons[-1]}"
        h = hashlib.md5(key.encode()).hexdigest()[:12]
        out_path = charts_dir / f"comparison_{player_id1}_{player_id2}_{metric}_{h}.png"
        fig.tight_layout()
        fig.savefig(out_path, dpi=150, bbox_inches='tight')
        plt.close(fig)

        # Return the image file directly
        return FileResponse(open(out_path, 'rb'), content_type='image/png')
    except Exception as e:
        logger.exception('history_chart_comparison_api error: %s', e)
        return JsonResponse({'error': str(e)}, status=500)


def generate_history_chart_comparison_file(player_id1: int, player_id2: int, metric: str) -> Path:
    """Internal helper to generate comparison chart file and return its Path."""
    with connection.cursor() as cur:
        cur.execute("SELECT id, full_name FROM players WHERE id IN (%s, %s)", [player_id1, player_id2])
        rows = cur.fetchall()
        if len(rows) < 2:
            raise ValueError('one or both players not found')
        names_map = {row[0]: row[1] for row in rows}
    history1 = _fetch_history_rows(names_map[player_id1])
    history2 = _fetch_history_rows(names_map[player_id2])
    if not history1 or not history2:
        raise ValueError('no history for one or both players')

    seasons1 = [r['season'] for r in history1]
    y1 = [np.nan if (v:=(r.get(metric))) in (None, '') else float(v) for r in history1]
    seasons2 = [r['season'] for r in history2]
    y2 = [np.nan if (v:=(r.get(metric))) in (None, '') else float(v) for r in history2]
    all_seasons = sorted(set(seasons1 + seasons2))
    indices1 = [all_seasons.index(s) for s in seasons1]
    indices2 = [all_seasons.index(s) for s in seasons2]

    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(indices1, y1, marker='o', linewidth=2, markersize=4, label=names_map[player_id1], color='#3b82f6', alpha=0.8)
    ax.plot(indices2, y2, marker='s', linewidth=2, markersize=4, label=names_map[player_id2], color='#ef4444', alpha=0.8)
    ax.set_xticks(range(len(all_seasons)))
    ax.set_xticklabels(all_seasons, rotation=45, fontsize=7, ha='right')
    ax.set_ylabel(metric, fontsize=9)
    ax.grid(True, axis='y', alpha=0.2)
    ax.legend(loc='upper left', fontsize=8, framealpha=0.9)
    ax.margins(x=0.02)
    charts_dir = Path(settings.MEDIA_ROOT) / 'charts'
    charts_dir.mkdir(parents=True, exist_ok=True)
    key = f"{player_id1}|{player_id2}|{metric}|{all_seasons[0]}|{all_seasons[-1]}"
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    out_path = charts_dir / f"comparison_{player_id1}_{player_id2}_{metric}_{h}.png"
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    return out_path


@login_required
def history_chart_multi_api(request):
    """Generate multi-line historical chart for up to 3 players.
    Query params: ids (comma separated), metric (col name)
    """
    try:
        ids_param = request.GET.get('ids', '')
        metric = request.GET.get('metric')
        if not ids_param or not metric:
            return JsonResponse({'error': 'missing ids or metric'}, status=400)
        id_list = [int(x) for x in ids_param.split(',') if x.strip().isdigit()][:3]
        if len(id_list) == 0:
            return JsonResponse({'error': 'no valid ids'}, status=400)

        # Resolve names
        with connection.cursor() as cur:
            cur.execute(
                f"SELECT id, full_name FROM players WHERE id = ANY(%s)", [id_list]
            )
            rows = cur.fetchall()
            if len(rows) < len(id_list):
                # proceed with available
                pass
            id_to_name = {r[0]: r[1] for r in rows}

        # Gather histories
        histories = []
        for pid in id_list:
            name = id_to_name.get(pid)
            if not name:
                continue
            hist = _fetch_history_rows(name)
            if hist:
                seasons = [r['season'] for r in hist]
                y = [np.nan if (v:=(r.get(metric))) in (None, '') else float(v) for r in hist]
                histories.append((pid, name, seasons, y))

        if not histories:
            return JsonResponse({'error': 'no history'}, status=404)

        # Build unified seasons
        all_seasons = sorted(set(s for _,_,seas,_ in histories for s in seas))

        # unified palette with dashboards: green, magenta, blue
        colors = ['#01c49d', '#d80499', '#3b82f6']
        markers = ['o', 's', 'D']
        fig, ax = plt.subplots(figsize=(8, 3))
        for idx, (pid, name, seasons, y_vals) in enumerate(histories):
            indices = [all_seasons.index(s) for s in seasons]
            ax.plot(indices, y_vals, marker=markers[idx%len(markers)], linewidth=2, markersize=4,
                    label=name, color=colors[idx%len(colors)], alpha=0.9)

        ax.set_xticks(range(len(all_seasons)))
        ax.set_xticklabels(all_seasons, rotation=45, fontsize=7, ha='right')
        ax.set_ylabel(metric, fontsize=9)
        ax.grid(True, axis='y', alpha=0.2)
        ax.legend(loc='upper left', fontsize=8, framealpha=0.9)
        ax.margins(x=0.02)

        charts_dir = Path(settings.MEDIA_ROOT) / 'charts'
        charts_dir.mkdir(parents=True, exist_ok=True)
        key = f"{'-'.join(map(str,id_list))}|{metric}|{all_seasons[0]}|{all_seasons[-1]}"
        h = hashlib.md5(key.encode()).hexdigest()[:12]
        out_path = charts_dir / f"multi_{'_'.join(map(str,id_list))}_{metric}_{h}.png"
        fig.tight_layout()
        fig.savefig(out_path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        return FileResponse(open(out_path, 'rb'), content_type='image/png')
    except Exception as e:
        logger.exception('history_chart_multi_api error: %s', e)
        return JsonResponse({'error': str(e)}, status=500)