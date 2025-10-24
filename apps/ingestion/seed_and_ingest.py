"""
Seed script for Smart‑Scouting‑AI
---------------------------------
1. **Players**: load a CSV (see `CSV_COLUMN_MAP`) → PostgreSQL/pgvector
2. **News**: fetch RSS feeds, summarise, embed, upsert.

Run:
```bash
# bootstrap DB + ingest players + news
python -m apps.ingestion.seed_and_ingest \
       --players-csv data/all_players_cleaned.csv \
       --ingest-news
```
Add `--help` for CLI flags.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

import pandas as pd
import sqlalchemy as sa
from newspaper import Article
from sentence_transformers import SentenceTransformer
from sqlalchemy import orm
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base
from pgvector.sqlalchemy import Vector
from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM
from bs4 import BeautifulSoup
import requests
import torch
from transformers import logging as hf_logging
import feedparser
from tqdm.auto import tqdm
from pgvector.sqlalchemy import Vector
from sklearn.preprocessing import StandardScaler
import unicodedata, unidecode, re
from sqlalchemy.dialects.postgresql import insert as pg_insert

hf_logging.set_verbosity_error()

DIM = 43  # Feature vector dimension (adjust according to model) 

# outside functions, so it loads once
_SUMMARIZER = pipeline(
    task="summarization",
    model="facebook/bart-large-cnn",   # or t5-small / pegasus
    device=0 if torch.cuda.is_available() else -1,
)
# tokenizer to count tokens (optional, if you want to chunk very long articles)
_TOKENIZER = AutoTokenizer.from_pretrained("facebook/bart-large-cnn")

MAX_TOKENS = 1024 

EMB_MODEL = "sentence-transformers/all-mpnet-base-v2"  # 768 d
embedder = SentenceTransformer(EMB_MODEL)

EMB_DIM = 768

# ───  helper  ────────────────────────────────────────────────────────────
_WS_RE = re.compile(r"\s+")
_WS = re.compile(r"\s+")

# ---------------------------------------------------------------------------
#  DB setup
# ---------------------------------------------------------------------------

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://scout:scout@localhost:5432/scouting"
)
Base = declarative_base()


# ---------------------------------------------------------------------------
#  Player model (aligned with CSV_COLUMN_MAP values)
# ---------------------------------------------------------------------------

class PlayerHistory(Base):
    """
    PlayerHistory model for storing historical player statistics by season.
    Each row represents a player's statistics for a specific season.
    Used for evolution charts in player dashboards.
    """
    __tablename__ = "player_history"
    
    # Primary key
    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    player = sa.Column(sa.String(255), nullable=False, index=True)
    player_uid = sa.Column(sa.String(255), nullable=True, index=True)
    season = sa.Column(sa.String(10), nullable=False, index=True)
    
    # Team and league info
    team = sa.Column(sa.String(128))
    league = sa.Column(sa.String(64))
    team_logo = sa.Column(sa.Text)
    
    # Basic info
    nationality = sa.Column(sa.String(64))
    position = sa.Column(sa.String(32))
    age = sa.Column(sa.Integer)
    
    # Playing time
    games = sa.Column(sa.Integer)
    games_starts = sa.Column(sa.Integer)
    minutes = sa.Column(sa.Integer)
    minutes_90s = sa.Column(sa.Float)
    
    # Performance metrics
    goals = sa.Column(sa.Integer)
    assists = sa.Column(sa.Integer)
    expected_goals = sa.Column(sa.Float)
    expected_assists = sa.Column(sa.Float)
    
    # Advanced metrics
    progressive_carries = sa.Column(sa.Integer)
    progressive_passes = sa.Column(sa.Integer)
    progressive_passes_received = sa.Column(sa.Integer)
    
    # Per 90 stats
    goals_per90 = sa.Column(sa.Float)
    assists_per90 = sa.Column(sa.Float)
    goals_assists_per90 = sa.Column(sa.Float)
    expected_goals_per90 = sa.Column(sa.Float)
    expected_assists_per90 = sa.Column(sa.Float)
    
    # Passing
    passes_completed = sa.Column(sa.Integer)
    passes = sa.Column(sa.Integer)
    passes_pct = sa.Column(sa.Float)
    
    # Defensive
    tackles = sa.Column(sa.Integer)
    tackles_won = sa.Column(sa.Integer)
    interceptions = sa.Column(sa.Integer)
    blocks = sa.Column(sa.Integer)
    clearances = sa.Column(sa.Integer)
    
    # Timestamps
    created_at = sa.Column(sa.DateTime, server_default=sa.func.now())
    updated_at = sa.Column(sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now())
    
    # Unique constraint on player + season
    __table_args__ = (
        sa.UniqueConstraint('player', 'season', name='uq_player_season'),
        sa.Index('idx_player_season', 'player', 'season'),
    )


class Player(Base):
    __tablename__ = "players"

    id = sa.Column(sa.Integer, primary_key=True)
    full_name = sa.Column(sa.Text, nullable=False, index=True)
    player_uid = sa.Column(sa.String(255), nullable=True, unique=True, index=True)
    age = sa.Column(sa.Integer)
    nationality = sa.Column(sa.String(64))
    position = sa.Column(sa.String(32))
    club = sa.Column(sa.String(128))
    team_logo = sa.Column(sa.Text)
    league = sa.Column(sa.String(64))
    season = sa.Column(sa.String(10), index=True)

    minutes = sa.Column(sa.Integer)
    minutes_90s = sa.Column(sa.Float)
    goals = sa.Column(sa.Integer)
    assists = sa.Column(sa.Integer)

    expected_goals = sa.Column(sa.Float)
    expected_assists = sa.Column(sa.Float)
    no_penalty_expected_goals_plus_expected_assists = sa.Column(sa.Float)

    progressive_carries = sa.Column(sa.Integer)
    progressive_passes = sa.Column(sa.Integer)
    progressive_passes_received = sa.Column(sa.Integer)

    goals_per90 = sa.Column(sa.Float)
    assists_per90 = sa.Column(sa.Float)
    goals_assists_per90 = sa.Column(sa.Float)

    expected_goals_per90 = sa.Column(sa.Float)
    expected_assists_per90 = sa.Column(sa.Float)
    expected_goals_assists_per90 = sa.Column(sa.Float)

    gk_goals_against = sa.Column(sa.Integer)
    gk_pens_allowed = sa.Column(sa.Integer)
    gk_free_kick_goals_against = sa.Column(sa.Integer)
    gk_corner_kick_goals_against = sa.Column(sa.Integer)
    gk_own_goals_against = sa.Column(sa.Integer)
    gk_psxg = sa.Column(sa.Float)
    gk_psnpxg_per_shot_on_target_against = sa.Column(sa.Float)

    passes_completed = sa.Column(sa.Integer)
    passes = sa.Column(sa.Integer)
    passes_pct = sa.Column(sa.Float)
    passes_progressive_distance = sa.Column(sa.Integer)
    passes_completed_long = sa.Column(sa.Integer)
    passes_long = sa.Column(sa.Integer)
    passes_pct_long = sa.Column(sa.Float)

    tackles = sa.Column(sa.Integer)
    tackles_won = sa.Column(sa.Integer)
    challenge_tackles = sa.Column(sa.Integer)
    challenges = sa.Column(sa.Integer)
    challenge_tackles_pct = sa.Column(sa.Float)
    challenges_lost = sa.Column(sa.Integer)

    blocks = sa.Column(sa.Integer)
    blocked_shots = sa.Column(sa.Integer)
    blocked_passes = sa.Column(sa.Integer)
    interceptions = sa.Column(sa.Integer)
    tackles_interceptions = sa.Column(sa.Integer)
    clearances = sa.Column(sa.Integer)
    errors = sa.Column(sa.Integer)

    # Historical player fields
    player_status = sa.Column(sa.String(20), default='active')

    # optional: pgvector column for aggregated numerical vector
    feature_vector = sa.Column(Vector(DIM))


class PlayerRating(Base):
    """
    FIFA-style ratings calculated for each player.
    Automatically updated whenever the players table is updated.
    """
    __tablename__ = "player_ratings"
    
    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    player_id = sa.Column(sa.Integer, sa.ForeignKey('players.id', ondelete='CASCADE'), nullable=False, index=True)
    player_uid = sa.Column(sa.String(255), nullable=True, index=True)
    
    # Overall rating
    overall_rating = sa.Column(sa.Integer, nullable=False)  # Final OVR (0-100)
    
    # OVR components
    league_base_rating = sa.Column(sa.Float)  # Base rating by league
    performance_rating = sa.Column(sa.Float)  # Performance-based rating
    
    # Attributes by category (0-100)
    att = sa.Column(sa.Integer)  # Attacking
    ply = sa.Column(sa.Integer)  # Playmaking
    def_rating = sa.Column(sa.Integer)  # Defending (renamed to avoid reserved word conflict)
    ctr = sa.Column(sa.Integer)  # Ball Control
    phy = sa.Column(sa.Integer)  # Physical
    gkp = sa.Column(sa.Integer)  # Goalkeeping (NULL for non-goalkeepers)
    
    # Metadata
    season = sa.Column(sa.String(10), index=True)
    position = sa.Column(sa.String(32))
    minutes_played = sa.Column(sa.Integer)
    
    # Timestamps
    created_at = sa.Column(sa.DateTime, server_default=sa.func.now())
    updated_at = sa.Column(sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now())
    
    # Indexes and constraints
    __table_args__ = (
        sa.UniqueConstraint('player_id', 'season', name='uq_player_rating_season'),
        sa.Index('idx_overall_rating', 'overall_rating'),
        sa.Index('idx_player_season_rating', 'player_id', 'season'),
    )


class FootballNews(Base):
    __tablename__ = "football_news"

    id           = sa.Column(sa.Integer, primary_key=True)
    url          = sa.Column(sa.Text, unique=True, nullable=False)
    title        = sa.Column(sa.Text, nullable=False)
    published_at = sa.Column(sa.DateTime(timezone=True), index=True)
    article_text = sa.Column(sa.Text)
    summary      = sa.Column(sa.Text)
    embedding    = sa.Column(Vector(EMB_DIM))           # pgvector
    source_id    = sa.Column(sa.String(50))
    article_meta = sa.Column(sa.JSON, nullable=True)  # <— instead of `metadata`


player_news = sa.Table(
    "player_news",
    Base.metadata,
    sa.Column("player_id", sa.Integer, sa.ForeignKey("players.id", ondelete="CASCADE")),
    sa.Column("news_id",   sa.Integer, sa.ForeignKey("football_news.id", ondelete="CASCADE")),
    sa.Column("player_club", sa.String(128), nullable=True),
    sa.Column("player_league", sa.String(64), nullable=True),
    sa.Column("linked_at", sa.DateTime, server_default=sa.func.now()),
    sa.PrimaryKeyConstraint("player_id", "news_id"),
)

# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def get_engine(echo: bool = False) -> sa.Engine:
    return sa.create_engine(DATABASE_URL, echo=echo, future=True)


def create_tables(engine):
    # Ensure that the vector extension exists
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector;")
    Base.metadata.create_all(engine)

# --------------------------- CSV ingest -------------------------

CSV_COLUMN_MAP = {
    "player": "full_name",
    "player_uid": "player_uid",
    "age": "age",
    "nationality": "nationality",
    "position": "position",
    "Team": "club",
    "Team_Logo": "team_logo",
    "League": "league",
    "minutes": "minutes",
    "minutes_90s": "minutes_90s",
    "goals": "goals",
    "assists": "assists",
    "xg": "expected_goals",
    "xg_assist": "expected_assists",
    "npxg_xg_assist": "no_penalty_expected_goals_plus_expected_assists",
    "progressive_carries": "progressive_carries",
    "progressive_passes": "progressive_passes",
    "progressive_passes_received": "progressive_passes_received",
    "goals_per90": "goals_per90",
    "assists_per90": "assists_per90",
    "goals_assists_per90": "goals_assists_per90",
    "xg_per90": "expected_goals_per90",
    "xg_assist_per90": "expected_assists_per90",
    "xg_xg_assist_per90": "expected_goals_assists_per90",
    "gk_goals_against": "gk_goals_against",
    "gk_pens_allowed": "gk_pens_allowed",
    "gk_free_kick_goals_against": "gk_free_kick_goals_against",
    "gk_corner_kick_goals_against": "gk_corner_kick_goals_against",
    "gk_own_goals_against": "gk_own_goals_against",
    "gk_psxg": "gk_psxg",
    "gk_psnpxg_per_shot_on_target_against": "gk_psnpxg_per_shot_on_target_against",
    "passes_completed": "passes_completed",
    "passes": "passes",
    "passes_pct": "passes_pct",
    "passes_progressive_distance": "passes_progressive_distance",
    "passes_completed_long": "passes_completed_long",
    "passes_long": "passes_long",
    "passes_pct_long": "passes_pct_long",
    "tackles": "tackles",
    "tackles_won": "tackles_won",
    "challenge_tackles": "challenge_tackles",
    "challenges": "challenges",
    "challenge_tackles_pct": "challenge_tackles_pct",
    "challenges_lost": "challenges_lost",
    "blocks": "blocks",
    "blocked_shots": "blocked_shots",
    "blocked_passes": "blocked_passes",
    "interceptions": "interceptions",
    "tackles_interceptions": "tackles_interceptions",
    "clearances": "clearances", 
    "errors": "errors",
    # Historical fields
    "player_status": "player_status",
    "Season": "season",
}

REQUIRED_COLUMNS = set(CSV_COLUMN_MAP.keys())
NUMERIC_RE = re.compile(r"[^0-9\-.]+")


def _to_float(x):
    if pd.isna(x) or x == "":
        return 0.0
    if isinstance(x, str):
        x = NUMERIC_RE.sub("", x)
    try:
        return round(float(x), 3)
    except ValueError:
        return 0.0


def _to_int(x):
    return int(_to_float(x))

def clean_name(name: str) -> str:
    """Normalize tildes, remove rare characters and collapse spaces."""
    # Guard against non-string values and NaN
    if pd.isna(name):
        return ""
    if not isinstance(name, str):
        try:
            name = str(name)
        except Exception:
            return ""
    if name.lower() in {"nan", "none", "null"}:
        return ""
    # 1) Normalize to NFKD and remove diacritics
    name_ascii = (
        unicodedata.normalize("NFKD", name)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    # 2) Collapse spaces and remove initial/final spaces
    name_ascii = _WS_RE.sub(" ", name_ascii).strip()
    # 3) Convert to Title Case (optional)
    return name_ascii.title()


def load_players(engine: sa.Engine, csv_path: Path,  if_exists: str = "append"):
    df = pd.read_csv(csv_path)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        sys.exit(f"CSV missing columns: {missing}")

    df = df[list(CSV_COLUMN_MAP.keys())].rename(columns=CSV_COLUMN_MAP)

    # Conversions --------------------------------------------------
    int_cols = [
        "age",
        "minutes",
        "progressive_carries",
        "progressive_passes",
        "progressive_passes_received",
        "gk_goals_against",
        "gk_pens_allowed",
        "gk_free_kick_goals_against",
        "gk_corner_kick_goals_against",
        "gk_own_goals_against",
        "passes_completed",
        "passes",
        "passes_completed_long",
        "passes_long",
        "tackles",
        "tackles_won",
        "challenge_tackles",
        "challenges",
        "challenges_lost",
        "blocks",
        "blocked_shots",
        "blocked_passes",
        "interceptions",
        "tackles_interceptions",
        "clearances",
        "errors",
    ]

    df["full_name"] = df["full_name"].apply(clean_name)

    for col in int_cols:
        df[col] = df[col].apply(_to_int)

    float_cols = list(
        set(df.columns)
        - set(int_cols)
        - {"full_name", "nationality", "position", "club", "team_logo", "league", "player_status", "season", "player_uid"}
    )
    for col in float_cols:
        df[col] = df[col].apply(_to_float)

    if if_exists == "replace":
        with engine.begin() as conn:
            conn.execute(sa.text("""
                TRUNCATE TABLE players, player_news
                RESTART IDENTITY CASCADE
            """))
    print(f"🔎 Upserting {len(df)} players")
    df.to_sql("players", con=engine, if_exists="append", index=False, method="multi", chunksize=1000)
    print(f"✅ Players upserted: {len(df)}")


# ----------------- News scraping & embedding --------------------

FEEDS: List[Tuple[str, str]] = [
    ("as_la_liga", "https://feeds.as.com/mrss-s/pages/as/site/as.com/section/futbol/subsection/primera/"),
    ("as_la_liga_hypermotion", "https://feeds.as.com/mrss-s/pages/as/site/as.com/section/futbol/subsection/segunda/"),
    ("as_champions_league", "https://feeds.as.com/mrss-s/pages/as/site/as.com/section/futbol/subsection/champions/"),
    ("marca_primera_division", "https://e00-marca.uecdn.es/rss/futbol/primera-division.xml"),
    ("marca_segunda_division", "https://e00-marca.uecdn.es/rss/futbol/segunda-division.xml"),
    ("marca_champions_league", "https://e00-marca.uecdn.es/rss/futbol/champions-league.xml"),
    ("marca_premier_league", "https://e00-marca.uecdn.es/rss/futbol/premier-league.xml"),
    ("marca_bundesliga", "https://e00-marca.uecdn.es/rss/futbol/bundesliga.xml"),
    ("marca_seria_a", "https://e00-marca.uecdn.es/rss/futbol/liga-italiana.xml"),
    ("marca_ligue_1", "https://e00-marca.uecdn.es/rss/futbol/liga-francesa.xml"),
    ("marca_america", "https://e00-marca.uecdn.es/rss/futbol/america.xml"),
    ("transfermarkt_es","https://www.transfermarkt.es/rss/news"),
    ("transfermarkt_uk","https://www.transfermarkt.co.uk/rss/news"),
    ("transfermarkt_it","https://www.transfermarkt.it/rss/news"),
    ("transfermarkt_de","https://www.transfermarkt.de/rss/news"),
    ("transfermarkt_pt","https://www.transfermarkt.pt/rss/news"),
]
def fetch_rss_items() -> List[dict]:
    """Return list of dicts with keys: source, title, url, published_at (UTC)."""

    items: List[dict] = []
    now = datetime.now(tz=timezone.utc)

    for source_id, feed_url in FEEDS:
        try:
            parsed = feedparser.parse(feed_url)
        except Exception as exc:
            print(f"[feed-error] {source_id}: {exc}")
            continue

        for entry in parsed.entries:
            # Robust date handling ------------------------------------------------
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                published_at = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
            else:
                published_at = now

            items.append(
                {
                    "source": source_id,
                    "title": entry.title,
                    "url": entry.link,
                    "published_at": published_at,
                }
            )
    return items


# ----------------- Article parsing & embeddings ------------------

def safe_summarize(text: str) -> str:
    """
    Resume a text with automatic length adjustment and
    fallback if the model fails.
    """
    try:
        # real tokens of the chunk
        n_tokens = len(_TOKENIZER(text).input_ids)

        # We want something shorter than the original but > min_length
        max_len = max(20, int(n_tokens * 0.8))    # 80 % of the size
        max_len = min(max_len, 128)               # never > 128
        min_len = max(10, int(max_len * 0.25))    # 25 % of the max_len

        return _SUMMARIZER(
            text,
            max_length=max_len,
            min_length=min_len,
            do_sample=False,
        )[0]["summary_text"]

    except Exception:
        # fallback: first 400 characters
        return text[:400] + "…"

def parse_article(url: str) -> tuple[str, str] | None:
    try:
        html = requests.get(url, timeout=10).text
    except requests.RequestException:
        return None

    soup = BeautifulSoup(html, "lxml")
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

    if len(text.split()) < 20:
        return None

    # Split by tokens ≤1024 for BART
    tokens = _TOKENIZER(text).input_ids
    chunks = []
    while tokens:
        chunk_ids, tokens = tokens[:1024], tokens[1024:]
        chunks.append(_TOKENIZER.decode(chunk_ids, skip_special_tokens=True))

    # Hierarchical summary
    summaries = [safe_summarize(c) for c in chunks]
    full_summary = safe_summarize(" ".join(summaries))
    return text, full_summary


def embed_texts(texts: list[str], verbose: bool = False) -> list[list[float]]:
    # Filter null and empty
    valid_texts = [t for t in texts if t]
    if not valid_texts:
        return []
    
    print(f"🔎 Embedding {len(valid_texts)} documentos…", flush=True)
    
    return embedder.encode(
        valid_texts,
        batch_size=32,
        show_progress_bar=verbose,
        convert_to_numpy=True,
    ).tolist()


def ingest_news(engine: sa.Engine, verbose: bool = False):
    items = sorted(fetch_rss_items(), key=lambda x: x["published_at"], reverse=True)
    print(f"Fetched {len(items)} RSS items → processing …", flush=True)

    texts:      list[str]  = []   # artículo completo
    summaries:  list[str]  = []   # resumen
    metas:      list[dict] = []   # metadatos URL, título, fecha…

    for meta in tqdm(items, desc="Parsing", unit="article",
                     disable=not verbose, dynamic_ncols=True):
        try:
            # ── parse the article and summarize ───────────────────────────────
            parsed = parse_article(meta["url"])

            # ── discard the ones that don't return anything ────────────────────────
            if parsed is None:
                continue

            text, summary = parsed
            texts.append(text)
            summaries.append(summary)
            metas.append(meta)

        except Exception as exc:
            print(f"[article-error] {meta['url']}: {exc}")

    if not summaries:
        print("No articles parsed, skipping embeddings.")
        return

    # Use SUMMARIES (or texts) for the embedding; the two have the same len
    embeddings = embed_texts(texts, verbose=verbose)

    with orm.Session(engine) as session:
        inserted = 0
        for text, summary, emb, meta in tqdm(
            zip(texts, summaries, embeddings, metas),
            total=len(metas),
            desc="DB upsert",
            unit="row", 
            disable=not verbose, 
            dynamic_ncols=True
        ):
            if session.query(FootballNews).filter_by(url=meta["url"]).first():
                continue  # duplicate

            session.add(
                FootballNews(
                    url         = meta["url"],
                    title       = meta["title"],
                    published_at= meta["published_at"],
                    article_text= text,
                    summary     = summary,
                    embedding   = list(map(float, emb)),
                    source_id   = meta["source"],
                    article_meta= {"source": meta["source"]},
                )
            )
            inserted += 1
        session.commit()

    print(f"✅ News upserted: {inserted}")

# ---------------------------------------------------------------------------
#  ==  Embedding / Standard‑Scaler pipeline for players  ====================
# ---------------------------------------------------------------------------

PLAYER_DIM = 43                # 43 stats + minutes_90s (🗒️ adjust if you change)
IVF_LISTS  = 140                # number of lists for ivfflat

FEATURE_COLS = [
    "minutes", "minutes_90s",
    "goals", "assists",
    "expected_goals", "expected_assists",
    "no_penalty_expected_goals_plus_expected_assists",
    "progressive_carries", "progressive_passes", "progressive_passes_received",
    "goals_per90", "assists_per90", "goals_assists_per90",
    "expected_goals_per90", "expected_assists_per90", "expected_goals_assists_per90",
    "gk_goals_against", "gk_pens_allowed", "gk_free_kick_goals_against",
    "gk_corner_kick_goals_against", "gk_own_goals_against",
    "gk_psxg", "gk_psnpxg_per_shot_on_target_against",
    "passes_completed", "passes", "passes_pct",
    "passes_progressive_distance", "passes_completed_long", "passes_long",
    "passes_pct_long", "tackles", "tackles_won", "challenge_tackles",
    "challenges", "challenge_tackles_pct", "challenges_lost", "blocks",
    "blocked_shots", "blocked_passes", "interceptions",
    "tackles_interceptions", "clearances", "errors",
]

assert len(FEATURE_COLS) == PLAYER_DIM, "Dim mismatch ‑ adjust FEATURE_COLS"

def prepare_pgvector(engine: sa.Engine):
    """Ensure pgvector extension + index exist (idempotent)."""
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector;")
        conn.exec_driver_sql(f"""
           ALTER TABLE players
             ADD COLUMN IF NOT EXISTS feature_vector vector({PLAYER_DIM});
        """)
        #  index
        conn.exec_driver_sql(f"""
           CREATE INDEX IF NOT EXISTS players_feature_vec_idx
             ON players USING ivfflat (feature_vector vector_cosine_ops)
             WITH (lists = {IVF_LISTS});
        """)

def compute_and_store_player_vectors(engine: sa.Engine, refresh: bool=False):
    """Compute Standard‑Scaled vectors and persist to DB (pgvector)."""
    prepare_pgvector(engine)

    query_cols = ["id"] + FEATURE_COLS
    df = pd.read_sql(
        f"SELECT {', '.join(query_cols)} FROM players", engine
    )

    if df.empty:
        print("⚠️  No players found – skipping vector generation.")
        return

    if not refresh:
        # Quick check – if any row already has vector skip unless refresh
        existing = engine.execute(sa.text(
            "SELECT COUNT(*) FROM players WHERE feature_vector IS NOT NULL"
        )).scalar()
        if existing == len(df):
            print("🟢 Player vectors already present. Use --refresh-embs to recompute.")
            return

    # -------  Standardize ---------------------------------------------------
    scaler = StandardScaler()
    vec_matrix = scaler.fit_transform(df[FEATURE_COLS]).astype("float32")
    df["feature_vector"] = [v.tolist() for v in vec_matrix]

    # -------  Bulk update ---------------------------------------------------
    with engine.begin() as conn:
        conn.execute(
            sa.text("""
                UPDATE players
                SET feature_vector = :vec
                WHERE id = :pid
            """),
            [{"pid": pid, "vec": vec}
             for pid, vec in zip(df.id, df.feature_vector)]
        )

    print(f"✅  Player embeddings stored: {len(df)} rows")

# ---------------------------------------------------------------------------
#  ==  Player ⇄ News linker  ================================================
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    """lower‑case, strip diacritics & collapse spaces – for matching."""
    if not text:
        return ""
    text = unidecode.unidecode(
        unicodedata.normalize("NFKD", text)
    ).lower()
    return _WS.sub(" ", text).strip()

def _get_club_variations(club: str) -> set:
    """
    Return normalized variations of club name for matching in titles.
    Handles common abbreviations and alternative names.
    """
    if not club or club == 'Unknown':
        return set()
    
    club_lower = _norm(club)
    variations = {club_lower}
    
    # Map of full club names to their common variations
    club_map = {
        'manchester city': {'man city', 'manchester city', 'mcfc'},
        'manchester united': {'man united', 'man utd', 'manchester united', 'mufc'},
        'real madrid': {'real madrid', 'madrid', 'real'},
        'atletico madrid': {'atletico madrid', 'atletico', 'atleti'},
        'barcelona': {'barcelona', 'barca', 'barça', 'fcb'},
        'paris saint germain': {'psg', 'paris saint germain', 'paris sg', 'paris'},
        'bayern munich': {'bayern munich', 'bayern', 'fc bayern'},
        'borussia dortmund': {'borussia dortmund', 'dortmund', 'bvb'},
        'inter milan': {'inter milan', 'inter'},
        'ac milan': {'ac milan', 'milan'},
        'liverpool': {'liverpool', 'lfc'},
        'chelsea': {'chelsea', 'cfc'},
        'arsenal': {'arsenal', 'afc'},
        'tottenham': {'tottenham', 'spurs', 'tottenham hotspur'},
        'real betis': {'real betis', 'betis'},
        'sevilla': {'sevilla', 'sevilla fc'},
        'villarreal': {'villarreal', 'villarreal cf'},
        'athletic bilbao': {'athletic bilbao', 'athletic', 'athletic club'},
        'valencia': {'valencia', 'valencia cf'},
        'real sociedad': {'real sociedad', 'la real', 'sociedad'},
        'juventus': {'juventus', 'juve'},
        'napoli': {'napoli', 'ssc napoli'},
        'roma': {'roma', 'as roma'},
        'lazio': {'lazio', 'ss lazio'},
        'ajax': {'ajax', 'afc ajax'},
        'benfica': {'benfica', 'sl benfica'},
        'porto': {'porto', 'fc porto'},
        'sporting': {'sporting', 'sporting cp', 'sporting lisboa'},
    }
    
    # Find matching club and add variations
    for full_name, abbrevs in club_map.items():
        if full_name in club_lower or club_lower in full_name:
            variations.update(abbrevs)
            break
    
    return variations

def ensure_link_index(engine: sa.Engine):
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS player_news (
              player_id     INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
              news_id       INTEGER NOT NULL REFERENCES football_news(id) ON DELETE CASCADE,
              player_club   VARCHAR(128),
              player_league VARCHAR(64),
              linked_at     TIMESTAMP DEFAULT NOW(),
              PRIMARY KEY (player_id, news_id)
            );
            """
        )
        conn.exec_driver_sql(
            """
            CREATE INDEX IF NOT EXISTS player_news_player_idx
              ON player_news(player_id);
            """
        )
        conn.exec_driver_sql(
            """
            CREATE INDEX IF NOT EXISTS player_news_club_idx
              ON player_news(player_club);
            """
        )

