from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func, literal
from pgvector.sqlalchemy import Vector
from apps.agent_service.db import get_session
from apps.ingestion.seed_and_ingest import FootballNews, player_news
from sentence_transformers import SentenceTransformer
import os, numpy as np
import sqlalchemy as sa

router = APIRouter(prefix="/news", tags=["news"])

# ---------- 1. Noticias por jugador ---------------------------------
@router.get("/players/{player_id}/news")
def player_news_endpoint(
    player_id: int,
    k: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_session),
):
    stmt = (
        select(FootballNews)
        .join(player_news, FootballNews.id == player_news.c.news_id)
        .where(player_news.c.player_id == player_id)
        .order_by(FootballNews.published_at.desc())
        .limit(k)
    )
    rows = db.execute(stmt).scalars().all()
    return [
        {
            "title": n.title,
            "url": n.url,
            "summary": n.summary,
            "content":n.article_text,
            "published_at": n.article_text,
            "source": n.source_id,
        }
        for n in rows
    ]


# ---------- 2. Búsqueda semántica global ----------------------------


# Reutiliza el embedder que ya usas en seed_and_ingest
_EMB_MODEL = os.getenv("EMB_MODEL", "sentence-transformers/all-mpnet-base-v2")
_embedder = SentenceTransformer(_EMB_MODEL)

EMB_DIM = 768  # la misma dimensión que usaste al crear la columna embedding

@router.get("/search")
def news_search_endpoint(
    query: str = Query(..., min_length=3),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_session),
):
    q_emb = _embedder.encode(query, convert_to_numpy=True).tolist()  # → list[float]

    query_vec = sa.cast(literal(q_emb), Vector(EMB_DIM))

    stmt = (
        select(
            FootballNews,
            func.cosine_distance(FootballNews.embedding, query_vec).label("dist")
        )
        .order_by("dist")
        .limit(limit)
    )
    rows = db.execute(stmt).all()

    return [
        {
            "title": n.title,
            "url": n.url,
            "summary": n.summary,
            "published_at": n.published_at,
            "distance": float(dist),
            "source": n.source_id,
        }
        for n, dist in rows
    ]
