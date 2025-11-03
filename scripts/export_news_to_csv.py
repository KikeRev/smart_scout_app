#!/usr/bin/env python3
"""
Export football_news table to CSV format for backup/restore.

This script exports all news articles from the football_news table,
including their linked players, to a CSV file that can be used with
--news-csv parameter in seed_and_ingest.py.

Usage:
    python scripts/export_news_to_csv.py --output data/news_backup.csv
    python scripts/export_news_to_csv.py --output data/news_backup.csv --verbose
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Add parent directory to path to import from apps
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from sqlalchemy import orm

from apps.ingestion.seed_and_ingest import (
    get_engine,
    FootballNews,
    Player,
    player_news,
)

def export_news_to_csv(output_path: Path, verbose: bool = False):
    """
    Export all news articles from football_news table to CSV.
    
    Args:
        output_path: Path where CSV file will be saved
        verbose: Print progress information
    """
    engine = get_engine(echo=False)
    
    if verbose:
        print(f"📊 Connecting to database...", flush=True)
    
    with orm.Session(engine) as session:
        # Get all news articles
        news_query = session.query(FootballNews).order_by(FootballNews.published_at.desc())
        news_items = news_query.all()
        
        if not news_items:
            print("⚠️  No news articles found in database")
            return False
        
        if verbose:
            print(f"📰 Found {len(news_items)} news articles", flush=True)
        
        # Get player_news relationships
        # Build mapping: news_id -> list of player_ids and player_names
        player_news_query = session.query(
            player_news.c.news_id,
            player_news.c.player_id,
            Player.full_name
        ).join(
            Player, player_news.c.player_id == Player.id
        )
        
        player_news_rows = player_news_query.all()
        
        # Build dictionaries
        news_to_player_ids = {}
        news_to_player_names = {}
        
        for news_id, player_id, player_name in player_news_rows:
            if news_id not in news_to_player_ids:
                news_to_player_ids[news_id] = []
                news_to_player_names[news_id] = []
            news_to_player_ids[news_id].append(str(player_id))
            news_to_player_names[news_id].append(player_name)
        
        # Build CSV rows
        rows = []
        for news in news_items:
            # Format published_at as ISO string with timezone
            published_at_str = news.published_at.isoformat() if news.published_at else ""
            
            # Get player associations
            player_ids_str = ",".join(news_to_player_ids.get(news.id, []))
            player_names_str = ",".join(news_to_player_names.get(news.id, []))
            
            row = {
                "url": news.url or "",
                "title": news.title or "",
                "published_at": published_at_str,
                "article_text": news.article_text or "",
                "summary": news.summary or "",
                "source_id": news.source_id or "",
                "player_ids": player_ids_str,
                "player_names": player_names_str,
            }
            rows.append(row)
        
        # Create DataFrame
        df = pd.DataFrame(rows)
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write to CSV
        df.to_csv(output_path, index=False, encoding='utf-8')
        
        print(f"✅ Exported {len(rows)} news articles to {output_path}", flush=True)
        
        if verbose:
            # Show summary
            total_linked = sum(1 for r in rows if r["player_ids"] or r["player_names"])
            print(f"   - Articles with player links: {total_linked}", flush=True)
            print(f"   - Total player links: {sum(len(news_to_player_ids.get(n.id, [])) for n in news_items)}", flush=True)
        
        return True


def main():
    parser = argparse.ArgumentParser(
        description="Export football_news table to CSV for backup/restore"
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output CSV file path (e.g., data/news_backup.csv)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed progress information"
    )
    
    args = parser.parse_args()
    
    try:
        success = export_news_to_csv(args.output, verbose=args.verbose)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Error exporting news: {e}", flush=True)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

