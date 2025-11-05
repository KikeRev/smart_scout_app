"""
search_services.py - Services for the manual player search system

Functions for:
- Player search with filters
- Player data retrieval
- Saved search management
"""

import requests
from typing import Dict, List, Any, Optional
import json

# Import Django settings only when available
try:
    from django.conf import settings
    DJANGO_AVAILABLE = True
except ImportError:
    DJANGO_AVAILABLE = False
    settings = None

# Base URL for the players API
API_BASE_URL = "http://api:8001"  # Adjust according to your configuration

def search_players(
    query: str = "",
    leagues: List[str] = None,
    clubs: List[str] = None,
    positions: List[str] = None,
    nationalities: List[str] = None,
    age_min: int = None,
    age_max: int = None,
    min_minutes: int = None,
    page: int = 1,
    per_page: int = 20
) -> Dict[str, Any]:
    """
    Searches players with applied filters (all filters are AND conditions)
    
    Parameters
    ----------
    query : str
        Search term by name
    leagues : List[str]
        List of leagues to filter
    clubs : List[str]
        List of clubs to filter
    positions : List[str]
        List of positions to filter
    nationalities : List[str]
        List of nationalities to filter
    age_min : int
        Minimum age
    age_max : int
        Maximum age
    min_minutes : int
        Minimum minutes played
    page : int
        Current page
    per_page : int
        Players per page
        
    Returns
    -------
    Dict[str, Any]
        Search results with pagination
    """
    try:
        # Build payload for server-side search (efficient)
        # All filters are applied as AND conditions
        payload = {
            "query": query if query else None,
            "positions": positions if positions else None,
            "leagues": leagues if leagues else None,
            "clubs": clubs if clubs else None,
            "nationalities": nationalities if nationalities else None,
            "age_min": age_min,
            "age_max": age_max,
            "min_minutes": min_minutes,
            "page": page,
            "per_page": per_page,
            "order": "minutes_desc",
        }
        response = requests.post(f"{API_BASE_URL}/players/search", json=payload, timeout=180)
        response.raise_for_status()
        return response.json()
        
    except requests.exceptions.RequestException as e:
        # In case of error, return empty structure
        return {
            "players": [],
            "total": 0,
            "page": page,
            "per_page": per_page,
            "total_pages": 0,
            "error": str(e)
        }

def get_player_details(player_ids: List[int]) -> List[Dict[str, Any]]:
    """
    Gets player details by their IDs
    
    Parameters
    ----------
    player_ids : List[int]
        List of player IDs
        
    Returns
    -------
    List[Dict[str, Any]]
        List of player data
    """
    try:
        # Use dedicated details endpoint for specific IDs
        response = requests.post(
            f"{API_BASE_URL}/players/details",
            json={"player_ids": player_ids},
            timeout=60,
        )
        response.raise_for_status()
        return response.json()
        
    except (requests.exceptions.RequestException, requests.exceptions.ConnectionError) as e:
        print(f"Error in get_player_details: {e}")
        # Retry once with shorter timeout
        try:
            response = requests.get(f"{API_BASE_URL}/players/all", timeout=60)
            response.raise_for_status()
            all_players = response.json().get('players', [])
            filtered_players = [p for p in all_players if p.get('id') in player_ids]
            return filtered_players
        except:
            return []

def get_all_players() -> Dict[str, Any]:
    """
    Gets all players from the database for dynamic filtering
    
    Returns
    -------
    Dict[str, Any]
        List of all players with their data
    """
    try:
        response = requests.get(f"{API_BASE_URL}/players/all", timeout=120)
        response.raise_for_status()
        
        return response.json()
        
    except requests.exceptions.RequestException as e:
        # Fallback: get players in batches
        try:
            # Get all players instead of using /players/search without query
            response = requests.get(f"{API_BASE_URL}/players/all", params={"limit": 1000}, timeout=90)
            response.raise_for_status()
            return response.json()
        except:
            return {"players": [], "error": str(e)}

def get_filter_options() -> Dict[str, List[str]]:
    """
    Gets available options for filters from the database
    
    Returns
    -------
    Dict[str, List[str]]
        Dictionary with options per filter
    """
    try:
        # Use FastAPI endpoint with dependent filters (all optional)
        params = {}
        # In this context we don't have current selections; leave empty
        response = requests.get(f'{API_BASE_URL}/players/filter-options', params=params, timeout=180)
        if response.status_code == 200:
            return response.json()
        else:
            return get_filter_options_fallback()
        
    except Exception as e:
        return get_filter_options_fallback()

def get_filter_options_fallback() -> Dict[str, List[str]]:
    """
    Fallback to get filter options from Django
    """
    try:
        # Get all players to extract unique options
        all_players = get_all_players()
        players = all_players.get('players', [])
        
        # Extract unique values for each filter
        leagues = list(set([p.get('league', '') for p in players if p.get('league')]))
        clubs = list(set([p.get('club', '') for p in players if p.get('club')]))
        positions = list(set([p.get('position', '') for p in players if p.get('position')]))
        nationalities = list(set([p.get('nationality', '') for p in players if p.get('nationality')]))
        
        return {
            "leagues": sorted(leagues),
            "clubs": sorted(clubs),
            "positions": sorted(positions),
            "nationalities": sorted(nationalities)
        }
        
    except Exception as e:
        # Return default options if there's an error
        return {
            "leagues": ["La Liga", "Premier League", "Serie A", "Bundesliga", "Ligue 1"],
            "clubs": ["Real Madrid", "Barcelona", "Atletico Madrid", "Manchester City", "Liverpool"],
            "positions": ["GK", "DF", "MF", "FW"],
            "nationalities": ["Spain", "Argentina", "Brazil", "France", "Germany"]
        }