def link_player_news(engine: sa.Engine, only_new: bool = True) -> None:
    """
    Link news to players by matching ONLY in article TITLE:
    1. Player name in title, OR
    2. Player's club in title
    
    This ensures only relevant news where the player is a protagonist,
    reduces token usage, and improves precision.
    
    Args:
        engine: SQLAlchemy engine
        only_new: If True, only process articles not yet linked
    """
    ensure_link_index(engine)

    with orm.Session(engine) as sess:
        # 1️⃣ Build mapping: normalized_name → list of {id, name, club, league}
        from collections import defaultdict
        name_to_players = defaultdict(list)
        
        for pid, name, club, league in sess.query(
            Player.id, 
            Player.full_name, 
            Player.club, 
            Player.league
        ):
            normalized_name = _norm(name)
            name_to_players[normalized_name].append({
                'id': pid,
                'full_name': name,
                'club': club or 'Unknown',
                'league': league or 'Unknown'
            })

        if not name_to_players:
            print("⚠️  No players to link – skipping player_news linking.")
            return

        # 2️⃣ Build regex pattern for player names
        pattern = r"\b(" + "|".join(re.escape(n) for n in name_to_players) + r")\b"
        name_re = re.compile(pattern, re.I)

        # 3️⃣ Get articles to process (ONLY TITLE)
        q = sess.query(FootballNews.id, FootballNews.title)
        if only_new:
            q = q.filter(
                ~FootballNews.id.in_(
                    sess.query(player_news.c.news_id).distinct()
                )
            )

        rows = q.all()
        if not rows:
            print("🟢  No new articles to link.")
            return

        inserted = 0
        player_name_matches = 0
        club_matches = 0
        ambiguous_links = 0
        
        for news_id, title in tqdm(rows, desc="Linking news↔players (title only)", unit="article"):
            if not title:
                continue
                
            title_normalized = _norm(title)
            
            # 🎯 STRATEGY 1: Check if player NAME is in title
            player_matches_in_title = {_norm(m.group(0)) for m in name_re.finditer(title)}
            
            if player_matches_in_title:
                # Player name found in title → link based on disambiguation
                for normalized_name in player_matches_in_title:
                    players = name_to_players.get(normalized_name, [])
                    
                    if len(players) == 1:
                        # Single player with this name → direct link
                        pdata = players[0]
                        stmt = pg_insert(player_news).values(
                            player_id=pdata['id'],
                            news_id=news_id,
                            player_club=pdata['club'],
                            player_league=pdata['league']
                        )
                        stmt = stmt.on_conflict_do_nothing()
                        sess.execute(stmt)
                        inserted += 1
                        player_name_matches += 1
                    else:
                        # Multiple players with same name → try club disambiguation
                        matched = False
                        for pdata in players:
                            club_variations = _get_club_variations(pdata['club'])
                            if any(var in title_normalized for var in club_variations):
                                stmt = pg_insert(player_news).values(
                                    player_id=pdata['id'],
                                    news_id=news_id,
                                    player_club=pdata['club'],
                                    player_league=pdata['league']
                                )
                                stmt = stmt.on_conflict_do_nothing()
                                sess.execute(stmt)
                                inserted += 1
                                player_name_matches += 1
                                matched = True
                        
                        if not matched:
                            # Ambiguous: club not mentioned, link to all
                            for pdata in players:
                                stmt = pg_insert(player_news).values(
                                    player_id=pdata['id'],
                                    news_id=news_id,
                                    player_club=pdata['club'],
                                    player_league=pdata['league']
                                )
                                stmt = stmt.on_conflict_do_nothing()
                                sess.execute(stmt)
                                inserted += 1
                                ambiguous_links += 1
            else:
                # 🎯 STRATEGY 2: Player name NOT in title → check if CLUB is in title
                for normalized_name, players in name_to_players.items():
                    for pdata in players:
                        club_variations = _get_club_variations(pdata['club'])
                        
                        # If player's club is mentioned in title → link
                        if any(var in title_normalized for var in club_variations):
                            stmt = pg_insert(player_news).values(
                                player_id=pdata['id'],
                                news_id=news_id,
                                player_club=pdata['club'],
                                player_league=pdata['league']
                            )
                            stmt = stmt.on_conflict_do_nothing()
                            sess.execute(stmt)
                            inserted += 1
                            club_matches += 1

        sess.commit()
        print(f"🔗  player_news linked: {inserted} total")
        print(f"    ├─ By player name in title: {player_name_matches}")
        print(f"    ├─ By club in title (no player name): {club_matches}")
        print(f"    └─ Ambiguous (name without club): {ambiguous_links}")


