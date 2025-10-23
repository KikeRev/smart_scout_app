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
from apps.agent_service.success_index_calculator import SuccessIndexCalculator


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

@router.get("/{player_id}/similar_team_fit", summary="Similar players with team-position fit index")
def similar_players_with_team_fit(
    player_id: int,
    team: str = Query(..., description="Target team (club) Y for fit computation"),
    position: str | None = Query(None, description="If not provided, base player's position is used"),
    k: int = Query(15, ge=1, le=100),
    min_minutes: int = Query(0, ge=0),
    max_age: int | None = Query(None, ge=0),
    exclude_club: str | None = Query(None, description="List of clubs to exclude, comma-separated"),
    overall_weight: float = Query(0.5, ge=0.0, le=1.0, description="Weight for overall similarity in success index"),
    db: Session = Depends(get_session),
):
    """
    Returns similar players to X and computes an additional similarity to the centroid of
    players from team Y who share the same position. The response includes an estimated
    success_index combining overall similarity and team-position fit similarity.
    """
    base = db.get(Player, player_id)
    if not base:
        raise HTTPException(404, "Player not found")

    pos = position or base.position
    if pos is None:
        raise HTTPException(400, "Position not provided and base player has no position")

    # Build cohort: players in target team Y with same position
    cohort_q = (
        db.query(Player.feature_vector)
          .filter(
              Player.club == team,
              Player.position == pos,
              Player.feature_vector.isnot(None)
          )
    )
    cohort = [fv[0] for fv in cohort_q.all()]
    if not cohort:
        # If no cohort found, we cannot compute team fit; degrade gracefully
        cohort_centroid = None
    else:
        # Compute centroid as mean of vectors
        # Ensure list of lists
        arr = np.vstack([
            fv if not isinstance(fv, np.ndarray) else fv.tolist() for fv in cohort
        ])
        centroid = arr.mean(axis=0)
        cohort_centroid = centroid.tolist() if isinstance(centroid, np.ndarray) else centroid

    # Fetch overall similar candidates (excluding same club by default)
    base_vec = base.feature_vector
    if isinstance(base_vec, np.ndarray):
        base_vec = base_vec.tolist()

    filters = [Player.id != player_id]

    # Exclude base player's club by default
    filters.append(Player.club != base.club)

    if exclude_club:
        clubs_to_exclude = [c.strip() for c in exclude_club.split(",") if c.strip()]
        if clubs_to_exclude:
            filters.append(Player.club.notin_(clubs_to_exclude))

    # Inclusion filters
    if pos:
        filters.append(Player.position == pos)
    if min_minutes:
        filters.append(Player.minutes >= min_minutes)
    if max_age is not None:
        filters.append(Player.age <= max_age)

    dist_expr = func.cosine_distance(
        Player.feature_vector,
        cast(literal(base_vec), Vector(43))
    )
    overall_sim = 1 - dist_expr

    stmt = (
        select(Player, overall_sim.label("overall_similarity"))
        .where(*filters)
        .order_by(overall_sim.desc())
        .limit(k)
    )

    rows = db.execute(stmt).all()

    def cosine_sim_to_centroid(vec: list[float] | np.ndarray, centroid_vec: list[float] | None) -> float | None:
        if centroid_vec is None or vec is None:
            return None
        v = vec.tolist() if isinstance(vec, np.ndarray) else vec
        # Compute cosine similarity
        a = np.array(v, dtype=float)
        b = np.array(centroid_vec, dtype=float)
        na = np.linalg.norm(a)
        nb = np.linalg.norm(b)
        if na == 0 or nb == 0:
            return None
        return float(np.dot(a, b) / (na * nb))

    # Base player's own fit to team Y position cohort
    base_team_fit = cosine_sim_to_centroid(base_vec, cohort_centroid)

    overall_w = overall_weight
    fit_w = 1.0 - overall_w

    results = []
    for p, ov_sim in rows:
        # p.feature_vector may be ndarray or list
        cand_vec = p.feature_vector.tolist() if isinstance(p.feature_vector, np.ndarray) else p.feature_vector
        team_fit = cosine_sim_to_centroid(cand_vec, cohort_centroid)
        # Success index base: weighted combination. If team_fit is None, fall back to overall only
        if team_fit is None:
            success_base = float(ov_sim)
        else:
            success_base = float(overall_w * ov_sim + fit_w * team_fit)

        # Calcular success_index v2.1 con todos los factores adicionales
        player_data = {
            'league': p.league,
            'minutes': p.minutes or 0,
            'age': p.age or 25,
            'club': p.club,
            'position': p.position,
            'goals_per90': p.goals_per90 or 0.0,
            'tackles': p.tackles or 0,
            'interceptions': p.interceptions or 0,
            'passes_pct': p.passes_pct or 0.0
        }
        
        success_v2_1 = SuccessIndexCalculator.calculate_success_index_v2_1(
            success_index_base=success_base,
            player_data=player_data,
            db=db
        )

        results.append({
            "id": p.id,
            "full_name": p.full_name,
            "club": p.club,
            "league": p.league,
            "position": p.position,
            "age": p.age,
            "minutes": p.minutes,
            "overall_similarity": float(ov_sim),
            "team_position_similarity": team_fit if team_fit is None else float(team_fit),
            "success_index": success_base,  # Mantener para retrocompatibilidad
            "success_index_v2_1": success_v2_1['success_index_v2_1'],
            "success_breakdown": success_v2_1['breakdown']
        })
    
    # Sort results by success_index_v2_1 descending
    results.sort(key=lambda x: x['success_index_v2_1'], reverse=True)

    return {
        "context": {
            "base_player_id": base.id,
            "base_full_name": base.full_name,
            "base_club": base.club,
            "position": pos,
            "target_team": team,
            "base_team_position_similarity": base_team_fit if base_team_fit is None else float(base_team_fit),
            "weights": {"overall": overall_w, "team_fit": fit_w},
            "cohort_size": len(cohort) if cohort else 0,
        },
        "candidates": results,
    }

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
def search_players(query: str, limit: int = 200, db: Session = Depends(get_session)):
    rows = (
        db.query(Player.id, Player.full_name, Player.club, Player.position)
          .filter(Player.full_name.ilike(f"%{query}%"))
          .limit(limit)
          .all()
    )
    return [dict(r._mapping) for r in rows]

@router.get("/all")
def get_all_players(limit: int = 47000, db: Session = Depends(get_session)):
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
