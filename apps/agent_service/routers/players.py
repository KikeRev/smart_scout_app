from fastapi import APIRouter, Depends, Query, Body, HTTPException
from sqlalchemy import select, func, literal, cast
from sqlalchemy.orm import Session
import numpy as np
from pgvector.sqlalchemy import Vector
from apps.ingestion.seed_and_ingest import Player   # existing model
from apps.agent_service.db import get_session
from typing import List
from decimal import Decimal
from pgvector.sqlalchemy import Vector as PGVector
from pydantic import BaseModel


class PlayerBatchRequest(BaseModel):
    player_ids: List[int]


def _serialize(v):
    """Converts any SQLAlchemy value to something JSON-safe."""
    if v is None:
        return None

    # ── vectors or sequences ───────────────────────────────
    if isinstance(v, (PGVector, list, tuple, np.ndarray)):
        # Ensures that *each* element is a native float/int
        return [ _serialize(x) for x in list(v) ]

    # ── numpy scalars (np.float32, np.int64, …) ───────────
    if isinstance(v, np.generic):
        return v.item()           # → Python float / int

    # ── optional Decimals ─────────────────────────────────
    if isinstance(v, Decimal):
        return float(v)

    # ── already serializable types (str, int, float, datetime…) ─
    return v

def player_to_dict(p: Player) -> dict:
    return {c.name: _serialize(getattr(p, c.name)) for c in Player.__table__.columns}

router = APIRouter(prefix="/players", tags=["players"])

@router.get("/{player_id}/similar")
def similar_players(
    player_id: int,
    nationality: str | None = Query(None),
    position: str | None = Query(None),
    min_minutes: int = Query(0, ge=0),
    max_age: int | None = Query(None, ge=0),
    exclude_club: str | None = Query(
        None,
        description="List of clubs to exclude, separated by comma"
    ),
    k: int = Query(15, le=100),
    db: Session = Depends(get_session),
):
    base = db.get(Player, player_id)
    if not base:
        raise HTTPException(404, "Player not found")
    
    base_vec = base.feature_vector
    if isinstance(base_vec, np.ndarray):
        base_vec = base_vec.tolist() 

    filters = [Player.id != player_id]  # never return the same player

    # ⬇️ 1. Exclude base player's club
    filters.append(Player.club != base.club)

    # ⬇️ 2. Exclude club(s) passed by query
    if exclude_club:
        clubs_to_exclude = [c.strip() for c in exclude_club.split(",") if c.strip()]
        if clubs_to_exclude:
            filters.append(Player.club.notin_(clubs_to_exclude))

    # Rest of inclusion filters
    if nationality:
        filters.append(Player.nationality == nationality)
    if position:
        filters.append(Player.position == position)
    if min_minutes:
        filters.append(Player.minutes >= min_minutes)
    if max_age:
        filters.append(Player.age <= max_age)

    dist_expr = func.cosine_distance(
                Player.feature_vector,
                cast(literal(base_vec), Vector(43))
            )

    sim_expr  = 1 - dist_expr                  

    stmt = (
        select(
            Player,
            sim_expr.label("similarity")        
        )
        .where(*filters)
        .order_by(sim_expr.desc())              
        .limit(k)
    )

    rows = db.execute(stmt).all()

    return [
        {
            "id": p.id,
            "full_name": p.full_name,
            "club": p.club,
            "dist": float(dist)     
        }
        for p, dist in rows
    ]

@router.post("/batch", summary="Returns all metrics for multiple players")
def players_batch(
    ids: List[int] = Body(..., embed=True, example=[274, 311, 658]),
    db: Session = Depends(get_session),
):
    rows = db.query(Player).filter(Player.id.in_(ids)).all()

    if not rows:
        raise HTTPException(status_code=404, detail="No players found")

    return [player_to_dict(p) for p in rows]

@router.get("/search")
def search_players(query: str, limit: int = 5, db: Session = Depends(get_session)):
    rows = (
        db.query(Player.id, Player.full_name, Player.club, Player.position)
          .filter(Player.full_name.ilike(f"%{query}%"))
          .limit(limit)
          .all()
    )
    return [dict(r._mapping) for r in rows]

@router.get("/all")
def get_all_players(limit: int = 20000, db: Session = Depends(get_session)):
    """Gets all players for dynamic filtering"""
    rows = (
        db.query(Player)
          .limit(limit)
          .all()
    )
    return {"players": [player_to_dict(p) for p in rows]}

@router.get("/filter-options")
def get_filter_options(db: Session = Depends(get_session)):
    """Gets unique options for filters without player limit"""
    # Get unique leagues
    leagues = db.query(Player.league).filter(Player.league.isnot(None)).distinct().all()
    leagues = [league[0] for league in leagues if league[0]]
    
    # Get unique clubs
    clubs = db.query(Player.club).filter(Player.club.isnot(None)).distinct().all()
    clubs = [club[0] for club in clubs if club[0]]
    
    # Get unique positions
    positions = db.query(Player.position).filter(Player.position.isnot(None)).distinct().all()
    positions = [position[0] for position in positions if position[0]]
    
    # Get unique nationalities
    nationalities = db.query(Player.nationality).filter(Player.nationality.isnot(None)).distinct().all()
    nationalities = [nationality[0] for nationality in nationalities if nationality[0]]
    
    return {
        "leagues": sorted(leagues),
        "clubs": sorted(clubs),
        "positions": sorted(positions),
        "nationalities": sorted(nationalities)
    }

@router.post("/details")
def get_players_details(request: PlayerBatchRequest, db: Session = Depends(get_session)):
    """Gets player details by their IDs for the dashboard"""
    player_ids = request.player_ids
    if not player_ids:
        return []
    
    players = (
        db.query(Player)
          .filter(Player.id.in_(player_ids))
          .all()
    )
    return [player_to_dict(p) for p in players]
