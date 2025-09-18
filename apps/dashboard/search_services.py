"""
search_services.py - Servicios para el sistema de búsqueda manual de jugadores

Funciones para:
- Búsqueda de jugadores con filtros
- Obtención de datos de jugadores
- Gestión de búsquedas guardadas
"""

import requests
from typing import Dict, List, Any, Optional
import json

# Import Django settings solo cuando esté disponible
try:
    from django.conf import settings
    DJANGO_AVAILABLE = True
except ImportError:
    DJANGO_AVAILABLE = False
    settings = None

# URL base de la API de jugadores
API_BASE_URL = "http://api:8001"  # Ajustar según tu configuración

def search_players(
    query: str = "",
    leagues: List[str] = None,
    clubs: List[str] = None,
    positions: List[str] = None,
    age_min: int = None,
    age_max: int = None,
    min_minutes: int = None,
    page: int = 1,
    per_page: int = 20
) -> Dict[str, Any]:
    """
    Busca jugadores con filtros aplicados
    
    Parameters
    ----------
    query : str
        Término de búsqueda por nombre
    leagues : List[str]
        Lista de ligas a filtrar
    clubs : List[str]
        Lista de clubes a filtrar
    positions : List[str]
        Lista de posiciones a filtrar
    age_min : int
        Edad mínima
    age_max : int
        Edad máxima
    min_minutes : int
        Minutos mínimos jugados
    page : int
        Página actual
    per_page : int
        Jugadores por página
        
    Returns
    -------
    Dict[str, Any]
        Resultados de la búsqueda con paginación
    """
    try:
        # Construir parámetros de búsqueda
        search_params = {
            "query": query,
            "page": page,
            "per_page": per_page
        }
        
        # Añadir filtros si están presentes
        if leagues:
            search_params["leagues"] = leagues
        if clubs:
            search_params["clubs"] = clubs
        if positions:
            search_params["positions"] = positions
        if age_min is not None:
            search_params["age_min"] = age_min
        if age_max is not None:
            search_params["age_max"] = age_max
        if min_minutes is not None:
            search_params["min_minutes"] = min_minutes
        
        # Hacer la petición a la API
        response = requests.post(f"{API_BASE_URL}/players/search", json=search_params)
        response.raise_for_status()
        
        return response.json()
        
    except requests.exceptions.RequestException as e:
        # En caso de error, devolver estructura vacía
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
    Obtiene detalles de jugadores por sus IDs
    
    Parameters
    ----------
    player_ids : List[int]
        Lista de IDs de jugadores
        
    Returns
    -------
    List[Dict[str, Any]]
        Lista de datos de jugadores
    """
    try:
        # Usar el endpoint /players/all que ya funciona y filtrar localmente
        response = requests.get(f"{API_BASE_URL}/players/all", timeout=30)
        response.raise_for_status()
        
        all_players = response.json().get('players', [])
        
        # Filtrar solo los jugadores que necesitamos
        filtered_players = [p for p in all_players if p.get('id') in player_ids]
        
        return filtered_players
        
    except requests.exceptions.RequestException as e:
        print(f"Error en get_player_details: {e}")
        return []

def get_all_players() -> Dict[str, Any]:
    """
    Obtiene todos los jugadores de la base de datos para filtrado dinámico
    
    Returns
    -------
    Dict[str, Any]
        Lista de todos los jugadores con sus datos
    """
    try:
        response = requests.get(f"{API_BASE_URL}/players/all")
        response.raise_for_status()
        
        return response.json()
        
    except requests.exceptions.RequestException as e:
        # Fallback: obtener jugadores por lotes
        try:
            # Obtener algunos jugadores de ejemplo
            response = requests.get(f"{API_BASE_URL}/players/search", params={"limit": 1000})
            response.raise_for_status()
            return response.json()
        except:
            return {"players": [], "error": str(e)}

def get_filter_options() -> Dict[str, List[str]]:
    """
    Obtiene las opciones disponibles para los filtros desde la base de datos
    
    Returns
    -------
    Dict[str, List[str]]
        Diccionario con opciones por filtro
    """
    try:
        # Usar el endpoint de FastAPI que obtiene todas las opciones únicas
        response = requests.get('http://api:8001/players/filter-options', timeout=30)
        if response.status_code == 200:
            return response.json()
        else:
            return get_filter_options_fallback()
        
    except Exception as e:
        return get_filter_options_fallback()

def get_filter_options_fallback() -> Dict[str, List[str]]:
    """
    Fallback para obtener opciones de filtros desde Django
    """
    try:
        # Obtener todos los jugadores para extraer opciones únicas
        all_players = get_all_players()
        players = all_players.get('players', [])
        
        # Extraer valores únicos para cada filtro
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
        # Devolver opciones por defecto si hay error
        return {
            "leagues": ["La Liga", "Premier League", "Serie A", "Bundesliga", "Ligue 1"],
            "clubs": ["Real Madrid", "Barcelona", "Atletico Madrid", "Manchester City", "Liverpool"],
            "positions": ["GK", "DF", "MF", "FW"],
            "nationalities": ["España", "Argentina", "Brasil", "Francia", "Alemania"]
        }

def get_comparison_data(players: List[Dict[str, Any]], metrics: List[str] = None) -> Dict[str, Any]:
    """
    Prepara datos para la comparación de jugadores
    
    Parameters
    ----------
    players : List[Dict[str, Any]]
        Lista de datos de jugadores
    metrics : List[str]
        Lista de métricas seleccionadas
        
    Returns
    -------
    Dict[str, Any]
        Datos preparados para la comparación
    """
    if not players:
        return {"error": "No hay jugadores para comparar"}
    
    if len(players) > 3:
        return {"error": "Máximo 3 jugadores para comparar"}
    
    # Si no se especifican métricas, usar las por defecto
    if not metrics:
        metrics = ['age', 'goals', 'assists', 'minutes_90s', 'goals_per90']
    
    # Preparar datos de comparación
    comparison_data = {
        "players": players,
        "metrics": metrics,
        "chart_type": "radar_comparison" if len(players) > 1 else "radar_single",
        "player_count": len(players)
    }
    
    return comparison_data

def build_search_filters(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Construye filtros de búsqueda a partir de los datos del request
    
    Parameters
    ----------
    request_data : Dict[str, Any]
        Datos del request del usuario
        
    Returns
    -------
    Dict[str, Any]
        Filtros construidos
    """
    filters = {}
    
    # Búsqueda por texto
    if request_data.get('query'):
        filters['query'] = request_data['query']
    
    # Filtros por listas
    for filter_name in ['leagues', 'clubs', 'positions']:
        if request_data.get(filter_name):
            filters[filter_name] = request_data[filter_name]
    
    # Filtros numéricos
    for filter_name in ['age_min', 'age_max', 'min_minutes']:
        if request_data.get(filter_name):
            filters[filter_name] = int(request_data[filter_name])
    
    # Paginación
    filters['page'] = int(request_data.get('page', 1))
    filters['per_page'] = int(request_data.get('per_page', 20))
    
    return filters

