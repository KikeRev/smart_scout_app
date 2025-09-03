# apps/agent_service/agents/tools.py
from __future__ import annotations

import requests
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field

from langchain_core.tools import tool
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

from apps.agent_service.viz_tools import (
    radar_chart,
    pizza_chart,
    radar_comparison_chart,
    pizza_comparison_chart,
)
from apps.agent_service.players_service import player_stats
from apps.agent_service.utils import stats_to_html_table, compare_stats_to_html_table
from apps.agent_service.dash_tools import dashboard_inline
from apps.agent_service.report_pdf import build_report_pdf
from apps.agent_service.llm_provider import get_llm


# =========================== helpers ======================================== #

def _normalize_position(pos: Optional[str]) -> Optional[str]:
    """Normaliza posición/rol en ES/EN a códigos esperados por el backend."""
    if not pos:
        return None
    p = str(pos).strip().lower()
    mapping = {
        "defensa": "DF",
        "defensas": "DF",
        "central": "CB",
        "centrales": "CB",
        "lateral": "FB",
        "lateral izquierdo": "LB",
        "lateral derecho": "RB",
        "mediocentro": "MF",
        "centrocampista": "MF",
        "extremo": "FW",
        "delantero": "FW",
        "portero": "GK",
    }
    return mapping.get(p, p.upper())


# =========================== 1) Similar Players ============================= #

class SimilarPlayersInput(BaseModel):
    """Parámetros para buscar jugadores similares"""
    player_id: int = Field(..., description="ID del jugador de referencia")
    position: Optional[str] = Field(
        None,
        description="Posición o rol objetivo (e.g. 'CB', 'DF', 'lateral izquierdo'). Opcional."
    )
    k: int = Field(10, description="Número de candidatos a devolver")
    exclude_club: Optional[str] = Field(None, description="Club a excluir de la búsqueda")
    min_minutes: int = Field(0, description="Mínimo de minutos jugados")
    max_age: int = Field(45, description="Edad máxima")


def _call_similar_players(
    player_id: int,
    position: Optional[str],
    k: int = 10,
    exclude_club: Optional[str] = None,
    min_minutes: int = 0,
    max_age: int = 45,
) -> List[dict]:
    """Llama a /players/{id}/similar con los filtros recibidos."""
    params: Dict[str, Any] = dict(k=k, min_minutes=min_minutes, max_age=max_age)
    if position:
        params["position"] = _normalize_position(position)
    if exclude_club:
        params["exclude_club"] = exclude_club
    url = f"http://api:8001/players/{player_id}/similar"
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


@tool(args_schema=SimilarPlayersInput)
def similar_players_tool(
    player_id: int,
    position: Optional[str] = None,
    k: int = 10,
    exclude_club: Optional[str] = None,
    min_minutes: int = 0,
    max_age: int = 45,
) -> List[dict]:
    """Devuelve jugadores similares al base según vector de características y filtros."""
    return _call_similar_players(
        player_id=player_id,
        position=position,
        k=k,
        exclude_club=exclude_club,
        min_minutes=min_minutes,
        max_age=max_age,
    )


# ============================= 2) Player Lookup ============================= #

class PlayerLookupInput(BaseModel):
    """Búsqueda rápida de jugadores por nombre (y opcionalmente posición)"""
    name: str = Field(..., description="Nombre o parte del nombre del jugador")
    position: Optional[str] = Field(
        None, description="Posición a filtrar (e.g. 'CB', 'DF', 'FW'). Opcional."
    )
    limit: int = Field(5, description="Cuántos resultados devolver")


def _call_player_lookup(name: str, position: Optional[str], limit: int = 5) -> List[dict]:
    """Llama a /players/players/search y devuelve los candidatos encontrados."""
    url = "http://api:8001/players/players/search"
    params: Dict[str, Any] = {"query": name, "limit": limit}
    if position:
        params["position"] = _normalize_position(position)
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


