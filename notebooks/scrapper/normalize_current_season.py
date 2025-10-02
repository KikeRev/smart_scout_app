#!/usr/bin/env python3
"""
normalize_current_season.py

Normalize current season file (all_players_cleaned.csv) to match the historical schema.
- Adds Season column (default: 2024-25)
- Renames nationality -> nationalit (to align with historical output)
- Ensures Team, League, Team_Logo exist
- Drops duplicate suffixed columns (e.g., goals.1) preferring base columns
- Cleans numeric fields (remove commas)
- Outputs data/current_season_players_normalized.csv

Usage:
    python normalize_current_season.py
"""
import os
import re
import pandas as pd
from typing import List

CURRENT_SEASON = "2024-25"
INPUT_PATH = "data/all_players_cleaned.csv"
OUTPUT_PATH = "data/current_season_players_normalized.csv"

# Columns that should exist in normalized output
REQUIRED_META_COLS: List[str] = [
    "player", "nationalit", "position", "age", "Team", "League", "Team_Logo", "Season"
]

# Prefer base columns when duplicates like `col` and `col.1` exist
DUPLICATE_SUFFIX_PATTERN = re.compile(r"^(?P<base>.+)\.\d+$")

# Columns that commonly contain thousands separators
COMMON_NUMERIC_COLS_CONTAINING_COMMAS = {
    "minutes", "passes_total_distance", "passes_progressive_distance"
}


def load_current_csv(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Input file not found: {path}")
    return pd.read_csv(path)


def drop_duplicate_suffixed_columns(df: pd.DataFrame) -> pd.DataFrame:
    # Build a map from base -> list of duplicates including base
    base_to_cols = {}
    for col in df.columns:
        m = DUPLICATE_SUFFIX_PATTERN.match(col)
        base = m.group("base") if m else col
        base_to_cols.setdefault(base, []).append(col)

    cols_to_keep = []
    for base, cols in base_to_cols.items():
        # Prefer exact base if present; otherwise keep the lexicographically first
        if base in cols:
            cols_to_keep.append(base)
        else:
            cols_to_keep.append(sorted(cols)[0])

    # De-duplicate keep list preserving original order
    seen = set()
    ordered_keep = []
    for col in df.columns:
        m = DUPLICATE_SUFFIX_PATTERN.match(col)
        base = m.group("base") if m else col
        preferred = base if base in cols_to_keep else (sorted(base_to_cols[base])[0])
        if preferred not in seen:
            seen.add(preferred)
            ordered_keep.append(preferred)

    # Recreate df with preferred columns
    new_df = pd.DataFrame()
    for col in ordered_keep:
        if col in df.columns:
            new_df[col] = df[col]
        else:
            # If preferred base not present, copy from first available duplicate
            candidates = base_to_cols[col] if col in base_to_cols else []
            for c in candidates:
                if c in df.columns:
                    new_df[col] = df[c]
                    break
            if col not in new_df.columns:
                # Create empty column if still missing
                new_df[col] = pd.NA
    return new_df


def rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {"nationality": "nationalit"}
    return df.rename(columns=rename_map)


def ensure_meta_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Season
    if "Season" not in df.columns:
        df["Season"] = CURRENT_SEASON
    else:
        df["Season"] = df["Season"].fillna(CURRENT_SEASON).replace("", CURRENT_SEASON)

    # Ensure Team/League/Team_Logo exist
    for col in ["Team", "League", "Team_Logo"]:
        if col not in df.columns:
            df[col] = pd.NA

    # Ensure nationalit exists after rename
    if "nationalit" not in df.columns and "nationality" in df.columns:
        df["nationalit"] = df["nationality"]

    return df


def clean_numeric(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in df.columns:
        if col in COMMON_NUMERIC_COLS_CONTAINING_COMMAS or col.endswith(("_distance", "_per90")) or col in {"minutes"}:
            if df[col].dtype == object:
                df[col] = df[col].str.replace(",", "", regex=False)
        # Try numeric coercion for obvious numeric columns
        if col not in {"player", "nationalit", "position", "Team", "League", "Team_Logo", "Season"}:
            df[col] = pd.to_numeric(df[col], errors="ignore")
    return df


def reorder_columns(df: pd.DataFrame) -> pd.DataFrame:
    # Place meta columns first if available, then the rest
    meta = [c for c in REQUIRED_META_COLS if c in df.columns]
    rest = [c for c in df.columns if c not in meta]
    return df[meta + rest]


def main() -> None:
    print("=== NORMALIZE CURRENT SEASON ===")
    print(f"Reading: {INPUT_PATH}")
    df = load_current_csv(INPUT_PATH)
    print(f"Loaded {len(df)} rows, {len(df.columns)} columns")

    print("Dropping duplicate suffixed columns (e.g., .1, .2)...")
    df = drop_duplicate_suffixed_columns(df)

    print("Renaming columns...")
    df = rename_columns(df)

    print("Ensuring metadata columns...")
    df = ensure_meta_columns(df)

    print("Cleaning numeric fields...")
    df = clean_numeric(df)

    print("Reordering columns...")
    df = reorder_columns(df)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"Written: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
