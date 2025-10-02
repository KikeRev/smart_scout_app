"""
Aggregation v2 pipeline
- Build metadata (non-numeric) by taking the latest season per player.
- Build numeric table with >=300 minutes filter and weighted means by recency.
- Join on player name to produce one row per player with Team/League/Logo and metrics.

Inputs (under notebooks/scrapper/data/):
  - historical_players_raw.csv          (long form, multiple seasons)
  - current_season_players_normalized.csv (Season == "2024-25")

Output:
  - historical_players_final_v2.csv
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from pathlib import Path
import unicodedata
import re

DATA_DIR = Path("notebooks/scrapper/data")
RAW_FILE = DATA_DIR / "historical_players_raw.csv"
CUR_FILE = DATA_DIR / "current_season_players_normalized.csv"
OUT_FILE = DATA_DIR / "historical_players_final_v2.csv"

_WS_RE = re.compile(r"\s+")

def clean_name(name: str) -> str:
    if pd.isna(name) or name == "":
        return ""
    try:
        name = str(name)
    except Exception:
        return ""
    ascii_ = (
        unicodedata.normalize("NFKD", name)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    ascii_ = _WS_RE.sub(" ", ascii_).strip()
    return ascii_.title()

def load_data() -> pd.DataFrame:
    if not RAW_FILE.exists():
        raise FileNotFoundError(f"Missing {RAW_FILE}")
    df = pd.read_csv(RAW_FILE)
    # Append current season if available
    if CUR_FILE.exists():
        cur = pd.read_csv(CUR_FILE)
        df = pd.concat([df, cur], ignore_index=True)
    return df

def coerce_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

def parse_season_weight(season: str) -> float:
    """Higher weight for more recent seasons. Simple linear by start year."""
    if pd.isna(season):
        return 0.0
    s = str(season)
    try:
        start = int(s.split("-")[0])
    except Exception:
        return 0.0
    # Map to weight ~ (start_year - 2018), floor at 0
    base = max(0, start - 2018)
    return 1.0 + base * 0.25

def build_metadata(df: pd.DataFrame) -> pd.DataFrame:
    # Clean identifiers and sort by season to take latest
    df = df.copy()
    for col in ["player", "Team", "League", "Team_Logo"]:
        if col in df.columns:
            df[col] = df[col].apply(clean_name)
    # Sort by player then by season start year
    def season_key(s):
        try:
            return int(str(s).split("-")[0])
        except Exception:
            return -1
    df["_season_key"] = df["Season"].apply(season_key) if "Season" in df.columns else -1
    df = df.sort_values(["player", "_season_key"], ascending=[True, True])
    # Latest season per player
    last = df.groupby("player").tail(1)
    meta = last[[c for c in ["player", "Team", "League", "Team_Logo", "Season"] if c in last.columns]].copy()
    # player_status: active if Season == 2024-25 else inactive
    if "Season" in meta.columns:
        meta["player_status"] = np.where(meta["Season"].astype(str) == "2024-25", "active", "inactive")
    else:
        meta["player_status"] = "inactive"
    return meta.drop(columns=["Season"], errors="ignore")

NUMERIC_COLS = [
    "minutes", "minutes_90s",
    "goals", "assists",
    "xg", "xg_assist", "npxg_xg_assist",
    "progressive_carries", "progressive_passes", "progressive_passes_received",
    "goals_per90", "assists_per90", "goals_assists_per90",
    "xg_per90", "xg_assist_per90", "xg_xg_assist_per90",
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

def build_numeric(df: pd.DataFrame) -> pd.DataFrame:
    use = df.copy()
    use["player"] = use["player"].apply(clean_name)
    coerce_numeric(use, [c for c in NUMERIC_COLS if c in use.columns] + ["minutes"])
    # Filter minutes >= 300
    if "minutes" in use.columns:
        use = use[use["minutes"] >= 300]
    # Compute weights per row
    use["_w"] = use["Season"].apply(parse_season_weight) if "Season" in use.columns else 1.0
    # Weighted mean per player
    aggs = {}
    for c in NUMERIC_COLS:
        if c in use.columns:
            aggs[c] = lambda s, c=c: np.average(s, weights=use.loc[s.index, "_w"]) if s.notna().any() else np.nan
    grouped = use.groupby("player").agg(aggs).reset_index()
    return grouped

def align_to_all_players_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Rename to match all_players_cleaned.csv headers as much as possible."""
    mapping = {
        "player": "player",
        "Team": "Team",
        "League": "League",
        "Team_Logo": "Team_Logo",
        # rename expected fields to original names used by seed
        "xg": "xg",
        "xg_assist": "xg_assist",
        "npxg_xg_assist": "npxg_xg_assist",
        "xg_per90": "xg_per90",
        "xg_assist_per90": "xg_assist_per90",
        "xg_xg_assist_per90": "xg_xg_assist_per90",
    }
    return df.rename(columns=mapping)

def main():
    print("Loading data…")
    df = load_data()
    if "player" not in df.columns:
        raise RuntimeError("Input data must contain 'player' column")

    print("Building metadata (latest season non-numerics)…")
    meta = build_metadata(df)

    print("Building numeric (>=300 min, weighted means)…")
    num = build_numeric(df)

    print("Joining…")
    final = num.merge(meta, on="player", how="left")
    final = align_to_all_players_schema(final)

    # Drop duplicates, ensure one row per player
    final = final.drop_duplicates(subset=["player"], keep="first")

    # Basic sanity checks
    missing_team = final["Team"].isna().sum() if "Team" in final.columns else len(final)
    print(f"Rows: {len(final)} | Missing Team: {missing_team}")

    print(f"Saving → {OUT_FILE}")
    final.to_csv(OUT_FILE, index=False)
    print("Done.")

if __name__ == "__main__":
    main()