@tool(args_schema=PlayerLookupInput)
def player_lookup_tool(name: str, position: Optional[str] = None, limit: int = 5) -> List[dict]:
    """Busca en la BD interna por nombre/posición y devuelve id, nombre y club."""
    return _call_player_lookup(name=name, position=position, limit=limit)


# =============================== 3) News Search ============================= #

class NewsSearchInput(BaseModel):
    query: str = Field(..., description="Búsqueda en lenguaje natural")
    limit: int = Field(5, description="Máximo de noticias a devolver")


def _call_news_search(query: str, limit: int = 5) -> List[dict]:
    url = "http://api:8001/news/search"
    resp = requests.get(url, params=dict(query=query, limit=limit), timeout=30)
    resp.raise_for_status()
    return resp.json()


@tool(args_schema=NewsSearchInput)
def news_search_tool(query: str, limit: int = 5) -> List[dict]:
    """Busca noticias futbolísticas relevantes y devuelve título, URL y resumen."""
    return _call_news_search(query=query, limit=limit)


# ============================ 4) Player → News ============================== #

class PlayerNewsInput(BaseModel):
    player_id: int = Field(..., description="ID del jugador")
    k: int = Field(5, description="Cuántas noticias devolver")


def _call_player_news(player_id: int, k: int = 5) -> List[dict]:
    url = f"http://api:8001/news/players/{player_id}/news"
    resp = requests.get(url, params=dict(k=k), timeout=30)
    resp.raise_for_status()
    return resp.json()


@tool(args_schema=PlayerNewsInput)
def player_news_tool(player_id: int, k: int = 5) -> List[dict]:
    """Devuelve las últimas noticias enlazadas a un jugador concreto."""
    return _call_player_news(player_id=player_id, k=k)


# --------------------------- 4.1) News summarizer --------------------------- #

class SummarizePlayerNewsInput(BaseModel):
    player_id: int = Field(..., description="ID del jugador")
    k: Optional[int] = Field(5, description="Número máximo de noticias a resumir")


def _summarize_player_news_logic(player_id: int, k: int = 5) -> str:
    # Paso 1: Recuperar noticias
    news = _call_player_news(player_id=player_id, k=k)
    if not news:
        return "No hay noticias relevantes sobre este jugador en los últimos meses."

    # Paso 2: Extraer contenido
    contents = [n.get("content", "").strip() for n in news if n.get("content")]
    if not contents:
        return "No hay contenido detallado disponible en las noticias recientes de este jugador."

    # Paso 3: Concatenar y resumir con tu LLM (LCEL)
    full_text = "\n\n".join(contents)
    prompt = PromptTemplate.from_template(
        """
        Eres un analista de scouting. A continuación tienes varias noticias sobre un jugador.
        Resume los aspectos clave (traspasos, rumores, interés de clubes, lesiones, declaraciones, etc.).
        Usa un estilo técnico, conciso y profesional. No repitas información redundante.
        Usa el idioma en que se te ha hecho la petición.

        Noticias:
        {text}

        Resumen:
        """
    )
    chain = prompt | get_llm() | StrOutputParser()
    resumen = chain.invoke({"text": full_text})
    return resumen.strip()


@tool(args_schema=SummarizePlayerNewsInput)
def summarize_player_news_tool(player_id: int, k: int = 5) -> str:
    """Resume en lenguaje técnico las noticias recientes relacionadas con un jugador."""
    try:
        return _summarize_player_news_logic(player_id=player_id, k=k)
    except Exception as e:
        return f"Error al generar el resumen de noticias: {str(e)}"


# --------------- 4.2) Recomendación con noticias + reporte ------------------ #

class BuildScoutingReportInput(BaseModel):
    objective: str = Field(..., description="Objetivo del informe (e.g. 'Buscar lateral izquierdo joven')")
    base_id: int = Field(..., description="ID del jugador base de comparación")
    candidate_ids: List[int] = Field(..., description="Lista de IDs de jugadores candidatos")
    chosen_id: int = Field(..., description="ID del jugador elegido como fichaje recomendado")
    pros: List[str] = Field(..., description="Ventajas del jugador")
    cons: List[str] = Field(..., description="Inconvenientes o riesgos del jugador")


