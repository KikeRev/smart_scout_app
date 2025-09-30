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


# ---------------------- 1.1) Similar Players + Team Fit --------------------- #
class SimilarPlayersTeamFitInput(BaseModel):
    """Parameters to search for similar players including team-position fit"""
    player_id: int = Field(..., description="Reference player ID")
    team: str = Field(..., description="Target team (club) Y for fit computation")
    position: Optional[str] = Field(None, description="If not provided, base player's position is used")
    k: int = Field(10, description="Number of candidates to return")
    min_minutes: int = Field(0, description="Minimum minutes played")
    max_age: int = Field(45, description="Maximum age")
    exclude_club: Optional[str] = Field(None, description="Clubs to exclude (comma-separated)")
    overall_weight: float = Field(0.5, description="Weight for overall similarity in success index (0..1)")

def _similar_players_team_fit(
    player_id: int,
    team: str,
    position: Optional[str] = None,
    k: int = 10,
    min_minutes: int = 0,
    max_age: int = 45,
    exclude_club: Optional[str] = None,
    overall_weight: float = 0.5,
):
    """Calls /players/{id}/similar_team_fit with the received filters."""
    params = dict(
        team=team,
        k=k,
        min_minutes=min_minutes,
        max_age=max_age,
        overall_weight=overall_weight,
    )
    if position:
        params["position"] = position
    if exclude_club:
        params["exclude_club"] = exclude_club

    url = f"http://api:8001/players/{player_id}/similar_team_fit"
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()

similar_players_team_fit_tool = StructuredTool.from_function(
    name="similar_players_team_fit",
    description=(
        "Returns players similar to the base player plus a team-position fit analysis "
        "against the target team Y's cohort on the same position. Includes a success_index "
        "that combines overall similarity and team-position similarity."
    ),
    func=_similar_players_team_fit,
    args_schema=SimilarPlayersTeamFitInput,
)

# ---------------------- 1.2) Team Fit → HTML Table (direct) ----------------- #
def _similar_players_team_fit_table(
    player_id: int,
    team: str,
    position: Optional[str] = None,
    k: int = 10,
    min_minutes: int = 0,
    max_age: int = 45,
    exclude_club: Optional[str] = None,
    overall_weight: float = 0.5,
):
    """
    Calls the team-fit endpoint and returns an HTML table with ordered results
    by success_index, including overall similarity and team-position similarity.
    """
    data = _similar_players_team_fit(
        player_id=player_id,
        team=team,
        position=position,
        k=k,
        min_minutes=min_minutes,
        max_age=max_age,
        exclude_club=exclude_club,
        overall_weight=overall_weight,
    )

    rows = data.get("candidates", [])
    # sort by success_index descending (defensive)
    rows = sorted(rows, key=lambda r: r.get("success_index", 0), reverse=True)

    def pct(x: float | None) -> str:
        if x is None:
            return "—"
        try:
            return f"{float(x)*100:.2f}%"
        except Exception:
            return "—"

    html = [
        "<div class=\"table-responsive\">",
        "<table class=\"table table-sm table-striped align-middle\">",
        "<thead><tr>",
        "<th>#</th><th>Player</th><th>Club</th><th>Position</th>",
        "<th>Success Index</th><th>Overall</th><th>Team Fit</th>",
        "</tr></thead>",
        "<tbody>",
    ]

    for i, r in enumerate(rows, start=1):
        html.append(
            """
            <tr>
              <td>{i}</td>
              <td>{name}</td>
              <td>{club}</td>
              <td>{pos}</td>
              <td><strong>{succ}</strong></td>
              <td>{ov}</td>
              <td>{fit}</td>
            </tr>
            """.format(
                i=i,
                name=r.get("full_name", "—"),
                club=r.get("club", "—"),
                pos=r.get("position", "—"),
                succ=pct(r.get("success_index")),
                ov=pct(r.get("overall_similarity")),
                fit=pct(r.get("team_position_similarity")),
            )
        )

    html.extend(["</tbody>", "</table>", "</div>"])

    context = data.get("context", {})
    title = (
        f"Top {len(rows)} candidates for {context.get('target_team','Team')}"
        f" · Position {context.get('position','?')}"
    )
    return {
        "text": title,
        "attachments": [
            {"type": "table", "html": "".join(html)}
        ],
    }

