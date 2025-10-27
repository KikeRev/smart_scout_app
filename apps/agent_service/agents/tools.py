import requests
import json
from pydantic import BaseModel, Field
from langchain.tools import StructuredTool
from apps.agent_service.viz_tools import radar_chart, pizza_chart, radar_comparison_chart, pizza_comparison_chart
from apps.agent_service.players_service import player_stats
from apps.agent_service.utils import stats_to_html_table, compare_stats_to_html_table
from typing import List, Optional, Annotated, Dict
from apps.agent_service.dash_tools import dashboard_inline
from apps.agent_service.report_pdf import build_report_pdf
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from apps.agent_service.llm_provider import get_llm
import threading

from apps.agent_service.validation import (
    validate_player_data, 
    validate_similar_players_data, 
    validate_news_data,
    validate_stats_data,
    validate_parameters,
    sanitize_text
)
from apps.agent_service.conversation_state import (
    ConversationState,
    StateManager,
    add_state_to_context,
    parse_state_from_context,
    update_state_after_action
)

# Global cache for last search context (simple in-memory storage)
# This allows build_scouting_report to access the last search metadata
# Key: user_id, Value: search context
_user_search_contexts: Dict[str, Dict] = {}

# Thread-local storage for current user_id
_thread_local = threading.local()

def set_current_user_id(user_id: str):
    """Set the current user_id in thread-local storage"""
    _thread_local.user_id = user_id

def get_current_user_id() -> str:
    """Get the current user_id from thread-local storage"""
    return getattr(_thread_local, 'user_id', 'anon')

# Alternative: Use a more persistent cache approach
# Store the last search context in a way that survives between agent calls
_last_search_context: Dict = {}

# Redis connection for persistent context (optional)
try:
    import redis
    redis_client = redis.Redis(host='redis', port=6379, db=0, decode_responses=True)
    redis_client.ping()  # Test connection
    REDIS_AVAILABLE = True
except:
    redis_client = None
    REDIS_AVAILABLE = False

def _save_context_to_redis(user_id: str, context: Dict, state: ConversationState = ConversationState.IDLE):
    """Save context to Redis for persistence across requests with conversation state"""
    # Add state information to context
    context_with_state = add_state_to_context(context.copy(), state)
    
    if REDIS_AVAILABLE:
        try:
            redis_client.setex(f"search_context:{user_id}", 3600, json.dumps(context_with_state))  # 1 hour TTL
        except Exception:
            pass  # Fallback to in-memory cache

def _get_context_from_redis(user_id: str) -> Dict:
    """Get context from Redis"""
    if REDIS_AVAILABLE:
        try:
            data = redis_client.get(f"search_context:{user_id}")
            if data:
                return json.loads(data)
        except Exception:
            pass
    return {}



# ----------------------------------------------------------------------------
# Helper utilities (simple language detection for guided messages)
# ----------------------------------------------------------------------------

def _looks_spanish(text: str) -> bool:
    """Heurística liviana ES/EN para mensajes guiados."""
    if not isinstance(text, str):
        return False
    t = text.lower()
    spanish_clues = [
        " el ", " la ", " los ", " las ", " de ", " del ", " para ", " por ",
        " jugador", " equipo", " informe", " reporte", " crear", " dame", " buscar",
        "¿", "¡", "ó", "á", "é", "í", "ú", "ñ",
    ]
    return any(clue in t for clue in spanish_clues)

