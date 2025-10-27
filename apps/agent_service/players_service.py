
from typing import Dict, Any, Optional
from apps.agent_service.db import get_session
from langchain.tools import tool

@tool(description="Returns role and stats of a player (PostgreSQL)")
def player_stats(player_name: str, team: Optional[str] = None) -> Dict[str, any]:
    """
    Reads the player from the database and returns:
      • role           → position
      • stats          → only scalar columns (lists/arrays excluded)
      • player_name    → full name
      • team           → club
      • nationality    → country
    
    Args:
        player_name: The name of the player to search for
        team: Optional team name to disambiguate when multiple players have the same name
    """
    #with get_session() as db:
    db = get_session()
    try:
        # Lazy import to avoid heavy side-effects at module import time
        from apps.ingestion.seed_and_ingest import Player
        query = db.query(Player).filter(Player.full_name.ilike(player_name))
        
        # If team is provided, also filter by team to disambiguate
        if team:
            query = query.filter(Player.club.ilike(f"%{team}%"))
        
        # Prioritize active players and most recent season
        # Use CASE to prioritize 'active' status over 'retired or inactive'
        from sqlalchemy import case
        row = query.order_by(
            case(
                (Player.player_status == 'active', 1),
                else_=0
            ).desc(),
            Player.season.desc(),          # Most recent season first
            Player.minutes.desc()          # More minutes played (more relevant)
        ).first()
        if row is None:
            raise ValueError(f"Player {player_name} not found")

        # --- clean the ORM dict ---
        stats = row.__dict__.copy()
        stats.pop("_sa_instance_state", None)
        # remove non-scalar columns that break tabulate/markdown
        stats.pop("feature_vector", None)

        return {
            "role":        row.position,
            "stats":       stats,          # clean dict, no arrays
            "player_name": row.full_name,
            "team":        row.club,
            "nationality": row.nationality,
        }
    finally:
        db.close()
