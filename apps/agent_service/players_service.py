
from typing import Dict, Any
from apps.agent_service.db import get_session
from apps.ingestion.seed_and_ingest import Player       # tu modelo de jugadores
from langchain.tools import tool
import pandas as pd

@tool(description="Devuelve role y stats de un jugador (PostgreSQL)")
def player_stats(player_name: str) -> Dict[str, any]:
    """
    Lee el jugador en la BD y devuelve:
      • role           → posición
      • stats          → solo columnas escalares (listas/arrays excluidas)
      • player_name    → nombre completo
      • team           → club
      • nationality    → país
    """
    with get_session() as db:
        row = (
            db.query(Player)
              .filter(Player.full_name.ilike(player_name))
              .first()
        )
        if row is None:
            raise ValueError(f"Jugador {player_name} no encontrado")

        # --- limpia el dict del ORM ---
        stats = row.__dict__.copy()
        stats.pop("_sa_instance_state", None)
        # elimina columnas no escalares que rompen tabulate/markdown
        stats.pop("feature_vector", None)

        return {
            "role":        row.position,
            "stats":       stats,          # dict limpio, sin arrays
            "player_name": row.full_name,
            "team":        row.club,
            "nationality": row.nationality,
        }