def generate_recommendation_with_news(
    chosen_id: int,
    player_name: str,
    objective: str,
    base_id: int,
    candidate_ids: List[int],
    pros: List[str],
    cons: List[str],
) -> str:
    summary = summarize_player_news_tool.invoke({"player_id": chosen_id, "k": 5})
    prompt = PromptTemplate.from_template(
        """
        Eres un analista profesional de scouting.
        Tu objetivo es redactar un informe técnico para recomendar un fichaje. 
        Usa el idioma que se te ha hecho la petición (EN/ES).
        Usa datos estadísticos, pros y contras, y contexto de mercado (noticias recientes).
        Genera un texto fluido, coherente y profesional.

        Objetivo: {objective}

        Jugador recomendado: {player_name}
        Resumen de noticias recientes (si existen):
        {news}

        Genera un informe que incluya:
        - Al menos tres párrafos (virtudes, defectos, estilo de juego).
        - Un párrafo final con justificación del fichaje y encaje en el equipo.
        - Referencias a las noticias si aportan valor.
        Informe:
        """
    )
    chain = prompt | get_llm() | StrOutputParser()
    return chain.invoke({
        "objective": objective,
        "player_name": player_name,
        "news": summary,
    }).strip()


def _build_scouting_report_logic(
    objective: str,
    base_id: int,
    candidate_ids: List[int],
    chosen_id: int,
    pros: List[str],
    cons: List[str],
) -> dict:
    from apps.dashboard.views import _fetch_stats
    players_map = _fetch_stats(candidate_ids + [base_id])

    recommendation = generate_recommendation_with_news(
        chosen_id=chosen_id,
        player_name=players_map[chosen_id]["full_name"],
        objective=objective,
        base_id=base_id,
        candidate_ids=candidate_ids,
        pros=pros,
        cons=cons,
    )

    return build_report_pdf(
        objective=objective,
        base_id=base_id,
        candidate_ids=candidate_ids,
        chosen_id=chosen_id,
        recommendation=recommendation,
        pros=pros,
        cons=cons,
    )


@tool(args_schema=BuildScoutingReportInput)
def build_scouting_report_tool(
    objective: str,
    base_id: int,
    candidate_ids: List[int],
    chosen_id: int,
    pros: List[str],
    cons: List[str],
) -> dict:
    """Genera un informe PDF profesional de scouting con contexto de mercado."""
    return _build_scouting_report_logic(
        objective=objective,
        base_id=base_id,
        candidate_ids=candidate_ids,
        chosen_id=chosen_id,
        pros=pros,
        cons=cons,
    )


# ====================== 5) Visualización de estadísticas ==================== #

class StatsTableInput(BaseModel):
    player_name: str = Field(..., description="Nombre del jugador")


@tool(args_schema=StatsTableInput)
def stats_table_tool(player_name: str) -> Dict[str, Any]:
    """
    Busca las estadísticas (player_stats) y las devuelve formateadas como tabla HTML.
    """
    data = player_stats.invoke({"player_name": player_name})
    tabla_html = stats_to_html_table(data["stats"])
    return {
        "text": f"Aquí tienes la tabla de {player_name}:",
        "attachments": [{"type": "table", "html": tabla_html}],
    }


class CompareStatsTableInput(BaseModel):
    player1_name: str = Field(..., description="Nombre del jugador 1")
    player2_name: str = Field(..., description="Nombre del jugador 2")


@tool(args_schema=CompareStatsTableInput)
def compare_stats_table_tool(player1_name: str, player2_name: str) -> Dict[str, Any]:
    """
    Compara estadísticas de dos jugadores y devuelve la tabla HTML.
    """
    player1 = player_stats.invoke({"player_name": player1_name})
    player2 = player_stats.invoke({"player_name": player2_name})
    tabla_html = compare_stats_to_html_table(player1["stats"], player2["stats"])
    return {
        "text": f"Aquí tienes la tabla de {player1_name} vs {player2_name}:",
        "attachments": [{"type": "table", "html": tabla_html}],
    }