def _msg_locale(user_text: Optional[str], es: str, en: str) -> str:
    return es if _looks_spanish(user_text or "") else en


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
    user_id: Optional[str] = Field(None, description="User ID to save context to Redis")

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
    user_id: Optional[str] = None,
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
    # sort by success_index_v2_1 descending (primary), fallback to success_index
    rows = sorted(rows, key=lambda r: r.get("success_index_v2_1", r.get("success_index", 0)), reverse=True)

    def pct(x: float | None) -> str:
        if x is None:
            return "—"
        try:
            return f"{float(x)*100:.2f}%"
        except Exception:
            return "—"

    html = [
        "<div class=\"table-responsive\">",
        "<div class=\"d-flex justify-content-between align-items-center mb-2\">",
        "<h6 class=\"mb-0\">Player Recommendations</h6>",
        "<button class=\"btn btn-sm btn-outline-secondary\" onclick=\"copyTableToClipboard()\" title=\"Copy table to clipboard\">",
        "<i class=\"fas fa-copy\"></i> Copy Table",
        "</button>",
        "</div>",
        "<table id=\"recommendations-table\" class=\"table table-sm table-striped align-middle\">",
        "<thead><tr>",
        "<th onclick=\"sortTable(0)\" style=\"cursor: pointer;\"># <i class=\"fas fa-sort\"></i></th>",
        "<th onclick=\"sortTable(1)\" style=\"cursor: pointer;\">Player <i class=\"fas fa-sort\"></i></th>",
        "<th onclick=\"sortTable(2)\" style=\"cursor: pointer;\">Club <i class=\"fas fa-sort\"></i></th>",
        "<th onclick=\"sortTable(3)\" style=\"cursor: pointer;\">Position <i class=\"fas fa-sort\"></i></th>",
           "<th onclick=\"sortTable(4)\" style=\"cursor: pointer;\">Success Index <i class=\"fas fa-sort\"></i></th>",
           "<th onclick=\"sortTable(5)\" style=\"cursor: pointer;\">Viability Score <i class=\"fas fa-sort\"></i></th>",
           "<th onclick=\"sortTable(6)\" style=\"cursor: pointer;\">Overall <i class=\"fas fa-sort\"></i></th>",
           "<th onclick=\"sortTable(7)\" style=\"cursor: pointer;\">Team Fit <i class=\"fas fa-sort\"></i></th>",
           "<th>Profile <i class=\"fas fa-info-circle\"></i></th>",
        "</tr></thead>",
        "<tbody>",
    ]

    def get_profile_badges(breakdown: dict, age: int, minutes: int, league: str) -> str:
        """Generate visual badges based on success index breakdown"""
        badges = []
        
        # League badge
        league_w = breakdown.get('league_weight', 0)
        if league_w >= 1.0:
            badges.append("🟢 Top5")
        elif league_w >= 0.85:
            badges.append("🟡 Tier2")
        elif league_w >= 0.70:
            badges.append("🟠 Tier3")
        else:
            badges.append("🔴 Minor")
        
        # Minutes badge
        minutes_w = breakdown.get('minutes_weight', 0)
        if minutes_w >= 1.0:
            badges.append("🟢 Starter")
        elif minutes_w >= 0.75:
            badges.append("🟡 Rotation")
        else:
            badges.append("🔴 Backup")
        
        # Age badge
        age_w = breakdown.get('age_weight', 0)
        if age_w >= 0.95:
            badges.append(f"🟢 {age}y")
        elif age_w >= 0.85:
            badges.append(f"🟡 {age}y")
        else:
            badges.append(f"🔴 {age}y")
        
        return "<br>".join(badges)

    for i, r in enumerate(rows, start=1):
        profile_href = f"/dashboard/player/{r.get('id')}/"
        breakdown = r.get("success_breakdown", {})
        profile_info = get_profile_badges(
            breakdown, 
            r.get("age", 0), 
            r.get("minutes", 0),
            r.get("league", "")
        )
        
        # Calculate viability score for display
        success_idx = r.get("success_index_v2_1", r.get("success_index", 0))
        # Use provided team argument as target team for feasibility calc
        feasibility = _feasibility_multiplier(r, team)
        viability = float(success_idx) * feasibility
        
        html.append(
            """
            <tr>
                <td>{i}</td>
                <td><a href="{href}" target="_blank" rel="noopener">{name}</a></td>
                <td>{club}</td>
                <td>{pos}</td>
                <td><strong>{succ}</strong></td>
                <td><strong style="color: #28a745;">{viab}</strong></td>
                <td>{ov}</td>
                <td>{fit}</td>
                <td style="font-size: 0.85em; line-height: 1.4;">{profile}</td>
            </tr>
            """.format(
                i=i,
                name=r.get("full_name", "—"),
                href=profile_href,
                club=r.get("club", "—"),
                pos=r.get("position", "—"),
                succ=pct(success_idx),
                viab=pct(viability),
                ov=pct(r.get("overall_similarity")),
                fit=pct(r.get("team_position_similarity")),
                profile=profile_info,
            )
        )

    html.extend([
        "</tbody>", 
        "</table>",
        "<div class=\"mt-2\" style=\"font-size: 0.85em; color: #6c757d;\">",
        "<strong>Profile Legend:</strong> ",
        "🟢 Optimal | 🟡 Good | 🟠 Moderate | 🔴 Risk/Concern",
        "</div>",
        "</div>",
        """
        <script>
        let sortDirection = {};
        
        function sortTable(columnIndex) {
            const table = document.getElementById('recommendations-table');
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            
            // Toggle sort direction
            sortDirection[columnIndex] = sortDirection[columnIndex] === 'asc' ? 'desc' : 'asc';
            const direction = sortDirection[columnIndex];
            
            // Update sort icons
            const headers = table.querySelectorAll('th');
            headers.forEach((header, index) => {
                const icon = header.querySelector('i');
                if (index === columnIndex) {
                    icon.className = direction === 'asc' ? 'fas fa-sort-up' : 'fas fa-sort-down';
                } else {
                    icon.className = 'fas fa-sort';
                }
            });
            
            // Sort rows
            rows.sort((a, b) => {
                let aVal = a.cells[columnIndex].textContent.trim();
                let bVal = b.cells[columnIndex].textContent.trim();
                
                   // Handle numeric columns (Success Index, Viability Score, Overall, Team Fit) - excluding Profile (column 8)
                   if (columnIndex >= 4 && columnIndex <= 7) {
                    aVal = parseFloat(aVal.replace('%', '')) || 0;
                    bVal = parseFloat(bVal.replace('%', '')) || 0;
                }
                
                if (direction === 'asc') {
                    return aVal > bVal ? 1 : -1;
                } else {
                    return aVal < bVal ? 1 : -1;
                }
            });
            
            // Re-append sorted rows
            rows.forEach(row => tbody.appendChild(row));
        }
        
        function copyTableToClipboard() {
            const table = document.getElementById('recommendations-table');
            const range = document.createRange();
            range.selectNode(table);
            window.getSelection().removeAllRanges();
            window.getSelection().addRange(range);
            
            try {
                document.execCommand('copy');
                // Show success feedback
                const button = event.target.closest('button');
                const originalText = button.innerHTML;
                button.innerHTML = '<i class="fas fa-check"></i> Copied!';
                button.classList.remove('btn-outline-secondary');
                button.classList.add('btn-success');
                
                setTimeout(() => {
                    button.innerHTML = originalText;
                    button.classList.remove('btn-success');
                    button.classList.add('btn-outline-secondary');
                }, 2000);
            } catch (err) {
                console.error('Failed to copy table:', err);
                alert('Failed to copy table. Please try selecting and copying manually.');
            }
            
            window.getSelection().removeAllRanges();
        }
        </script>
        """
    ])

    context = data.get("context", {})
    title = (
        f"Top {len(rows)} candidates for {context.get('target_team','Team')}"
        f" · Position {context.get('position','?')}"
    )
    
    # Store candidate IDs for report generation
    candidate_ids = [r.get("id") for r in rows]
    
    # Save context globally for build_scouting_report to access
    # Always overwrite to ensure we use the latest list in the same chat session
    global _user_search_contexts, _last_search_context
    context_data = {
        "base_id": player_id,
        "candidate_ids": candidate_ids,
        "target_team": team,
        "position": position or context.get("position"),
        "candidates_data": rows  # Full data with success_index_v2_1
    }
    _user_search_contexts["current"] = context_data
    _last_search_context = context_data  # Backup cache
    
    # Save to Redis for persistence across requests
    # Use thread-local user_id if not explicitly provided
    effective_user_id = user_id or get_current_user_id()
    _save_context_to_redis(effective_user_id, context_data, ConversationState.SEARCH_COMPLETED)
    
    
    return {
        "text": title,
        "attachments": [
            {"type": "table", "html": "".join(html)}
        ]
    }