def serialize_player_for_card(player: Dict[str, Any]) -> Dict[str, Any]:
    """
    Serializa un jugador para mostrar en tarjeta
    
    Parameters
    ----------
    player : Dict[str, Any]
        Datos del jugador
        
    Returns
    -------
    Dict[str, Any]
        Datos serializados para la tarjeta
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
    Obtiene todas las métricas disponibles de la base de datos
    
    Returns
    -------
    List[str]
        Lista de métricas disponibles
    """
    try:
        # Obtener un jugador de ejemplo para ver qué métricas están disponibles
        response = requests.get(f"{API_BASE_URL}/players/search", params={"limit": 1})
        response.raise_for_status()
        data = response.json()
        
        if data.get('players') and len(data['players']) > 0:
            player = data['players'][0]
            # Excluir campos que no son métricas
            exclude_fields = {'id', 'full_name', 'club', 'nationality', 'age', 'position', 'team_logo', 'feature_vector'}
            metrics = [key for key in player.keys() if key not in exclude_fields]
            return sorted(metrics)
        
        return []
        
    except Exception as e:
        # Todas las métricas disponibles por defecto si hay error
        return [
            # Métricas básicas
            'age', 'minutes', 'minutes_90s',
            
            # Goles y asistencias
            'goals', 'assists', 'goals_per90', 'assists_per90', 'goals_assists_per90',
            
            # Expected Goals
            'expected_goals', 'expected_assists', 'expected_goals_per90', 'expected_assists_per90',
            'expected_goals_assists_per90', 'no_penalty_expected_goals_plus_expected_assists',
            
            # Pases
            'passes_completed', 'passes', 'passes_pct', 'passes_progressive_distance',
            'passes_completed_long', 'passes_long', 'passes_pct_long',
            'progressive_passes', 'progressive_passes_received',
            
            # Regates y carreras
            'progressive_carries',
            
            # Defensivas
            'tackles', 'tackles_won', 'challenge_tackles', 'challenges', 'challenge_tackles_pct',
            'challenges_lost', 'blocks', 'blocked_shots', 'blocked_passes',
            'interceptions', 'tackles_interceptions', 'clearances', 'errors',
            
            # Porteros
            'gk_goals_against', 'gk_pens_allowed', 'gk_free_kick_goals_against',
            'gk_corner_kick_goals_against', 'gk_own_goals_against', 'gk_psxg',
            'gk_psnpxg_per_shot_on_target_against'
        ]

def serialize_saved_search(search) -> Dict[str, Any]:
    """
    Serializa una búsqueda guardada
    
    Parameters
    ----------
    search : SavedSearch
        Instancia de búsqueda guardada
        
    Returns
    -------
    Dict[str, Any]
        Datos serializados de la búsqueda
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
