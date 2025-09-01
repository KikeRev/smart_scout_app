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

DIM = 42  # Dimensión del vector de características (ajustar según el modelo)

# fuera de las funciones, para que se cargue una vez
_SUMMARIZER = pipeline(
    task="summarization",
    model="facebook/bart-large-cnn",   # o t5-small / pegasus
    device=0 if torch.cuda.is_available() else -1,
)
# tokenizer para contar tokens (opcional, si quieres trocear artículos muy largos)
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

class Player(Base):
    __tablename__ = "players"

    id = sa.Column(sa.Integer, primary_key=True)
    full_name = sa.Column(sa.Text, nullable=False, index=True)
    age = sa.Column(sa.Integer)
    nationality = sa.Column(sa.String(64))
    position = sa.Column(sa.String(32))
    club = sa.Column(sa.String(128))
    team_logo = sa.Column(sa.Text)
    league = sa.Column(sa.String(64))

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

    # optional: pgvector column for aggregated numerical vector
    feature_vector = sa.Column(Vector(DIM))


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
    article_meta = sa.Column(sa.JSON, nullable=True)  # <— en vez de `metadata`


player_news = sa.Table(
    "player_news",
    Base.metadata,
    sa.Column("player_id", sa.Integer, sa.ForeignKey("players.id", ondelete="CASCADE")),
    sa.Column("news_id",   sa.Integer, sa.ForeignKey("football_news.id", ondelete="CASCADE")),
    sa.PrimaryKeyConstraint("player_id", "news_id"),
)

# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def get_engine(echo: bool = False) -> sa.Engine:
    return sa.create_engine(DATABASE_URL, echo=echo, future=True)


def create_tables(engine):
    # Asegurarse de que existe la extensión vector
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector;")
    Base.metadata.create_all(engine)

# --------------------------- CSV ingest -------------------------

CSV_COLUMN_MAP = {
    "player": "full_name",
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
}

REQUIRED_COLUMNS = set(CSV_COLUMN_MAP.keys())
NUMERIC_RE = re.compile(r"[^0-9\-.]+")


def _to_float(x):
    if pd.isna(x) or x == "":
        return 0.0
    if isinstance(x, str):
        x = NUMERIC_RE.sub("", x)
    try:
        return float(x)
    except ValueError:
        return 0.0


def _to_int(x):
    return int(_to_float(x))