# ========================== 6) Wrappers de visualización ===================== #

class PizzaChartInput(BaseModel):
    role: str
    stats: dict
    player_name: str
    club: str


@tool(args_schema=PizzaChartInput)
def pizza_chart_tool(role: str, stats: dict, player_name: str, club: str) -> Dict[str, Any]:
    """Pizza chart de 9 métricas por rol (ataque, posesión, defensa)."""
    return pizza_chart(role=role, stats=stats, player_name=player_name, club=club)


class PizzaComparisonChartInput(BaseModel):
    player1_name: str
    player2_name: str


@tool(args_schema=PizzaComparisonChartInput)
def pizza_comparison_chart_tool(player1_name: str, player2_name: str) -> Dict[str, Any]:
    """Pizza comparison chart de 9 métricas por rol."""
    return pizza_comparison_chart(player1_name=player1_name, player2_name=player2_name)


class RadarChartInput(BaseModel):
    stats: dict
    player_name: str
    club: str
    position: str
    nationality: str


@tool(args_schema=RadarChartInput)
def radar_chart_tool(stats: dict, player_name: str, club: str, position: str, nationality: str) -> Dict[str, Any]:
    """Radar de 6 métricas genéricas para un jugador."""
    return radar_chart(stats=stats, player_name=player_name, club=club, position=position, nationality=nationality)


class RadarComparisonChartInput(BaseModel):
    player1_name: str
    player2_name: str


@tool(args_schema=RadarComparisonChartInput)
def radar_comparison_chart_tool(player1_name: str, player2_name: str) -> Dict[str, Any]:
    """Radar de 6 métricas genéricas para dos jugadores."""
    return radar_comparison_chart(player1_name=player1_name, player2_name=player2_name)


# ====================== 7) Dashboard & Report PDF directos =================== #

class DashboardInlineInput(BaseModel):
    base_player_id: int
    candidate_ids: List[int]


@tool(args_schema=DashboardInlineInput)
def dashboard_inline_tool(base_player_id: int, candidate_ids: List[int]) -> Dict[str, Any]:
    """Genera un dashboard interactivo con jugador base y candidatos."""
    return dashboard_inline(base_player_id=base_player_id, candidate_ids=candidate_ids)


class BuildReportPdfInput(BaseModel):
    objective: str
    base_id: int
    candidate_ids: List[int]
    chosen_id: int
    recommendation: str
    pros: List[str]
    cons: List[str]


@tool(args_schema=BuildReportPdfInput)
def build_report_pdf_tool(
    objective: str,
    base_id: int,
    candidate_ids: List[int],
    chosen_id: int,
    recommendation: str,
    pros: List[str],
    cons: List[str],
) -> Dict[str, Any]:
    """Genera un informe descargable en PDF."""
    return build_report_pdf(
        objective=objective,
        base_id=base_id,
        candidate_ids=candidate_ids,
        chosen_id=chosen_id,
        recommendation=recommendation,
        pros=pros,
        cons=cons,
    )


# ============================= 8) Export de TOOLS ============================ #

TOOLS = [
    # lookup / datos base
    player_lookup_tool,
    # estadísticas (vía tabla/comparación)
    stats_table_tool,
    compare_stats_table_tool,
    # noticias
    news_search_tool,
    player_news_tool,
    summarize_player_news_tool,
    # similitud
    similar_players_tool,
    # visualizaciones
    pizza_chart_tool,
    pizza_comparison_chart_tool,
    radar_chart_tool,
    radar_comparison_chart_tool,
    # dashboard e informes
    dashboard_inline_tool,
    build_scouting_report_tool,
    build_report_pdf_tool,
]




