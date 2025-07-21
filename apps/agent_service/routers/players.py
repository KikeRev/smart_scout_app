from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func, literal, cast
from sqlalchemy.orm import Session
import numpy as np
from pgvector.sqlalchemy import Vector
from apps.ingestion.seed_and_ingest import Player   # modelo ya existente
from apps.agent_service.db import get_session

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
