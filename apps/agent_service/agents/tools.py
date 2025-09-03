import requests
from pydantic import BaseModel, Field
from langchain.tools import StructuredTool
from apps.agent_service.viz_tools import radar_chart, pizza_chart, radar_comparison_chart, pizza_comparison_chart
from apps.agent_service.players_service import player_stats
from apps.agent_service.utils import stats_to_html_table, compare_stats_to_html_table
from typing import List, Optional       
from apps.agent_service.dash_tools import dashboard_inline
from apps.agent_service.report_pdf import build_report_pdf
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from typing import Optional, Annotated
from apps.agent_service.llm_provider import get_llm


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

# -------------------------- 4.1) New summarizer -------------------------------#

class SummarizePlayerNewsInput(BaseModel):
    player_id: int = Field(..., description="ID del jugador")
    k: Optional[int] = Field(5, description="Número máximo de noticias a resumir")

def _summarize_player_news(player_id: int, k: int = 5) -> str:
    try:
        # Paso 1: Recuperar noticias
        news = _player_news(player_id=player_id, k=k)
        if not news or len(news) == 0:
            return "No hay noticias relevantes sobre este jugador en los últimos meses."

        # Paso 2: Extraer contenido completo
        contents = [n.get("content", "").strip() for n in news if n.get("content")]
        if not contents:
            return "No hay contenido detallado disponible en las noticias recientes de este jugador."

        # Paso 3: Concatenar y resumir con tu LLM
        full_text = "\n\n".join(contents)

        prompt = PromptTemplate.from_template(
            """
            Eres un analista de scouting. A continuación tienes varias noticias sobre un jugador.
            Resume los aspectos clave (traspasos, rumores, interés de clubes, lesiones, declaraciones, etc.).
            Usa un estilo técnico, conciso y profesional. No repitas información redundante.
            Usa el idioma en que se te ha hecho la petición.

            Noticias:
            {text}

            Resumen:"""
        )

        chain = LLMChain(
            llm=get_llm(),  # Usamos tu función aquí
            prompt=prompt,
        )
        resumen = chain.run({"text": full_text})
        return resumen.strip()

    except Exception as e:
        return f"Error al generar el resumen de noticias: {str(e)}"

# Tool LangChain
summarize_player_news_tool = StructuredTool.from_function(
    func=_summarize_player_news,
    name="summarize_player_news",
    description="Resume en lenguaje técnico las noticias recientes relacionadas con un jugador.",
    args_schema=SummarizePlayerNewsInput,
)

# -------------------------- 4.2) Recomendación con noticias ------------------- #

class BuildScoutingReportInput(BaseModel):
    objective: str = Field(..., description="Objetivo del informe (e.g. 'Buscar lateral izquierdo joven')")
    base_id: int = Field(..., description="ID del jugador base de comparación")
    candidate_ids: List[int] = Field(..., description="Lista de IDs de jugadores candidatos")
    chosen_id: int = Field(..., description="ID del jugador elegido como fichaje recomendado")
    pros: List[str] = Field(..., description="Lista de ventajas del jugador")
    cons: List[str] = Field(..., description="Lista de inconvenientes o riesgos del jugador")

def generate_recommendation_with_news(
    chosen_id: int,
    player_name: str,
    objective: str,
    base_id: int,
    candidate_ids: List[int],
    pros: List[str],
    cons: List[str],
) -> str:
    # Paso 1: Obtener resumen de noticias
    summary = summarize_player_news_tool.run({"player_id": chosen_id, "k": 5})

    # Paso 2: Crear prompt con contexto
    prompt = PromptTemplate.from_template(
        """
        Eres un analista profesional de scouting.
        Tu objetivo es redactar un informe técnico para recomendar un fichaje. 
        Usa el idioma que se te ha hecho la petición, si la petición es en inglés usa inglés, si es en español
        usa español, etc.
        Usa datos estadísticos, pros y contras, y contexto de mercado (noticias recientes).
        Geera un texto fluido, coherente y profesional.

        Objetivo: {objective}

        Jugador recomendado: {player_name}
        Resumen de noticias recientes (si existen):
        {news}

        Genera un informe profesional que incluya, en el idioma de la petición, que incluya:
        - Al menos tres párrafos sobre virtudes, defectos, estilo de juego.
        - Un párrafo final con justificación del fichaje y encaje en el equipo.
        - Referencias a las noticias si son relevantes. Si el texto de las noticas no aporta nada, ignóralo.

        Informe:
        """
    )

    chain = LLMChain(llm=get_llm(), prompt=prompt)
    return chain.run({
        "objective": objective,
        "player_name": player_name,
        "news": summary,
    }).strip()

