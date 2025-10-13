#!/usr/bin/env python3
"""
🎯 Mass Rating Calculation - Generates ratings for all players

This script calculates FIFA-style ratings for all players in the database
and stores them in the player_ratings table.

Usage:
    python scripts/calculate_all_ratings.py [--season 2024-25] [--replace]
    
Options:
    --season: Specific season to calculate (default: all)
    --replace: Delete existing ratings before calculating
    --batch-size: Batch size for commits (default: 100)
    --verbose: Show detailed progress
"""

import os
import sys
import argparse
from pathlib import Path

# Add root directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlalchemy as sa
from sqlalchemy import text, orm
from tqdm import tqdm

from apps.ingestion.seed_and_ingest import Player, PlayerRating, get_engine
from apps.rating_system.calculator import calculate_player_rating

# ============================================================================
# FUNCTIONS
# ============================================================================

def calculate_all_ratings(
    engine: sa.Engine,
    season: str = None,
    replace: bool = False,
    batch_size: int = 100,
    verbose: bool = False
):
    """
    Calculates ratings for all players and saves them to player_ratings.
    
    Args:
        engine: SQLAlchemy engine
        season: Specific season (None = all)
        replace: If True, delete existing ratings first
        batch_size: Number of ratings to insert per batch
        verbose: Show detailed progress
    """
    with orm.Session(engine) as session:
        # If replace=True, clean table
        if replace:
            if season:
                deleted = session.execute(
                    text("DELETE FROM player_ratings WHERE season = :season"),
                    {"season": season}
                ).rowcount
                session.commit()
                print(f"🗑️  Deleted {deleted} ratings from season {season}")
            else:
                session.execute(text("TRUNCATE TABLE player_ratings RESTART IDENTITY CASCADE"))
                session.commit()
                print("🗑️  player_ratings table cleaned")
        
        # Get players to process
        query = session.query(Player).filter(Player.minutes > 0)
        
        if season:
            query = query.filter(Player.season == season)
        
        players = query.all()
        
        if not players:
            print("⚠️  No players found to process")
            return
        
        print(f"📊 Processing {len(players)} players...")
        
        # Process players
        ratings_to_insert = []
        processed = 0
        skipped = 0
        errors = 0
        
        iterator = tqdm(players, desc="Calculating ratings", unit="player") if verbose else players
        
        for player in iterator:
            try:
                # Prepare player stats
                player_stats = {
                    'goals_per90': player.goals_per90 or 0.0,
                    'assists_per90': player.assists_per90 or 0.0,
                    'expected_goals_per90': player.expected_goals_per90 or 0.0,
                    'expected_assists_per90': player.expected_assists_per90 or 0.0,
                    'progressive_carries': player.progressive_carries or 0,
                    'progressive_passes': player.progressive_passes or 0,
                    'progressive_passes_received': player.progressive_passes_received or 0,
                    'passes_completed': player.passes_completed or 0,
                    'passes_pct': player.passes_pct or 0.0,
                    'passes_progressive_distance': player.passes_progressive_distance or 0,
                    'tackles': player.tackles or 0,
                    'interceptions': player.interceptions or 0,
                    'clearances': player.clearances or 0,
                    'blocks': player.blocks or 0,
                    # GK stats
                    'gk_goals_against': player.gk_goals_against or 0,
                    'gk_psxg': player.gk_psxg or 0.0,
                    'gk_psnpxg_per_shot': player.gk_psnpxg_per_shot_on_target_against or 0.0,
                    'minutes_90s': player.minutes_90s or 0.0,
                }
                
                # Calculate rating
                rating_data = calculate_player_rating(
                    engine=engine,
                    player_id=player.id,
                    player_name=player.full_name,
                    league=player.league or 'default',
                    position=player.position or '',
                    minutes=player.minutes or 0,
                    season=player.season or 'unknown',
                    player_stats=player_stats
                )
                
                if rating_data is None:
                    skipped += 1
                    if verbose:
                        print(f"⏭️  Skipped: {player.full_name} (no league data)")
                    continue
                
                # Create PlayerRating object
                rating = PlayerRating(
                    player_id=rating_data['player_id'],
                    overall_rating=rating_data['overall_rating'],
                    league_base_rating=rating_data['league_base_rating'],
                    performance_rating=rating_data['performance_rating'],
                    att=rating_data['att'],
                    ply=rating_data['ply'],
                    def_rating=rating_data['def_rating'],
                    ctr=rating_data['ctr'],
                    phy=rating_data['phy'],
                    gkp=rating_data['gkp'],
                    season=rating_data['season'],
                    position=rating_data['position'],
                    minutes_played=rating_data['minutes_played'],
                )
                
                ratings_to_insert.append(rating)
                processed += 1
                
                # Commit in batches
                if len(ratings_to_insert) >= batch_size:
                    session.bulk_save_objects(ratings_to_insert)
                    session.commit()
                    ratings_to_insert = []
                    
            except Exception as e:
                errors += 1
                if verbose:
                    print(f"❌ Error calculating rating for {player.full_name}: {e}")
                continue
        
        # Final commit
        if ratings_to_insert:
            session.bulk_save_objects(ratings_to_insert)
            session.commit()
        
        print(f"\n✅ Calculation completed:")
        print(f"   - Processed: {processed}")
        print(f"   - Skipped: {skipped}")
        print(f"   - Errors: {errors}")
        print(f"   - Total in DB: {session.query(PlayerRating).count()}")


def main():
    parser = argparse.ArgumentParser(
        description="Calculate FIFA-style ratings for all players"
    )
    parser.add_argument(
        "--season",
        type=str,
        help="Specific season (e.g., 2024-25). If not specified, processes all seasons."
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete existing ratings before calculating"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for commits (default: 100)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed progress"
    )
    parser.add_argument(
        "--echo-sql",
        action="store_true",
        help="Show SQL queries"
    )
    
    args = parser.parse_args()
    
    # Create engine
    engine = get_engine(echo=args.echo_sql)
    
    # Execute calculation
    calculate_all_ratings(
        engine=engine,
        season=args.season,
        replace=args.replace,
        batch_size=args.batch_size,
        verbose=args.verbose
    )


if __name__ == "__main__":
    main()