similar_players_team_fit_table_tool = StructuredTool.from_function(
    name="similar_players_team_fit_table",
    description=(
        "Same as similar_players_team_fit but returns a compact HTML table "
        "sorted by success_index, ideal for chat display or copy to report."
    ),
    func=_similar_players_team_fit_table,
    args_schema=SimilarPlayersTeamFitInput,
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
            - Format the response as HTML for better PDF integration.
            
            **ASPECTS TO INCLUDE (only if they are in the news):**
            - Confirmed transfers or specific rumors with mentioned clubs
            - Interest from specific clubs with specific names
            - Injuries with mentioned medical details
            - Statements from the player, coach or executives
            - Recent performance with specific statistics
            - Contractual situation with mentioned dates or figures
            
            **FORMAT (HTML):**
            Use the following HTML structure:
            <div class="news-summary">
                <h4>Recent News Summary</h4>
                <p>Maximum 3 concise paragraphs with technical and professional style.</p>
                <p>Only verifiable information from the original text.</p>
                <p>Use <strong> tags for key information and <em> for emphasis.</em></p>
            </div>
            
            News:
            {text}

            Summary (HTML format):"""
        )

        chain = LLMChain(
            llm=get_llm(),  # We use your function here
            prompt=prompt,
        )
        resumen = chain.run({"text": full_text})
        return resumen.strip()

    except Exception as e:
        return f"Error generating news summary: {str(e)}"

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

# -------------------------- 4.2) Recommendation with news ------------------- #

class BuildScoutingReportInput(BaseModel):
    objective: str = Field(..., description="Report objective (e.g. 'Find young left-back')")
    base_id: int = Field(..., description="Base player ID for comparison")
    candidate_ids: List[int] = Field(..., description="List of candidate player IDs")
    chosen_id: int = Field(..., description="ID of the chosen player as recommended signing")
    pros: List[str] = Field(..., description="List of player advantages")
    cons: List[str] = Field(..., description="List of player disadvantages or risks")
    target_team: Optional[str] = Field(None, description="If provided, compute success_index vs team-position cohort and include it in the recommendation context")

def generate_recommendation_with_news(
    chosen_id: int,
    player_name: str,
    objective: str,
    base_id: int,
    candidate_ids: List[int],
    pros: List[str],
    cons: List[str],
    success_index: Optional[float] = None,
) -> str:
    # Validate input parameters
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
    
    # Validate that IDs are positive integers
    if not isinstance(chosen_id, int) or chosen_id <= 0:
        return "Error: Invalid chosen player ID."
    
    if not isinstance(base_id, int) or base_id <= 0:
        return "Error: Invalid base player ID."
    
    if not isinstance(candidate_ids, list) or not all(isinstance(id, int) and id > 0 for id in candidate_ids):
        return "Error: Invalid candidate IDs list."
    
    # Sanitize input text
    player_name = sanitize_text(player_name)
    objective = sanitize_text(objective)
    
    if not player_name or not objective:
        return "Error: Invalid player name or objective."
    
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
        - Format the response as HTML for PDF integration.
        
        **REPORT OBJECTIVE:**
        Write a professional technical report to recommend a transfer based ONLY on the provided data.
        
        **AVAILABLE DATA:**
        - Transfer objective: {objective}
        - Recommended player: {player_name}
        - News summary (if any): {news}
        - Success index vs target team fit (if available): {success_index}
        
        **REPORT STRUCTURE (HTML FORMAT):**
        Use the following HTML structure:
        
        <div class="scouting-report">
            <h3>Technical Analysis</h3>
            <p>Player's strengths based on real data, identified areas for improvement, and playing style characteristics.</p>
            
            <h3>Market Context</h3>
            <p>Only include if news contains relevant and verifiable information. If no relevant news, omit this section.</p>
            
            <h3>Transfer Justification</h3>
            <p>Why this player fits the stated objective and coherence with team needs.</p>
        </div>
        
        **WRITING RULES:**
        - Use proper HTML tags: <h3> for section headers, <p> for paragraphs
        - Maximum 4 paragraphs in total
        - Technical and professional style
        - Only verifiable information
        - If you don't have enough data, indicate it clearly
        - Use <strong> tags for emphasis on key points
        - Use <ul> and <li> for lists when appropriate

        Report (HTML format):
        """
    )

    chain = LLMChain(llm=get_llm(), prompt=prompt)
    return chain.run({
        "objective": objective,
        "player_name": player_name,
        "news": summary,
        "success_index": f"{success_index:.3f}" if isinstance(success_index, (int, float)) else "N/A",
    }).strip()

