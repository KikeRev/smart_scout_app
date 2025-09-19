import requests
from pydantic import BaseModel, Field
from langchain.tools import StructuredTool
from apps.agent_service.viz_tools import radar_chart, pizza_chart, radar_comparison_chart, pizza_comparison_chart
from apps.agent_service.players_service import player_stats
from apps.agent_service.utils import stats_to_html_table, compare_stats_to_html_table
from typing import List, Optional, Annotated
from apps.agent_service.dash_tools import dashboard_inline
from apps.agent_service.report_pdf import build_report_pdf
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from apps.agent_service.llm_provider import get_llm
from apps.agent_service.validation import (
    validate_player_data, 
    validate_similar_players_data, 
    validate_news_data,
    validate_stats_data,
    validate_parameters,
    sanitize_text
)


# --------------------------- 1) Similar Players ----------------------------- #
class SimilarPlayersInput(BaseModel):
    """Parameters to search for similar players"""
    player_id: int = Field(..., description="Reference player ID")
    position: str = Field(..., description="Position to compare (e.g. 'MF')")
    k: int = Field(10, description="Number of candidates to return")
    exclude_club: Optional[str] = Field(
        None, description="Club to exclude from search"
    )
    min_minutes: int = Field(0, description="Minimum minutes played")
    max_age: int = Field(45, description="Maximum age")

def _similar_players(
    player_id: int,
    position: str,
    k: int = 10,
    exclude_club: Optional[str] = None,
    min_minutes: int = 0,
    max_age: int = 45,
) -> List[dict]:
    """Calls /players/{id}/similar with the received filters."""
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
        "Returns a list of players similar to the base player "
        "based on feature vector and filters (position, minutes, age, etc.). "
        "REQUIREMENTS: player_id must exist in the database, position must be valid ('GK'|'DF'|'MF'|'FW'). "
        "Always validate that the player_id exists before using this tool."
    ),
    func=_similar_players,
    args_schema=SimilarPlayersInput,
)


# ----------------------------- 2) Player Lookup ----------------------------- #
class PlayerLookupInput(BaseModel):
    """Quick player search by name (and optionally position)"""
    name: str = Field(..., description="Player name or part of the name")
    position: str = Field("MF", description="Position to filter (e.g. 'FW', 'MF')")
    limit: int = Field(5, description="Number of results to return")

def _player_lookup(name: str, position: str = "MF", limit: int = 5) -> List[dict]:
    """Calls /players/search and returns the found candidates."""
    url = "http://api:8001/players/search"
    resp = requests.get(url, params=dict(query=name, position=position, limit=limit), timeout=30)
    resp.raise_for_status()
    return resp.json()

player_lookup_tool = StructuredTool.from_function(
    name="player_lookup",
    description=(
        "Searches the internal database by name (and position) and "
        "returns possible players with their id, name and club. "
        "REQUIREMENT: The name must be exact or very similar to the name in the database. "
        "If it doesn't find the player, returns empty list. "
        "Always validate that the player exists before using their ID in other tools."
    ),
    func=_player_lookup,
    args_schema=PlayerLookupInput,
)


# ------------------------------- 3) News Search ----------------------------- #
class NewsSearchInput(BaseModel):
    query: str = Field(..., description="Natural language search")
    limit: int = Field(5, description="Maximum number of news to return")

def _news_search(query: str, limit: int = 5) -> List[dict]:
    url = "http://api:8001/news/search"
    resp = requests.get(url, params=dict(query=query, limit=limit), timeout=30)
    resp.raise_for_status()
    return resp.json()

news_search_tool = StructuredTool.from_function(
    name="news_search",
    description="Searches for relevant football news and returns title, URL and summary.",
    func=_news_search,
    args_schema=NewsSearchInput,
)


# --------------------------- 4) Player → News ------------------------------- #
class PlayerNewsInput(BaseModel):
    player_id: int = Field(..., description="Player ID")
    k: int = Field(5, description="Number of news to return")

def _player_news(player_id: int, k: int = 5) -> List[dict]:
    url = f"http://api:8001/news/players/{player_id}/news"
    resp = requests.get(url, params=dict(k=k), timeout=30)
    resp.raise_for_status()
    return resp.json()

player_news_tool = StructuredTool.from_function(
    name="player_news",
    description="Returns the latest news linked to a specific player.",
    func=_player_news,
    args_schema=PlayerNewsInput,
)

# -------------------------- 4.1) New summarizer -------------------------------#

class SummarizePlayerNewsInput(BaseModel):
    player_id: int = Field(..., description="Player ID")
    k: Optional[int] = Field(5, description="Maximum number of news to summarize")