similar_players_team_fit_table_tool = StructuredTool.from_function(
    name="similar_players_team_fit_table",
    description=(
        "Same as similar_players_team_fit but returns a compact HTML table "
        "sorted by success_index, ideal for chat display or copy to report. "
        "CRITICAL: ALWAYS pass user_id parameter - this tool stores search context (base_id, candidate_ids, target_team) "
        "in Redis using user_id for persistence. After this tool completes, the user can request 'dashboard' or 'PDF report' "
        "in their NEXT message, and those tools will automatically retrieve the stored context using the same user_id."
    ),
    func=_similar_players_team_fit_table,
    args_schema=SimilarPlayersTeamFitInput,
    return_direct=True  # Must be True to display table correctly in chat
)


# ----------------------------- 2) Player Lookup ----------------------------- #
class PlayerLookupInput(BaseModel):
    """Quick player search by name (and optionally position)"""
    name: str = Field(..., description="Player name or part of the name")
    position: str = Field("MF", description="Position to filter (e.g. 'FW', 'MF')")
    limit: int = Field(15, description="Number of results to return")

def _player_lookup(name: str, position: str = "MF", limit: int = 200) -> List[dict]:
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

def _feasibility_multiplier(candidate: dict, target_team: Optional[str]) -> float:
    """Compute feasibility multiplier based on simple, explicit rules.

    Rules (from agent instructions):
      - HIGH (1.0-1.2): tier2/3 leagues, rotation players, young from mid-table
      - MED (0.75-0.9): starter mid-table Top5, star in competitive club
      - LOW (0.3-0.5): direct rival, undisputed star UCL giant, just signed

    Inputs available in candidate row: club, league, minutes, age, success_index_v2_1.
    """
    if not candidate:
        return 0.75

    club = (candidate.get("club") or "").lower()
    league = (candidate.get("league") or "").lower()
    minutes = int(candidate.get("minutes") or 0)
    age = int(candidate.get("age") or 0)

    # Rivalry matrix (basic hardcoded set)
    target = (target_team or "").lower()
    rivals_map = {
        "real madrid": {"barcelona", "atlético madrid", "atletico madrid"},
        "barcelona": {"real madrid"},
        "manchester city": {"manchester united"},
        "manchester united": {"manchester city"},
        "arsenal": {"tottenham"},
        "tottenham": {"arsenal"},
        "liverpool": {"everton"},
        "everton": {"liverpool"},
        "inter": {"milan"},
        "milan": {"inter"},
        "roma": {"lazio"},
        "lazio": {"roma"},
        "juventus": {"torino"},
        "torino": {"juventus"},
        "bayern": {"dortmund"},
        "borussia dortmund": {"bayern"},
    }

    # Rival penalty (not zero, but strong)
    if target and any(target in k for k in rivals_map.keys()):
        for k, rivals in rivals_map.items():
            if target.startswith(k) and any(r in club for r in rivals):
                return 0.30

    # League tiers (approx)
    tier1 = {"premier", "la liga", "bundesliga", "serie a", "ligue 1"}
    tier2 = {"eredivisie", "primeira", "belgian", "liga mx", "brasileirao"}

    league_mult = 1.0
    if any(t in league for t in tier2):
        league_mult = 1.2
    elif any(t in league for t in tier1):
        league_mult = 1.0  # Top 5 leagues - neutral (not penalized)
    else:
        league_mult = 1.1  # emerging leagues

    # Minutes-based role (less penalizing for starters)
    role_mult = 1.0
    if minutes >= 2000:
        role_mult = 0.95  # undisputed starter → slightly harder but not much
    elif minutes >= 1000:
        role_mult = 1.0
    else:
        role_mult = 1.1  # rotation → easier

    # Young bonus
    age_mult = 1.0
    if 18 <= age <= 23:
        age_mult = 1.1

    # Cap and compose
    mult = league_mult * role_mult * age_mult
    # Clamp within 0.3 - 1.2
    return max(0.3, min(1.2, round(mult, 2)))

