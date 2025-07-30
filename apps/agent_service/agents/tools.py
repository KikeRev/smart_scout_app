import requests
from pydantic import BaseModel, Field
from langchain.tools import StructuredTool, tool
from apps.agent_service.viz_tools import radar_chart, pizza_chart
from apps.agent_service.players_service import player_stats
from apps.agent_service.utils import stats_to_html_table
from typing import List, Optional       


# --------------------------- 1) Similar Players ----------------------------- #
class SimilarPlayersInput(BaseModel):
    """Parámetros para buscar jugadores similares"""
    player_id: int = Field(..., description="ID del jugador de referencia")
    position: str = Field(..., description="Posición a comparar (e.g. 'MF')")
    k: int = Field(10, description="Número de candidatos a devolver")
    exclude_club: Optional[str] = Field(
        None, description="Club a excluir de la búsqueda"
    )
    min_minutes: int = Field(0, description="Mínimo de minutos jugados")
    max_age: int = Field(45, description="Edad máxima")

def _similar_players(
    player_id: int,
    position: str,
    k: int = 10,
    exclude_club: Optional[str] = None,
    min_minutes: int = 0,
    max_age: int = 45,
) -> List[dict]:
    """Llama a /players/{id}/similar con los filtros recibidos."""
    params = dict(
        position=position,
        k=k,
        min_minutes=min_minutes,
        max_age=max_age,
    )
    if exclude_club:
        params["exclude_club"] = exclude_club

    url = f"http://api:8001/players/{player_id}/similar"
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()

similar_players_tool = StructuredTool.from_function(
    name="similar_players",
    description=(
        "Devuelve una lista de jugadores similares al jugador base "
        "según vector de características y filtros (posición, minutos, edad, etc.)."
    ),
    func=_similar_players,
    args_schema=SimilarPlayersInput,
)


# ----------------------------- 2) Player Lookup ----------------------------- #
class PlayerLookupInput(BaseModel):
    """Búsqueda rápida de jugadores por nombre (y opcionalmente posición)"""
    name: str = Field(..., description="Nombre o parte del nombre del jugador")
    position: str = Field("MF", description="Posición a filtrar (e.g. 'FW', 'MF')")
    limit: int = Field(5, description="Cuántos resultados devolver")

def _player_lookup(name: str, position: str = "MF", limit: int = 5) -> List[dict]:
    """Llama a /players/players/search y devuelve los candidatos encontrados."""
    url = "http://api:8001/players/players/search"
    resp = requests.get(url, params=dict(query=name, position=position, limit=limit), timeout=30)
    resp.raise_for_status()
    return resp.json()

player_lookup_tool = StructuredTool.from_function(
    name="player_lookup",
    description=(
        "Busca en la base de datos interna a partir del nombre (y posicion) y "
        "devuelve los posibles jugadores con su id, nombre y club."
    ),
    func=_player_lookup,
    args_schema=PlayerLookupInput,
)


# ------------------------------- 3) News Search ----------------------------- #
class NewsSearchInput(BaseModel):
    query: str = Field(..., description="Búsqueda en lenguaje natural")
    limit: int = Field(5, description="Máximo de noticias a devolver")

def _news_search(query: str, limit: int = 5) -> List[dict]:
    url = "http://api:8001/news/search"
    resp = requests.get(url, params=dict(query=query, limit=limit), timeout=30)
    resp.raise_for_status()
    return resp.json()

news_search_tool = StructuredTool.from_function(
    name="news_search",
    description="Busca noticias futbolísticas relevantes y devuelve título, URL y resumen.",
    func=_news_search,
    args_schema=NewsSearchInput,
)


# --------------------------- 4) Player → News ------------------------------- #
class PlayerNewsInput(BaseModel):
    player_id: int = Field(..., description="ID del jugador")
    k: int = Field(5, description="Cuántas noticias devolver")

def _player_news(player_id: int, k: int = 5) -> List[dict]:
    url = f"http://api:8001/news/players/{player_id}/news"
    resp = requests.get(url, params=dict(k=k), timeout=30)
    resp.raise_for_status()
    return resp.json()

player_news_tool = StructuredTool.from_function(
    name="player_news",
    description="Devuelve las últimas noticias enlazadas a un jugador concreto.",
    func=_player_news,
    args_schema=PlayerNewsInput,
)


#@tool(description="Devuelve la tabla html de estadísticas de un jugador como adjunto al contexto.")
def stats_table(player_name: str) -> str:
    """
    Busca las estadísticas (player_stats) y las devuelve formateadas
    como tabla Markdown para su impresión en el chat.
    """
    data = player_stats.invoke({"player_name": player_name})
    tabla_html = stats_to_html_table(data["stats"])
    return {
        "text": f"Aquí tienes la tabla de {player_name}:",
        "attachments": [
            {"type": "table", "html": tabla_html}
        ]
    }
    
pizza_chart = StructuredTool.from_function(
    func=pizza_chart,
    name="pizza_chart",
    description=(
        "Pizza chart de 9 métricas por rol (verde=ataque, azul=posesión, naranja=defensa)."
        """Requiere: role (position) ('GK'|'DF'|'MF'|'FW') y stats (dict con las métricas), 
        el player_name (full_name) y club (team)"""
        ),
    return_direct=True          #  <<–– ¡clave!
)

radar_chart = StructuredTool.from_function(
    func=radar_chart,
    name="radar_chart",
    description=(
    "Radar de 6 métricas genéricas para un jugador (edad, minutos/juego, partidos_90s, goles, asistencias, G+A)."
    "Requiere:  un dict con las player stats, el player_name, club, position (role) y nationality."),
    return_direct=True          #  <<–– ¡clave!
)

stats_table = StructuredTool.from_function(
    func=stats_table,
    name="stats_table",
    description="Genera una tabla HTML de estadísticas de un jugador",
    return_direct=True          #  <<–– ¡clave!
)

# --------------------------- 5) Exporta la lista ---------------------------- #
TOOLS = [
    player_lookup_tool,      # <-- importante: primero lookup
    player_stats,            # <-- herramienta para obtener stats de un jugador
    stats_table,             # <-- herramienta para formatear stats a Markdown
    pizza_chart,             # <-- herramienta para generar pizza charts
    radar_chart,             # <-- herramienta para generar radar charts   
    similar_players_tool,
    news_search_tool,
    player_news_tool,
]