def build_scouting_report(
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


# --------------------------- 5) Visualización de estadísticas ---------------- #
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

def compare_stats_table(player1_name: str, player2_name: str) -> str:
    """
    Busca las estadísticas (player_stats) y las devuelve formateadas
    como tabla Markdown para su impresión en el chat.
    """
    player1 = player_stats.invoke({"player_name": player1_name})
    player2 = player_stats.invoke({"player_name": player2_name})

    tabla_html = compare_stats_to_html_table(player1["stats"], player2["stats"])
    return {
        "text": f"Aquí tienes la tabla de {player1_name} vs {player2_name}:",
        "attachments": [
            {"type": "table", "html": tabla_html}
        ]
    }
    
pizza_chart_tool = StructuredTool.from_function(
    func=pizza_chart,
    name="pizza_chart",
    description=(
        "Pizza chart de 9 métricas por rol (verde=ataque, azul=posesión, naranja=defensa)."
        """Requiere: role (position) ('GK'|'DF'|'MF'|'FW') y stats (dict con las métricas), 
        el player_name (full_name) y club (team)"""
        ),
    return_direct=True          #  <<–– Importante: permite devolver el gráfico directamente al chat 
)

pizza_comparison_chart_tool = StructuredTool.from_function(
    func=pizza_comparison_chart,
    name="pizza_comparison_chart",
    description=(
        "Pizza comparison chart de 9 métricas por rol (verde=ataque, azul=posesión, naranja=defensa)."
        """Requiere: player1_name, player2_name como mínimo, ya que el role lo podemos inferir de las stats"""
        ),
    return_direct=True          #  <<–– Importante: permite devolver el gráfico directamente al chat 
)

radar_chart_tool = StructuredTool.from_function(
    func=radar_chart,
    name="radar_chart",
    description=(
    "Radar de 6 métricas genéricas para un jugador (edad, minutos/juego, partidos_90s, goles, asistencias, G+A)."
    "Requiere:  un dict con las player stats, el player_name, club, position (role) y nationality."),
    return_direct=True          #  <<–– Importante: permite devolver el gráfico directamente al chat
)

radar_comparison_chart_tool = StructuredTool.from_function(
    func=radar_comparison_chart,
    name="radar_comparison_chart",
    description=(
    "Radar de 6 métricas genéricas para dos jugadores (edad, minutos/juego, partidos_90s, goles, asistencias, G+A)."
    "Requiere:  player1_name, player2_name como mínimo, ya que el role y el resto lo podemos inferir de las stats."),
    return_direct=True          #  <<–– Importante: permite devolver el gráfico directamente al chat
)

stats_table_tool = StructuredTool.from_function(
    func=stats_table,
    name="stats_table",
    description="Genera una tabla HTML de estadísticas de un jugador",
    return_direct=True          #  <<–– Importante: permite devolver la tabla directamente al chat
)

compare_stats_table_tool = StructuredTool.from_function(
    func=compare_stats_table,
    name="compare_stats_table",
    description="Genera una tabla HTML con estadísticas de dos jugadores y resalta el mejor valor de cada fila",
    return_direct=True          #  <<–– Importante: permite devolver la tabla directamente al chat
)

build_report_pdf_tool = StructuredTool.from_function(
    func=build_report_pdf,
    name="build_report_pdf",
    description="Genera un informe descargable en pdf",
    return_direct=True          #  <<–– Importante: permite devolver la tabla directamente al chat
)

dashboard_inline_tool = StructuredTool.from_function(
    func=dashboard_inline,
    name="dashboard_inline",
    description="Genera un dashboard interactivo con el jugador base y los candidatos",
    return_direct=True          #  <<–– Importante: permite devolver la URL directamente al chat
)

build_scouting_report_tool = StructuredTool.from_function(
    func=build_scouting_report,
    name="build_scouting_report",
    description=(
        "Genera un informe PDF profesional de scouting usando datos estadísticos y contexto de mercado actual "
        "(noticias recientes). El informe incluye análisis técnico, pros, contras y recomendación final."
    ),
    return_direct=True
)

# --------------------------- 5) Exporta la lista ---------------------------- #
TOOLS = [
    player_lookup_tool,           # <-- importante: primero lookup
    player_stats,                 # <-- herramienta para obtener stats de un jugador
    stats_table_tool,             # <-- herramienta para formatear stats a Markdown
    summarize_player_news_tool,       # <-- herramienta para resumir las noticias
    compare_stats_table_tool,     # <-- herramienta para comparar stats de dos jugadores
    pizza_chart_tool,             # <-- herramienta para generar pizza charts
    pizza_comparison_chart_tool,  # <-- herramienta para generar pizza comparison charts
    radar_chart_tool,             # <-- herramienta para generar radar charts   
    radar_comparison_chart_tool,  # <-- herramienta para generar radar comparison charts
    similar_players_tool,         # <-- herramienta para buscar jugadores similares
    news_search_tool,             # <-- herramienta para buscar noticias
    player_news_tool,             # <-- herramienta para buscar noticias relaconadas con un jugador
    dashboard_inline_tool,        # <-- herramienta para generar dashboard inline
    build_scouting_report_tool,   # <-- Herramienta para generar el la recomendación dentro del report pdf
    build_report_pdf_tool         # <-- herramienta para crear un report en pfd
] 
