from fastapi import APIRouter, Depends, Query, Body, HTTPException
from sqlalchemy import select, func, literal, cast
from sqlalchemy.orm import Session
import numpy as np
from pgvector.sqlalchemy import Vector
from apps.ingestion.seed_and_ingest import Player   # modelo ya existente
from apps.agent_service.db import get_session
from typing import List
from decimal import Decimal
from pgvector.sqlalchemy import Vector as PGVector


def _serialize(v):
    """Convierte cualquier valor de SQLAlchemy a algo JSON-safe."""
    if v is None:
        return None

    # ── vectores o secuencias ───────────────────────────────
    if isinstance(v, (PGVector, list, tuple, np.ndarray)):
        # Asegura que *cada* elemento sea float/int nativo
        return [ _serialize(x) for x in list(v) ]

    # ── escalares numpy (np.float32, np.int64, …) ───────────
    if isinstance(v, np.generic):
        return v.item()           # → float / int de Python

    # ── Decimals opcionales ─────────────────────────────────
    if isinstance(v, Decimal):
        return float(v)

    # ── tipos ya serializables (str, int, float, datetime…) ─
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
        description="Lista de clubes a excluir, separados por coma"
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

    filters = [Player.id != player_id]  # nunca devolvemos al propio

    # ⬇️ 1. Excluir club del jugador base
    filters.append(Player.club != base.club)

    # ⬇️ 2. Excluir club(es) pasados por query
    if exclude_club:
        clubs_to_exclude = [c.strip() for c in exclude_club.split(",") if c.strip()]
        if clubs_to_exclude:
            filters.append(Player.club.notin_(clubs_to_exclude))

    # Resto de filtros de inclusión
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

@router.post("/batch", summary="Devuelve todas las métricas de varios jugadores")
def players_batch(
    ids: List[int] = Body(..., embed=True, example=[274, 311, 658]),
    db: Session = Depends(get_session),
):
    rows = db.query(Player).filter(Player.id.in_(ids)).all()

    if not rows:
        raise HTTPException(status_code=404, detail="No players found")

    return [player_to_dict(p) for p in rows]

@router.get("/players/search")
def search_players(query: str, limit: int = 5, db: Session = Depends(get_session)):
    rows = (
        db.query(Player.id, Player.full_name, Player.club, Player.position)
          .filter(Player.full_name.ilike(f"%{query}%"))
          .limit(limit)
          .all()
    )
    return [dict(r._mapping) for r in rows]