# ----------------------------- CLI --------------------------------

def load_player_history(engine: sa.Engine, csv_path: Path, if_exists: str = "append"):
    """
    Load historical player data into player_history table.
    Each row represents a player's stats for a specific season.
    """
    print(f"📊 Loading player history from {csv_path}...")
    
    df = pd.read_csv(csv_path, low_memory=False)
    
    # Fix column names
    if 'nationalit' in df.columns:
        df.rename(columns={'nationalit': 'nationality'}, inplace=True)
    
    # Column mapping for player_history table
    column_mapping = {
        'player': 'player',
        'player_uid': 'player_uid',
        'Season': 'season',
        'Team': 'team',
        'League': 'league',
        'Team_Logo': 'team_logo',
        'nationality': 'nationality',
        'position': 'position',
        'age': 'age',
        'games': 'games',
        'games_starts': 'games_starts',
        'minutes': 'minutes',
        'minutes_90s': 'minutes_90s',
        'goals': 'goals',
        'assists': 'assists',
        'xg': 'expected_goals',
        'xg_assist': 'expected_assists',
        'progressive_carries': 'progressive_carries',
        'progressive_passes': 'progressive_passes',
        'progressive_passes_received': 'progressive_passes_received',
        'goals_per90': 'goals_per90',
        'assists_per90': 'assists_per90',
        'goals_assists_per90': 'goals_assists_per90',
        'xg_per90': 'expected_goals_per90',
        'xg_assist_per90': 'expected_assists_per90',
        'passes_completed': 'passes_completed',
        'passes': 'passes',
        'passes_pct': 'passes_pct',
        'tackles': 'tackles',
        'tackles_won': 'tackles_won',
        'interceptions': 'interceptions',
        'blocks': 'blocks',
        'clearances': 'clearances',
    }
    
    # Keep only columns that exist
    available_cols = {k: v for k, v in column_mapping.items() if k in df.columns}
    df_prepared = df[list(available_cols.keys())].copy()
    df_prepared.rename(columns=available_cols, inplace=True)
    
    # Convert numeric columns
    numeric_cols = ['age', 'games', 'games_starts', 'minutes', 'minutes_90s', 'goals', 'assists',
                    'expected_goals', 'expected_assists', 'progressive_carries', 'progressive_passes',
                    'progressive_passes_received', 'goals_per90', 'assists_per90', 'goals_assists_per90',
                    'expected_goals_per90', 'expected_assists_per90', 'passes_completed', 'passes',
                    'passes_pct', 'tackles', 'tackles_won', 'interceptions', 'blocks', 'clearances']
    
    for col in numeric_cols:
        if col in df_prepared.columns:
            df_prepared[col] = pd.to_numeric(df_prepared[col], errors='coerce')
    
    # Remove rows with missing player or season
    df_prepared = df_prepared.dropna(subset=['player', 'season'])

    df_prepared["player"] = df_prepared["player"].apply(clean_name)
    
    print(f"Inserting {len(df_prepared)} historical records...")
    
    # Use if_exists parameter
    df_prepared.to_sql('player_history', engine, if_exists=if_exists, index=False, method='multi', chunksize=1000)
    
    print(f"✅ Player history loaded: {len(df_prepared)} records")


