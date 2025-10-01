
from typing import Dict, Any
from apps.agent_service.db import get_session
from langchain.tools import tool

@tool(description="Returns role and stats of a player (PostgreSQL)")
def player_stats(player_name: str) -> Dict[str, any]:
    """
    Reads the player from the database and returns:
      • role           → position
      • stats          → only scalar columns (lists/arrays excluded)
      • player_name    → full name
      • team           → club
      • nationality    → country
    """
    #with get_session() as db:
    db = get_session()
    try:
        # Lazy import to avoid heavy side-effects at module import time
        from apps.ingestion.seed_and_ingest import Player
        row = (
            db.query(Player)
                .filter(Player.full_name.ilike(player_name))
                .first()
        )
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