def clean_name(name: str) -> str:
    """Normaliza tildes, elimina caracteres raros y colapsa espacios."""
    if pd.isna(name):
        return ""
    # 1) Normaliza a NFKD y elimina diacríticos
    name_ascii = (
        unicodedata.normalize("NFKD", name)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    # 2) Colapsa espacios y quita espacios iniciales/finales
    name_ascii = _WS_RE.sub(" ", name_ascii).strip()
    # 3) Convierte a Title Case (opcional)
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

    float_cols = list(set(df.columns) - set(int_cols) - {"full_name", "nationality", "position", "club", "team_logo", "league"})
    for col in float_cols:
        df[col] = df[col].apply(_to_float)

    if if_exists == "replace":
        with engine.begin() as conn:
            conn.execute(sa.text("""
                TRUNCATE TABLE player_news, players
                RESTART IDENTITY CASCADE
            """))

    df.to_sql("players", con=engine, if_exists="append", index=False, method="multi")
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
    Resume un texto con ajuste automático de longitudes y
    fallback si el modelo falla.
    """
    try:
        # tokens reales del chunk
        n_tokens = len(_TOKENIZER(text).input_ids)

        # Queremos algo más corto que el original pero > min_length
        max_len = max(20, int(n_tokens * 0.8))    # 80 % del tamaño
        max_len = min(max_len, 128)               # nunca > 128
        min_len = max(10, int(max_len * 0.25))    # 25 % del max_len

        return _SUMMARIZER(
            text,
            max_length=max_len,
            min_length=min_len,
            do_sample=False,
        )[0]["summary_text"]

    except Exception:
        # fallback: primeros 400 caracteres
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

    # Split by tokens ≤1024 para BART
    tokens = _TOKENIZER(text).input_ids
    chunks = []
    while tokens:
        chunk_ids, tokens = tokens[:1024], tokens[1024:]
        chunks.append(_TOKENIZER.decode(chunk_ids, skip_special_tokens=True))

    # Resumen jerárquico
    summaries = [safe_summarize(c) for c in chunks]
    full_summary = safe_summarize(" ".join(summaries))
    return text, full_summary


def embed_texts(texts: list[str]) -> list[list[float]]:
    # Filtra nulos y vacíos
    valid_texts = [t for t in texts if t]
    if not valid_texts:
        return []

    return embedder.encode(
        valid_texts,
        batch_size=32,
        show_progress_bar=True,
        convert_to_numpy=True,
    ).tolist()


def ingest_news(engine: sa.Engine):
    items = sorted(fetch_rss_items(), key=lambda x: x["published_at"], reverse=True)
    print(f"Fetched {len(items)} RSS items → processing …")

    texts:      list[str]  = []   # artículo completo
    summaries:  list[str]  = []   # resumen
    metas:      list[dict] = []   # metadatos URL, título, fecha…

    for meta in tqdm(items, desc="Parsing", unit="article"):
        try:
            # ── parsea el artículo y resume ───────────────────────────────
            parsed = parse_article(meta["url"])

            # ── descarta los que no devuelven nada ────────────────────────
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

    # Usa RESÚMENES (o texts) para la embedding; los dos tienen la misma len
    embeddings = embed_texts(texts)

    with orm.Session(engine) as session:
        inserted = 0
        for text, summary, emb, meta in tqdm(
            zip(texts, summaries, embeddings, metas),
            total=len(metas),
            desc="DB upsert",
            unit="row"
        ):
            if session.query(FootballNews).filter_by(url=meta["url"]).first():
                continue  # duplicado

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

PLAYER_DIM = 43                 # 42 stats + minutes_90s (🗒️ ajusta si cambias)
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
    """lower‑case, strip diacritics & collapse spaces – for matching."""
    if not text:
        return ""
    text = unidecode.unidecode(
        unicodedata.normalize("NFKD", text)
    ).lower()
    return _WS.sub(" ", text).strip()

def ensure_link_index(engine: sa.Engine):
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS player_news (
              player_id  INTEGER NOT NULL REFERENCES players(id)  ON DELETE CASCADE,
              news_id    INTEGER NOT NULL REFERENCES football_news(id) ON DELETE CASCADE,
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

def link_player_news(engine: sa.Engine, only_new: bool = True) -> None:
    """
    Populate `player_news` by regex‑matching player names inside each article.
    If `only_new` is True we link only news entries not yet in the bridge table.
    """
    ensure_link_index(engine)

    with orm.Session(engine) as sess:

        # 1️⃣ Dict {normalized_name: player_id}
        name_to_id = {
            _norm(name): pid
            for pid, name in sess.query(Player.id, Player.full_name)
        }

        if not name_to_id:
            print("⚠️  No players to link – skipping player_news linking.")
            return

        # Build single regex (word boundary) e.g.  \b(mbappe|vinicius jr|...) \b
        pattern = r"\b(" + "|".join(re.escape(n) for n in name_to_id) + r")\b"
        name_re = re.compile(pattern, re.I)

        # 2️⃣ Rows to scan
        q = sess.query(FootballNews.id, FootballNews.article_text)
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
        for news_id, article in tqdm(rows, desc="Linking news↔players", unit="article"):
            matches = { _norm(m.group(0)) for m in name_re.finditer(article or "") }

            for n in matches:
                pid = name_to_id.get(n)
                if not pid:
                    continue

                stmt = pg_insert(player_news).values(player_id=pid, news_id=news_id)
                stmt = stmt.on_conflict_do_nothing()
                sess.execute(stmt)
                inserted += 1

        sess.commit()
        print(f"🔗  player_news linked: {inserted}")


# ----------------------------- CLI --------------------------------

def main():
    parser = argparse.ArgumentParser(description="Seed players & ingest news")
    parser.add_argument("--players-csv", type=Path, help="Path to players CSV", required=False)
    parser.add_argument("--replace", action="store_true", help="TRUNCATE players before importing CSV")
    parser.add_argument("--ingest-news", action="store_true", help="Fetch & embed latest news")
    parser.add_argument("--echo-sql", action="store_true")
    parser.add_argument("--skip-players", action="store_true")
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

    if args.ingest_news:
        ingest_news(engine)
        link_player_news(engine)

    print("✅ All done")


if __name__ == "__main__":
    main()