def load_ratings_from_csv(engine: sa.Engine, csv_path: Path, if_exists: str = "replace", verbose: bool = False):
    """
    Load player ratings from CSV file.
    """
    if not csv_path.exists():
        print(f"❌ Ratings CSV not found: {csv_path}")
        return False
    
    try:
        print(f"\n📊 Loading player ratings from {csv_path}...")
        
        # Read CSV
        df = pd.read_csv(csv_path)
        print(f"📊 Loaded {len(df)} ratings from CSV")
        
        if verbose:
            print(f"📋 Sample of ratings:")
            print(df[['player_name', 'player_uid', 'overall_rating', 'position', 'league']].head(5).to_string(index=False))
        
        # Map column names to match database schema
        column_mapping = {
            'player_id': 'player_id',
            'player_uid': 'player_uid', 
            'overall_rating': 'overall_rating',
            'league_base_rating': 'league_base_rating',
            'performance_rating': 'performance_rating',
            'att': 'att',
            'ply': 'ply',
            'def_rating': 'def_rating',
            'ctr': 'ctr',
            'phy': 'phy',
            'gkp': 'gkp',
            'season': 'season',
            'position': 'position',
            'minutes_played': 'minutes_played'
        }
        
        # Rename columns
        df = df.rename(columns=column_mapping)
        
        # Select only the columns we need
        db_columns = list(column_mapping.values())
        df_db = df[db_columns].copy()
        
        # Clean table if replace (manual TRUNCATE for better performance)
        if if_exists == "replace":
            with engine.begin() as conn:
                conn.execute(sa.text("TRUNCATE TABLE player_ratings RESTART IDENTITY CASCADE"))
            print("🗑️  player_ratings table cleaned")
        
        # Disable constraints for faster bulk insert
        with engine.begin() as conn:
            conn.execute(sa.text("ALTER TABLE player_ratings DISABLE TRIGGER ALL"))
            print("⚡ Constraints disabled for bulk insert")
        
        try:
            # Import to database (always append after manual TRUNCATE)
            df_db.to_sql(
                'player_ratings',
                engine,
                if_exists="append",
                index=False,
                method='multi',
                chunksize=1000
            )
        finally:
            # Re-enable constraints
            with engine.begin() as conn:
                conn.execute(sa.text("ALTER TABLE player_ratings ENABLE TRIGGER ALL"))
            print("🔒 Constraints re-enabled")
        
        print(f"✅ Player ratings loaded: {len(df_db)} records")
        
        # Verify import
        with engine.connect() as conn:
            result = conn.execute(sa.text("SELECT COUNT(*) FROM player_ratings"))
            count = result.fetchone()[0]
            print(f"📊 Total ratings in database: {count}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error loading ratings from CSV: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="Seed players & ingest news")
    parser.add_argument("--players-csv", type=Path, help="Path to players CSV", required=False)
    parser.add_argument("--history-csv", type=Path, help="Path to historical players CSV (non-aggregated)", required=False)
    parser.add_argument("--ratings-csv", type=Path, help="Path to player ratings CSV", required=False)
    parser.add_argument("--replace", action="store_true", help="TRUNCATE players before importing CSV")
    parser.add_argument("--replace-history", action="store_true", help="TRUNCATE player_history before importing CSV")
    parser.add_argument("--replace-ratings", action="store_true", help="TRUNCATE player_ratings before importing CSV")
    parser.add_argument("--ingest-news", action="store_true", help="Fetch & embed latest news")
    parser.add_argument("--calculate-ratings", action="store_true", help="Calculate FIFA-style ratings for all players (DEPRECATED: use --ratings-csv instead)")
    parser.add_argument("--ratings-season", type=str, help="Season for ratings calculation (default: all)")
    parser.add_argument("--echo-sql", action="store_true")
    parser.add_argument("--skip-players", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--refresh-embs",
        action="store_true",
        help="Re‑compute player embeddings even if they exist"
    )
    args = parser.parse_args()

    engine = get_engine(echo=args.echo_sql)
    create_tables(engine)

    if not args.skip_players and args.players_csv:
        if not args.skip_players and args.players_csv:
            load_players(engine, args.players_csv, if_exists="replace" if args.replace else "append")
            compute_and_store_player_vectors(engine, refresh=args.refresh_embs)

    if args.history_csv:
        load_player_history(engine, args.history_csv, if_exists="replace" if args.replace_history else "append")

    if args.ingest_news:
        ingest_news(engine, verbose=args.verbose)
        link_player_news(engine)

    # Load ratings from CSV (new approach)
    if args.ratings_csv:
        load_ratings_from_csv(
            engine=engine,
            csv_path=args.ratings_csv,
            if_exists="replace" if args.replace_ratings else "append",
            verbose=args.verbose
        )
    
    # Legacy: Calculate ratings (deprecated)
    elif args.calculate_ratings:
        print("⚠️  --calculate-ratings is deprecated. Use --ratings-csv instead.")
        calculate_ratings_wrapper(
            engine=engine,
            season=args.ratings_season,
            replace=args.replace_ratings,
            verbose=args.verbose
        )

    print("✅ All done")


if __name__ == "__main__":
    main()