def build_scouting_report(
    objective: str,
    base_id: int,
    candidate_ids: List[int],
    chosen_id: int,
    pros: List[str],
    cons: List[str],
    target_team: Optional[str] = None,
) -> dict:
    from apps.dashboard.views import _fetch_stats 
    players_map = _fetch_stats(candidate_ids + [base_id])

    # Optionally compute success_index for the chosen player against target team
    chosen_success_index: Optional[float] = None
    if target_team:
        try:
            # Use base_id as reference and request fit for the same position and team
            import requests as _rq
            position = players_map[base_id].get("position") or players_map[base_id].get("role")
            params = {"team": target_team, "k": 50}
            if position:
                params["position"] = position
            r = _rq.get(f"http://api:8001/players/{base_id}/similar_team_fit", params=params, timeout=20)
            if r.ok:
                data = r.json()
                for item in data.get("candidates", []):
                    if int(item.get("id")) == int(chosen_id):
                        chosen_success_index = float(item.get("success_index"))
                        break
        except Exception:
            chosen_success_index = None

    recommendation = generate_recommendation_with_news(
        chosen_id=chosen_id,
        player_name=players_map[chosen_id]["full_name"],
        objective=objective,
        base_id=base_id,
        candidate_ids=candidate_ids,
        pros=pros,
        cons=cons,
        success_index=chosen_success_index,
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


# --------------------------- 5) Statistics visualization ---------------- #
def stats_table(player_name: str) -> str:
    """
    Fetches player statistics (player_stats) and returns them formatted
    as a Markdown table for display in the chat.
    """
    data = player_stats.invoke({"player_name": player_name})
    tabla_html = stats_to_html_table(data["stats"])
    return {
        "text": f"Here's the table for {player_name}:",
        "attachments": [
            {"type": "table", "html": tabla_html}
        ]
    }

def compare_stats_table(player1_name: str, player2_name: str) -> str:
    """
    Fetches player statistics (player_stats) and returns them formatted
    as a Markdown table for display in the chat.
    """
    player1 = player_stats.invoke({"player_name": player1_name})
    player2 = player_stats.invoke({"player_name": player2_name})

    tabla_html = compare_stats_to_html_table(player1["stats"], player2["stats"])
    return {
        "text": f"Here's the table for {player1_name} vs {player2_name}:",
        "attachments": [
            {"type": "table", "html": tabla_html}
        ]
    }
    
pizza_chart_tool = StructuredTool.from_function(
    func=pizza_chart,
    name="pizza_chart",
    description=(
        "Pizza chart of 9 role-based metrics (green=attack, blue=possession, orange=defense)."
        """Requires: role (position) ('GK'|'DF'|'MF'|'FW') and stats (dict with the metrics), 
        the player_name (full_name) and club (team)"""
        ),
    return_direct=True          #  <<–– Important: allows returning the chart directly to the chat 
)

pizza_comparison_chart_tool = StructuredTool.from_function(
    func=pizza_comparison_chart,
    name="pizza_comparison_chart",
    description=(
        "Pizza comparison chart of 9 role-based metrics (green=attack, blue=possession, orange=defense)."
        """Requires: player1_name, player2_name at minimum, as the role can be inferred from the stats"""
        ),
    return_direct=True          #  <<–– Important: allows returning the chart directly to the chat 
)

radar_chart_tool = StructuredTool.from_function(
    func=radar_chart,
    name="radar_chart",
    description=(
    "Radar of 6 generic metrics for a player (age, minutes/game, games_90s, goals, assists, G+A)."
    "Requires: a dict with player stats, player_name, club, position (role) and nationality."),
    return_direct=True          #  <<–– Important: allows returning the chart directly to the chat
)

radar_comparison_chart_tool = StructuredTool.from_function(
    func=radar_comparison_chart,
    name="radar_comparison_chart",
    description=(
    "Radar of 6 generic metrics for two players (age, minutes/game, games_90s, goals, assists, G+A)."
    "Requires: player1_name, player2_name at minimum, as the role and the rest can be inferred from the stats."),
    return_direct=True          #  <<–– Important: allows returning the chart directly to the chat
)

stats_table_tool = StructuredTool.from_function(
    func=stats_table,
    name="stats_table",
    description="Generates an HTML table of a player's statistics",
    return_direct=True          #  <<–– Important: allows returning the table directly to the chat
)

compare_stats_table_tool = StructuredTool.from_function(
    func=compare_stats_table,
    name="compare_stats_table",
    description="Generates an HTML table with two players' statistics and highlights the best value in each row",
    return_direct=True          #  <<–– Important: allows returning the table directly to the chat
)

build_report_pdf_tool = StructuredTool.from_function(
    func=build_report_pdf,
    name="build_report_pdf",
    description="Generates a downloadable PDF report",
    return_direct=True          #  <<–– Important: allows returning the table directly to the chat
)

dashboard_inline_tool = StructuredTool.from_function(
    func=dashboard_inline,
    name="dashboard_inline",
    description="Generates an interactive dashboard with the base player and candidates",
    return_direct=True          #  <<–– Important: allows returning the URL directly to the chat
)

build_scouting_report_tool = StructuredTool.from_function(
    func=build_scouting_report,
    name="build_scouting_report",
    description=(
        "Generates a professional PDF scouting report using statistical data and current market context "
        "(recent news). The report includes technical analysis, pros, cons, and final recommendation."
    ),
    return_direct=True
)

# --------------------------- 5) Export the list ---------------------------- #
TOOLS = [
    player_lookup_tool,           # <-- important: first lookup
    player_stats,                 # <-- tool to get player stats
    stats_table_tool,             # <-- tool to format stats to Markdown
    summarize_player_news_tool,       # <-- tool to summarize news
    compare_stats_table_tool,     # <-- tool to compare stats of two players
    pizza_chart_tool,             # <-- tool to generate pizza charts
    pizza_comparison_chart_tool,  # <-- tool to generate pizza comparison charts
    radar_chart_tool,             # <-- tool to generate radar charts   
    radar_comparison_chart_tool,  # <-- tool to generate radar comparison charts
    similar_players_tool,         # <-- tool to search for similar players
    similar_players_team_fit_tool, # <-- tool to search for similar players with team fit
    similar_players_team_fit_table_tool, # <-- HTML table for team fit results
    news_search_tool,             # <-- tool to search for news
    player_news_tool,             # <-- tool to search for news related to a player
    dashboard_inline_tool,        # <-- tool to generate inline dashboard
    build_scouting_report_tool,   # <-- Tool to generate the recommendation within the PDF report
    build_report_pdf_tool         # <-- tool to create a PDF report
] 