def get_comparison_data(players: List[Dict[str, Any]], metrics: List[str] = None) -> Dict[str, Any]:
    """
    Prepares data for player comparison
    
    Parameters
    ----------
    players : List[Dict[str, Any]]
        List of player data
    metrics : List[str]
        List of selected metrics
        
    Returns
    -------
    Dict[str, Any]
        Prepared data for comparison
    """
    if not players:
        return {"error": "No players to compare"}
    
    if len(players) > 3:
        return {"error": "Maximum 3 players to compare"}
    
    # If no metrics specified, use defaults
    if not metrics:
        metrics = ['age', 'goals', 'assists', 'minutes_90s', 'goals_per90']
    
    # Prepare comparison data
    comparison_data = {
        "players": players,
        "metrics": metrics,
        "chart_type": "radar_comparison" if len(players) > 1 else "radar_single",
        "player_count": len(players)
    }
    
    return comparison_data

def build_search_filters(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Builds search filters from request data (all filters are AND conditions)
    
    Parameters
    ----------
    request_data : Dict[str, Any]
        User request data
        
    Returns
    -------
    Dict[str, Any]
        Built filters
    """
    filters = {}
    
    # Text search
    query = request_data.get('query')
    if query and query.strip():
        filters['query'] = query.strip()
    
    # List filters - only include if list is not empty
    for filter_name in ['leagues', 'clubs', 'positions', 'nationalities']:
        value = request_data.get(filter_name)
        if value and isinstance(value, list) and len(value) > 0:
            filters[filter_name] = value
    
    # Numeric filters - only include if not None
    for filter_name in ['age_min', 'age_max', 'min_minutes']:
        value = request_data.get(filter_name)
        if value is not None:
            try:
                filters[filter_name] = int(value)
            except (ValueError, TypeError):
                pass
    
    # Pagination
    filters['page'] = int(request_data.get('page', 1))
    filters['per_page'] = int(request_data.get('per_page', 20))
    
    return filters

def serialize_player_for_card(player: Dict[str, Any]) -> Dict[str, Any]:
    """
    Serializes a player for card display
    
    Parameters
    ----------
    player : Dict[str, Any]
        Player data
        
    Returns
    -------
    Dict[str, Any]
        Serialized data for the card
    """
    return {
        "id": player.get("id"),
        "full_name": player.get("full_name", "N/A"),
        "club": player.get("club", "N/A"),
        "nationality": player.get("nationality", "N/A"),
        "age": player.get("age", "N/A"),
        "position": player.get("position", "N/A"),
        "team_logo": player.get("team_logo", ""),
        "minutes": player.get("minutes", 0),
        "goals": player.get("goals", 0),
        "assists": player.get("assists", 0)
    }

def get_available_metrics() -> List[str]:
    """
    Gets all available metrics from the database
    
    Returns
    -------
    List[str]
        List of available metrics
    """
    try:
        # Get an example player to see what metrics are available
        response = requests.get(f"{API_BASE_URL}/players/all", params={"limit": 1}, timeout=90)
        response.raise_for_status()
        data = response.json()
        
        if data.get('players') and len(data['players']) > 0:
            player = data['players'][0]
            # Exclude fields that are not metrics
            exclude_fields = {'id', 'full_name', 'club', 'nationality', 'age', 'position', 'team_logo', 'feature_vector'}
            metrics = [key for key in player.keys() if key not in exclude_fields]
            return sorted(metrics)
        
        return []
        
    except Exception as e:
        # All available metrics by default if there's an error
        return [
            # Basic metrics
            'age', 'minutes', 'minutes_90s',
            
            # Goals and assists
            'goals', 'assists', 'goals_per90', 'assists_per90', 'goals_assists_per90',
            
            # Expected Goals
            'expected_goals', 'expected_assists', 'expected_goals_per90', 'expected_assists_per90',
            'expected_goals_assists_per90', 'no_penalty_expected_goals_plus_expected_assists',
            
            # Passes
            'passes_completed', 'passes', 'passes_pct', 'passes_progressive_distance',
            'passes_completed_long', 'passes_long', 'passes_pct_long',
            'progressive_passes', 'progressive_passes_received',
            
            # Dribbles and carries
            'progressive_carries',
            
            # Defensive
            'tackles', 'tackles_won', 'challenge_tackles', 'challenges', 'challenge_tackles_pct',
            'challenges_lost', 'blocks', 'blocked_shots', 'blocked_passes',
            'interceptions', 'tackles_interceptions', 'clearances', 'errors',
            
            # Goalkeepers
            'gk_goals_against', 'gk_pens_allowed', 'gk_free_kick_goals_against',
            'gk_corner_kick_goals_against', 'gk_own_goals_against', 'gk_psxg',
            'gk_psnpxg_per_shot_on_target_against'
        ]

def serialize_saved_search(search) -> Dict[str, Any]:
    """
    Serializes a saved search
    
    Parameters
    ----------
    search : SavedSearch
        Saved search instance
        
    Returns
    -------
    Dict[str, Any]
        Serialized search data
    """
    return {
        "id": search.id,
        "name": search.name,
        "search_params": search.search_params,
        "selected_players": search.selected_players,
        "selected_metrics": search.selected_metrics,
        "created_at": search.created_at.isoformat(),
        "updated_at": search.updated_at.isoformat()
    }
