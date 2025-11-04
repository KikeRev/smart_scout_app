from fastapi import APIRouter, Depends, Query, Body, HTTPException
from sqlalchemy import select, func, literal, cast
from sqlalchemy.orm import Session
import numpy as np
from pgvector.sqlalchemy import Vector
from apps.ingestion.seed_and_ingest import Player   # existing model
from apps.agent_service.db import get_session
from typing import List, Optional
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

def player_to_light_dict(p: Player) -> dict:
    """Slim serialization for listings: excludes heavy fields like feature_vector."""
    data = player_to_dict(p)
    # Remove heavy/non-needed fields
    data.pop("feature_vector", None)
    return data

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
            "player_uid": p.player_uid,
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
            "player_uid": p.player_uid,
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
        db.query(Player.id, Player.player_uid, Player.full_name, Player.club, Player.position)
          .filter(Player.player_uid.ilike(f"%{query}%") | Player.full_name.ilike(f"%{query}%"))
          .limit(limit)
          .all()
    )
    return [dict(r._mapping) for r in rows]

@router.get("/all")
def get_all_players(
    limit: Optional[int] = Query(None, ge=1, le=100000),
    db: Session = Depends(get_session),
):
    """Gets players for dynamic filtering (deprecated for UI). Excludes feature_vector.

    Note: Kept for backwards compatibility. Prefer POST /players/search.
    """
    q = db.query(Player)
    if limit is not None:
        q = q.limit(limit)
    rows = q.all()
    return {"players": [player_to_light_dict(p) for p in rows]}

@router.get("/filter-options")
def get_filter_options(
    positions: Optional[List[str]] = Query(None),
    leagues: Optional[List[str]] = Query(None),
    clubs: Optional[List[str]] = Query(None),
    nationalities: Optional[List[str]] = Query(None),
    db: Session = Depends(get_session),
):
    """Gets unique options for filters, optionally conditioned by current selections."""
    q = db.query(Player)
    # Apply conditioning filters
    if positions:
        q = q.filter(Player.position.in_(positions))
    if leagues:
        q = q.filter(Player.league.in_(leagues))
    if clubs:
        q = q.filter(Player.club.in_(clubs))
    if nationalities:
        q = q.filter(Player.nationality.in_(nationalities))

    def distinct_list(col):
        return [v for (v,) in q.with_entities(col).filter(col.isnot(None)).distinct().all() if v]

    leagues_out = sorted(distinct_list(Player.league))
    clubs_out = sorted(distinct_list(Player.club))
    positions_out = sorted(distinct_list(Player.position))
    nationalities_out = sorted(distinct_list(Player.nationality))

    return {
        "leagues": leagues_out,
        "clubs": clubs_out,
        "positions": positions_out,
        "nationalities": nationalities_out,
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


# -------------------- New efficient endpoints --------------------

class SearchRequest(BaseModel):
    query: Optional[str] = None
    positions: Optional[List[str]] = None
    leagues: Optional[List[str]] = None
    clubs: Optional[List[str]] = None
    nationalities: Optional[List[str]] = None
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    min_minutes: Optional[int] = None
    page: int = 1
    per_page: int = 24
    order: Optional[str] = "minutes_desc"


@router.get("/lookup", summary="Quick lookup by name or uid (no vectors)")
def players_lookup(
    query: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_session),
):
    q = (
        db.query(Player)
        .with_entities(
            Player.id,
            Player.player_uid,
            Player.full_name,
            Player.club,
            Player.league,
            Player.position,
            Player.nationality,
            Player.age,
            Player.minutes,
            Player.team_logo,
        )
        .filter((Player.full_name.ilike(f"%{query}%")) | (Player.player_uid.ilike(f"%{query}%")))
        .limit(limit)
    )
    rows = [dict(r._mapping) for r in q.all()]
    return {"players": rows}


@router.post("/search", summary="Server-side filtered search with pagination (no vectors)")
def players_search(req: SearchRequest, db: Session = Depends(get_session)):
    q = db.query(Player)

    # Apply filters
    if req.query:
        q = q.filter((Player.full_name.ilike(f"%{req.query}%")) | (Player.player_uid.ilike(f"%{req.query}%")))
    if req.positions:
        q = q.filter(Player.position.in_(req.positions))
    if req.leagues:
        q = q.filter(Player.league.in_(req.leagues))
    if req.clubs:
        q = q.filter(Player.club.in_(req.clubs))
    if req.nationalities:
        q = q.filter(Player.nationality.in_(req.nationalities))
    if req.age_min is not None:
        q = q.filter(Player.age >= req.age_min)
    if req.age_max is not None:
        q = q.filter(Player.age <= req.age_max)
    if req.min_minutes is not None:
        q = q.filter(Player.minutes >= req.min_minutes)

    # Total count before pagination
    total = q.count()

    # Ordering
    if req.order == "minutes_desc":
        q = q.order_by(Player.minutes.desc())
    elif req.order == "age_asc":
        q = q.order_by(Player.age.asc())
    elif req.order == "age_desc":
        q = q.order_by(Player.age.desc())
    else:
        q = q.order_by(Player.full_name.asc())

    # Pagination
    page = max(1, req.page)
    per_page = max(1, min(100, req.per_page))
    offset = (page - 1) * per_page

    rows = (
        q.with_entities(
            Player.id,
            Player.player_uid,
            Player.full_name,
            Player.club,
            Player.league,
            Player.position,
            Player.nationality,
            Player.age,
            Player.minutes,
            Player.minutes_90s,
            Player.goals,
            Player.assists,
            Player.team_logo,
        )
        .offset(offset)
        .limit(per_page)
        .all()
    )

    players = [dict(r._mapping) for r in rows]
    return {"players": players, "total": total, "page": page, "per_page": per_page}