def _summarize_player_news(player_id: int, k: int = 5) -> str:
    try:
        # Validate input parameters
        if not validate_parameters({"player_id": player_id, "k": k}, ["player_id", "k"]):
            return "Error: Invalid input parameters."
        
        if not isinstance(player_id, int) or player_id <= 0:
            return "Error: Invalid player ID."
        
        if not isinstance(k, int) or k <= 0 or k > 20:
            return "Error: Invalid number of news (must be between 1 and 20)."

        # Step 1: Retrieve news
        news = _player_news(player_id=player_id, k=k)
        
        # Validate news data
        if not validate_news_data(news):
            return "No relevant news about this player in recent months."

        # Step 2: Extract full content and sanitize
        contents = []
        for n in news:
            if n.get("content"):
                sanitized_content = sanitize_text(n["content"])
                if sanitized_content:
                    contents.append(sanitized_content)
        
        if not contents:
            return "No detailed content available in recent news about this player."

        # Step 3: Concatenate and summarize with your LLM
        full_text = "\n\n".join(contents)

        prompt = PromptTemplate.from_template(
            """
            You are a scouting analyst specialized in evaluating football news.
            
            **CRITICAL INSTRUCTIONS:**
            - Only summarize information that is EXPLICITLY mentioned in the news.
            - DO NOT invent data, dates, clubs or figures that do not appear in the text.
            - If a news item does not contain scouting-relevant information, omit it from the summary.
            - Use the language in which the request was made.
            
            **ASPECTS TO INCLUDE (only if they are in the news):**
            - Confirmed transfers or specific rumors with mentioned clubs
            - Interest from specific clubs with specific names
            - Injuries with mentioned medical details
            - Statements from the player, coach or executives
            - Recent performance with specific statistics
            - Contractual situation with mentioned dates or figures
            
            **FORMAT:**
            - Maximum 3 concise paragraphs
            - Technical and professional style
            - Only verifiable information from the original text
            
            News:
            {text}

            Summary:"""
        )

        chain = LLMChain(
            llm=get_llm(),  # We use your function here
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
    description="Summarizes in technical language the recent news related to a player. "
    "REQUIREMENTS: player_id must exist in the database. "
    "Only summarizes information explicitly mentioned in the news. "
    "If there are no relevant news, returns message indicating absence of information.",
    args_schema=SummarizePlayerNewsInput,
)

# -------------------------- 4.2) Recomendación con noticias ------------------- #

class BuildScoutingReportInput(BaseModel):
    objective: str = Field(..., description="Report objective (e.g. 'Find young left-back')")
    base_id: int = Field(..., description="Base player ID for comparison")
    candidate_ids: List[int] = Field(..., description="List of candidate player IDs")
    chosen_id: int = Field(..., description="ID of the chosen player as recommended signing")
    pros: List[str] = Field(..., description="List of player advantages")
    cons: List[str] = Field(..., description="List of player disadvantages or risks")

def generate_recommendation_with_news(
    chosen_id: int,
    player_name: str,
    objective: str,
    base_id: int,
    candidate_ids: List[int],
    pros: List[str],
    cons: List[str],
) -> str:
    # Validar parámetros de entrada
    if not validate_parameters({
        "chosen_id": chosen_id, 
        "player_name": player_name, 
        "objective": objective,
        "base_id": base_id,
        "candidate_ids": candidate_ids,
        "pros": pros,
        "cons": cons
    }, ["chosen_id", "player_name", "objective", "base_id", "candidate_ids", "pros", "cons"]):
        return "Error: Invalid input parameters to generate recommendation."
    
    # Validar que los IDs sean enteros positivos
    if not isinstance(chosen_id, int) or chosen_id <= 0:
        return "Error: Invalid chosen player ID."
    
    if not isinstance(base_id, int) or base_id <= 0:
        return "Error: Invalid base player ID."
    
    if not isinstance(candidate_ids, list) or not all(isinstance(id, int) and id > 0 for id in candidate_ids):
        return "Error: Lista de IDs de candidatos inválida."
    
    # Sanitizar texto de entrada
    player_name = sanitize_text(player_name)
    objective = sanitize_text(objective)
    
    if not player_name or not objective:
        return "Error: Nombre del jugador u objetivo no válidos."
    
    # Step 1: Get news summary
    summary = summarize_player_news_tool.run({"player_id": chosen_id, "k": 5})

    # Step 2: Create prompt with context
    prompt = PromptTemplate.from_template(
        """
        You are a professional scouting analyst with experience in football transfers.
        
        **CRITICAL INSTRUCTIONS:**
        - Only use information that is EXPLICITLY provided in the input data.
        - DO NOT invent statistics, dates, clubs or details that are not in the data.
        - If you don't have enough information about some aspect, acknowledge it clearly.
        - Use the language in which the request was made.
        
        **REPORT OBJECTIVE:**
        Write a professional technical report to recommend a transfer based ONLY on the provided data.
        
        **AVAILABLE DATA:**
        - Transfer objective: {objective}
        - Recommended player: {player_name}
        - News summary (if any): {news}
        
        **REPORT STRUCTURE:**
        1. **Technical Analysis** (2-3 paragraphs):
           - Player's strengths based on real data
           - Identified areas for improvement
           - Playing style and technical characteristics
        
        2. **Market Context** (1 paragraph):
           - Only if the news contains relevant and verifiable information
           - If there are no relevant news, omit this section
        
        3. **Transfer Justification** (1 paragraph):
           - Why this player fits the stated objective
           - Coherence with the team's needs
        
        **WRITING RULES:**
        - Maximum 4 paragraphs in total
        - Technical and professional style
        - Only verifiable information
        - If you don't have enough data, indicate it clearly

        Report:
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