class BuildScoutingReportInput(BaseModel):
    objective: str = Field(..., description="Report objective (e.g. 'Find young left-back')")
    # Optional fields - will be filled from cached context if not provided
    base_id: Optional[int] = Field(None, description="Base player ID for comparison (optional, uses cached context if missing)")
    candidate_ids: Optional[List[int]] = Field(None, description="List of candidate player IDs (optional, uses cached context if missing)")
    chosen_id: int = Field(..., description="ID of the chosen player as recommended signing")
    pros: Optional[List[str]] = Field(None, description="List of player advantages (optional)")
    cons: Optional[List[str]] = Field(None, description="List of player disadvantages or risks (optional)")
    target_team: Optional[str] = Field(None, description="If provided, compute success_index vs team-position cohort and include it in the recommendation context")
    user_id: Optional[str] = Field(None, description="User ID to retrieve cached context from Redis")

def generate_recommendation_with_news(
    chosen_id: int,
    player_name: str,
    objective: str,
    base_id: int,
    candidate_ids: List[int],
    pros: List[str],
    cons: List[str],
    success_index: Optional[float] = None,
    feasibility_multiplier: Optional[float] = None,
    viability_score: Optional[float] = None,
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
        This report should justify why THIS player is the most viable option, not just the highest-scored one.
        
        **AVAILABLE DATA:**
        - Transfer objective: {objective}
        - Recommended player: {player_name}
        - News summary (if any): {news}
        - Success index v2.1 (probability of tactical fit considering league, minutes, age, team strength, position): {success_index}
        - Feasibility multiplier (transfer difficulty): {feasibility}
        - Viability score (success_index × feasibility): {viability}
        
        **CONTEXT:**
        This player was selected after analyzing multiple candidates and considering:
        1) Tactical fit (success_index_v2_1)
        2) Transfer feasibility (club rivalry, player status, market value)
        3) Risk-benefit balance
        
        **REPORT STRUCTURE (HTML FORMAT):**
        Write ONLY the content HTML, starting directly with the first <h3> tag.
        DO NOT include <html>, <body>, <head> or any document-level tags.
        
        Structure example:
        
        <h3>Technical Analysis</h3>
        <p>Player's strengths based on real data, identified areas for improvement, and playing style characteristics.</p>
        
        <h3>Market Context</h3>
        <p>Only include if news contains relevant and verifiable information. If no relevant news, omit this section.</p>
        
        <h3>Transfer Justification</h3>
        <p>Why THIS player is the most viable option considering:
           - Tactical fit (success_index as indicator)
           - Transfer feasibility (is this a realistic target given club dynamics?)
           - Value proposition (cost-benefit balance)</p>
        
        <h3>Why This Player Over Alternatives</h3>
        <p>If there were higher-scored candidates, explain why they were not selected (e.g., club rivalry, unrealistic target, excessive cost). 
           Justify why this recommendation is the most practical and achievable option.</p>
        
        **WRITING RULES:**
        - Start directly with <h3>, NOT with <html> or <div>
        - Use <h3> for section headers, <p> for paragraphs
        - Maximum 4 paragraphs in total
        - Technical and professional style
        - Only verifiable information
        - If you don't have enough data, indicate it clearly
        - Use <strong> tags for emphasis on key points
        - Use <ul> and <li> for lists when appropriate

        Report (HTML content only, no document tags):
        """
    )

    chain = LLMChain(llm=get_llm(), prompt=prompt)
    
    return chain.run({
    "objective": objective,
    "player_name": player_name,
    "news": summary,
        "success_index": f"{success_index:.3f}" if isinstance(success_index, (int, float)) else "N/A",
        "feasibility": f"{feasibility_multiplier:.2f}" if isinstance(feasibility_multiplier, (int, float)) else "N/A",
        "viability": f"{viability_score:.3f}" if isinstance(viability_score, (int, float)) else "N/A",
    }).strip()

def build_scouting_report(
    objective: str,
    base_id: Optional[int] = None,
    candidate_ids: Optional[List[int]] = None,
    chosen_id: int = None,
    pros: Optional[List[str]] = None,
    cons: Optional[List[str]] = None,
    target_team: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict:
    global _user_search_contexts
    
    # If parameters not provided, try to use cached context
    if not base_id or not candidate_ids:
        # Use thread-local user_id if not explicitly provided
        effective_user_id = user_id or get_current_user_id()
        
        # Try Redis first for persistence
        cached_context = _get_context_from_redis(effective_user_id)
        
        # Fallback to in-memory cache
        if not cached_context:
            if "current" in _user_search_contexts:
                cached_context = _user_search_contexts["current"]
            elif _last_search_context:
                cached_context = _last_search_context
        
        if not cached_context:
            # Mensaje guiado localizado (ES/EN) en vez de error técnico
            es_msg = (
                "No encuentro el contexto de la última búsqueda (base y candidatos). "
                "Para continuar puedo: \n"
                "1) volver a generar la tabla de candidatos (dime el jugador de referencia y el equipo objetivo), o\n"
                "2) si ya tienes los IDs, indícame 'base_id' y la lista de 'candidate_ids'."
            )
            en_msg = (
                "I can't find the last search context (base and candidates). "
                "To proceed, I can: \n"
                "1) regenerate the candidates table (tell me the reference player and the target team), or\n"
                "2) if you already have them, provide 'base_id' and the list of 'candidate_ids'."
            )
            return {"text": _msg_locale(objective, es_msg, en_msg), "attachments": []}
        
        base_id = base_id or cached_context.get("base_id")
        candidate_ids = candidate_ids or cached_context.get("candidate_ids")
        target_team = target_team or cached_context.get("target_team")
    
    from apps.dashboard.views import _fetch_stats 
    # Ensure the chosen_id is included when fetching stats to avoid KeyError
    ids_to_fetch = list({*(candidate_ids or []), base_id, chosen_id})
    # Filter invalid/None and cast to int
    ids_to_fetch = [int(i) for i in ids_to_fetch if isinstance(i, (int, float))]
    players_map = _fetch_stats(ids_to_fetch)

    # Optionally compute success_index_v2_1 for the chosen player against target team
    # and get full candidates data with Success Index
    chosen_success_index: Optional[float] = None
    candidates_data: Optional[List[dict]] = None
    
    # Try to use cached candidates_data first (also compute feasibility & viability)
    if ("current" in _user_search_contexts and _user_search_contexts["current"].get("candidates_data")) or _last_search_context.get("candidates_data"):
        candidates_data = _user_search_contexts["current"].get("candidates_data") or _last_search_context.get("candidates_data")
        # Normalize candidate_ids as ints and fallback to cached ids if missing
        cached_ids = [int(c.get("id")) for c in (candidates_data or []) if c.get("id") is not None]
        if not candidate_ids:
            candidate_ids = cached_ids
        else:
            candidate_ids = [int(cid) for cid in candidate_ids]

        # If chosen_id not provided or not in cached ids, fallback to best candidate
        if chosen_id is None or int(chosen_id) not in cached_ids:
            if candidates_data:
                # Compute feasibility & viability for each candidate
                for c in candidates_data:
                    c["feasibility_multiplier"] = _feasibility_multiplier(c, target_team)
                    base_si = float(c.get("success_index_v2_1", c.get("success_index", 0)))
                    c["viability_score"] = base_si * c["feasibility_multiplier"]
                best = sorted(
                    candidates_data,
                    key=lambda x: x.get("viability_score", x.get("success_index_v2_1", x.get("success_index", 0))),
                    reverse=True,
                )[0]
                chosen_id = int(best.get("id"))
                chosen_success_index = float(best.get("success_index_v2_1", best.get("success_index", 0)))
                chosen_feas = float(best.get("feasibility_multiplier", 1.0))
                chosen_viab = float(best.get("viability_score", chosen_success_index * chosen_feas))
        else:
            # Find chosen player's success index from cached data
            for item in candidates_data:
                if int(item.get("id")) == int(chosen_id):
                    chosen_success_index = float(item.get("success_index_v2_1", item.get("success_index", 0)))
                    chosen_feas = _feasibility_multiplier(item, target_team)
                    chosen_viab = chosen_success_index * chosen_feas
                    break
    elif target_team:
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
                all_candidates = data.get("candidates", [])
                
                # Filter to only include candidates in candidate_ids
                candidates_data = [
                    c for c in all_candidates 
                    if int(c.get("id")) in candidate_ids
                ]
                
                # Find chosen player's success index
                for item in all_candidates:
                    if int(item.get("id")) == int(chosen_id):
                        # Usar success_index_v2_1 si está disponible, sino fallback a success_index
                        chosen_success_index = float(item.get("success_index_v2_1", item.get("success_index")))
                        break
        except Exception as e:
            print(f"Error fetching success index data: {e}")
            chosen_success_index = None
            candidates_data = None

    recommendation = generate_recommendation_with_news(
        chosen_id=chosen_id,
        player_name=players_map[chosen_id]["full_name"],
        objective=objective,
        base_id=base_id,
        candidate_ids=candidate_ids,
        pros=pros,
        cons=cons,
        success_index=chosen_success_index,
        feasibility_multiplier=locals().get("chosen_feas", None),
        viability_score=locals().get("chosen_viab", None),
    )

    # Update conversation state to REPORT_AVAILABLE
    effective_user_id = user_id or get_current_user_id()
    current_context = _get_context_from_redis(effective_user_id) or {}
    if current_context:
        updated_context = update_state_after_action(current_context, "report")
        _save_context_to_redis(effective_user_id, updated_context, ConversationState.REPORT_AVAILABLE)

    return build_report_pdf(
        objective=objective,
        base_id=base_id,
        candidate_ids=candidate_ids,
        chosen_id=chosen_id,
        recommendation=recommendation,
        pros=pros,
        cons=cons,
        target_team=target_team,
        candidates_data=candidates_data,
    )


# --------------------------- 5) Statistics visualization ---------------- #
def stats_table(player_name: str, team: Optional[str] = None) -> str:
    """
    Fetches player statistics (player_stats) and returns them formatted
    as a Markdown table for display in the chat.
    
    Args:
        player_name: The name of the player to search for
        team: Optional team name to disambiguate when multiple players have the same name
    """
    data = player_stats.invoke({"player_name": player_name, "team": team})
    tabla_html = stats_to_html_table(data["stats"])
    return {
        "text": f"Here's the table for {player_name}:",
        "attachments": [
            {"type": "table", "html": tabla_html}
        ]
    }

def compare_stats_table(player1_name: str, player2_name: str, team1: Optional[str] = None, team2: Optional[str] = None) -> str:
    """
    Fetches player statistics (player_stats) and returns them formatted
    as a Markdown table for display in the chat.
    
    Args:
        player1_name: The name of the first player to search for
        player2_name: The name of the second player to search for
        team1: Optional team name to disambiguate the first player
        team2: Optional team name to disambiguate the second player
    """
    player1 = player_stats.invoke({"player_name": player1_name, "team": team1})
    player2 = player_stats.invoke({"player_name": player2_name, "team": team2})

    tabla_html = compare_stats_to_html_table(player1["stats"], player2["stats"])
    return {
        "text": f"Here's the table for {player1_name} vs {player2_name}:",
        "attachments": [
            {"type": "table", "html": tabla_html}
        ]
    }

# ---------------------- 4.3) Choose best candidate (no PDF) ----------------- #
class ChooseBestCandidateInput(BaseModel):
    objective: Optional[str] = Field(None, description="User objective text to infer language for the response")
    user_id: Optional[str] = Field(None, description="User ID to retrieve cached context from Redis")

def choose_best_candidate(objective: Optional[str] = None, user_id: Optional[str] = None) -> dict:
    """Return the best candidate name and id from cached/Redis context.
    If context is missing, return a localized guided message.
    """
    # Use thread-local user_id if not explicitly provided
    effective_user_id = user_id or get_current_user_id()
    cached_context = _get_context_from_redis(effective_user_id) or _user_search_contexts.get("current") or _last_search_context
    if not cached_context:
        es_msg = (
            "No encuentro el contexto de la última búsqueda. "
            "Primero genera la tabla de candidatos y después podré elegir el mejor (nombre real)."
        )
        en_msg = (
            "I can't find the last search context. "
            "Please generate the candidates table first and then I will pick the best one (real name)."
        )
        return {"text": _msg_locale(objective, es_msg, en_msg)}

    base_id = int(cached_context.get("base_id")) if cached_context.get("base_id") is not None else None
    candidate_ids = [int(i) for i in cached_context.get("candidate_ids", [])]
    if not base_id or not candidate_ids:
        es_msg = "El contexto está incompleto (falta base_id o candidate_ids). Vuelve a generar la tabla, por favor."
        en_msg = "Context is incomplete (missing base_id or candidate_ids). Please regenerate the candidates table."
        return {"text": _msg_locale(objective, es_msg, en_msg)}

    # Fetch minimal stats map to get names
    from apps.dashboard.views import _fetch_stats
    players_map = _fetch_stats([base_id, *candidate_ids])

    # Compute feasibility + viability from cached candidates_data if available
    candidates_data = cached_context.get("candidates_data") or []
    if not candidates_data:
        # fallback: pick first candidate_id
        best_id = candidate_ids[0]
    else:
        for c in candidates_data:
            c["feasibility_multiplier"] = _feasibility_multiplier(c, cached_context.get("target_team"))
            base_si = float(c.get("success_index_v2_1", c.get("success_index", 0)))
            c["viability_score"] = base_si * c["feasibility_multiplier"]
        best = sorted(candidates_data, key=lambda x: x.get("viability_score", 0), reverse=True)[0]
        best_id = int(best.get("id"))

    name = players_map.get(best_id, {}).get("full_name") or str(best_id)
    es_text = f"Mi recomendación inicial es: {name} (ID {best_id})."
    en_text = f"My initial recommendation is: {name} (ID {best_id})."
    return {"text": _msg_locale(objective, es_text, en_text), "chosen_id": best_id, "player_name": name}

choose_best_candidate_tool = StructuredTool.from_function(
    func=choose_best_candidate,
    name="choose_best_candidate",
    description=(
        "Selects the best candidate from the latest search context and returns the real player name and id. "
        "If context is missing, returns a guided message to regenerate the table."
    ),
    args_schema=ChooseBestCandidateInput,
)
    
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
        "If multiple players have the same name, use 'team1' and 'team2' parameters to disambiguate."
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
    "If multiple players have the same name, use 'team1' and 'team2' parameters to disambiguate."),
    return_direct=True          #  <<–– Important: allows returning the chart directly to the chat
)

stats_table_tool = StructuredTool.from_function(
    func=stats_table,
    name="stats_table",
    description="Generates an HTML table of a player's statistics. If multiple players have the same name, use the 'team' parameter to disambiguate.",
    return_direct=True          #  <<–– Important: allows returning the table directly to the chat
)

compare_stats_table_tool = StructuredTool.from_function(
    func=compare_stats_table,
    name="compare_stats_table",
    description="Generates an HTML table with two players' statistics and highlights the best value in each row. If multiple players have the same name, use the 'team1' and 'team2' parameters to disambiguate.",
    return_direct=True          #  <<–– Important: allows returning the table directly to the chat
)

build_report_pdf_tool = StructuredTool.from_function(
    func=build_report_pdf,
    name="build_report_pdf",
    description="Generates a downloadable PDF report",
    return_direct=True          #  <<–– Important: allows returning the table directly to the chat
)

class DashboardInlineInput(BaseModel):
    """Input for dashboard inline. Both parameters are optional - will use cached context if not provided."""
    base_player_id: Optional[int] = Field(None, description="ID of the base/reference player")
    candidate_ids: Optional[List[int]] = Field(None, description="List of candidate player IDs to compare")
    user_id: Optional[str] = Field(None, description="User ID to retrieve cached context from Redis")

def _dashboard_inline_with_context(
    base_player_id: Optional[int] = None, 
    candidate_ids: Optional[List[int]] = None,
    user_id: Optional[str] = None
) -> dict:
    """Wrapper that defaults to the latest candidate list from cache if not provided."""
    global _user_search_contexts, _last_search_context
    
    if (not base_player_id or not candidate_ids):
        ctx = {}
        
        # Use thread-local user_id if not explicitly provided
        effective_user_id = user_id or get_current_user_id()
        
        # Try Redis first (persistent across requests)
        ctx = _get_context_from_redis(effective_user_id) or {}
        
        # Fallback to primary cache
        if not ctx and "current" in _user_search_contexts:
            ctx = _user_search_contexts["current"]
        # Fallback to backup cache
        elif not ctx and _last_search_context:
            ctx = _last_search_context
            
        base_player_id = base_player_id or ctx.get("base_id")
        candidate_ids = candidate_ids or ctx.get("candidate_ids")
        
    # Safety: ensure list of ints
    candidate_ids = [int(i) for i in (candidate_ids or []) if isinstance(i, (int, float))]
    
    # Get the URL from dashboard_inline
    result = dashboard_inline(base_player_id, candidate_ids)
    dashboard_url = result.get("url", "")
    
    # Update conversation state to DASHBOARD_AVAILABLE
    effective_user_id = user_id or get_current_user_id()
    current_context = _get_context_from_redis(effective_user_id) or {}
    if current_context:
        updated_context = update_state_after_action(current_context, "dashboard")
        _save_context_to_redis(effective_user_id, updated_context, ConversationState.DASHBOARD_AVAILABLE)
    
    # Return in the format expected by ScoutParser (text + attachments)
    return {
        "text": "I have created an interactive dashboard with comparative analysis. Click the button below to explore the data.",
        "attachments": [
            {
                "type": "url",
                "url": dashboard_url,
                "title": "View Dashboard"
            }
        ]
    }

dashboard_inline_tool = StructuredTool.from_function(
    func=_dashboard_inline_with_context,
    name="dashboard_inline",
    description=(
        "Generates an interactive dashboard with the base player and candidates. "
        "If no candidate_ids/base_id are provided, uses the latest recommendation list from Redis. "
        "The user context is automatically handled by the system."
    ),
    args_schema=DashboardInlineInput,
    return_direct=True  # Return directly - already in correct format with text + attachments
)

build_scouting_report_tool = StructuredTool.from_function(
    func=build_scouting_report,
    name="build_scouting_report",
    description=(
        "Generates a professional PDF scouting report using statistical data and current market context "
        "(recent news). The report includes technical analysis, pros, cons, and final recommendation. "
        "IMPORTANT: Use candidate_ids from the previous similar_players search, and pass target_team "
        "if the user specified a team to compute Success Index v2.1."
    ),
    args_schema=BuildScoutingReportInput,
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
