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
                # Calculate rating using the updated function
                from scripts.calculate_player_rating import calculate_rating
                rating_data = calculate_rating(
                    player_name=player.full_name,
                    player_uid=player.player_uid
                )
                
                if rating_data is None:
                    skipped += 1
                    if verbose:
                        print(f"⏭️  Skipped: {player.full_name} (no league data)")
                    continue
                
                # Create PlayerRating object
                rating = PlayerRating(
                    player_id=rating_data['player_id'],
                    player_uid=rating_data['player_uid'],
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
                    try:
                        session.bulk_save_objects(ratings_to_insert)
                        session.commit()
                        ratings_to_insert = []
                    except Exception as e:
                        session.rollback()
                        if verbose:
                            print(f"⚠️  Batch error, inserting individually: {e}")
                        # Insert individually to handle duplicates
                        for rating in ratings_to_insert:
                            try:
                                session.merge(rating)  # Use merge for upsert behavior
                                session.commit()
                            except Exception as individual_error:
                                session.rollback()
                                if verbose:
                                    print(f"❌ Error with individual rating: {individual_error}")
                        ratings_to_insert = []
                    
            except Exception as e:
                errors += 1
                if verbose:
                    print(f"❌ Error calculating rating for {player.full_name}: {e}")
                continue
        
        # Final commit
        if ratings_to_insert:
            try:
                session.bulk_save_objects(ratings_to_insert)
                session.commit()
            except Exception as e:
                session.rollback()
                if verbose:
                    print(f"⚠️  Final batch error, inserting individually: {e}")
                # Insert individually to handle duplicates
                for rating in ratings_to_insert:
                    try:
                        session.merge(rating)  # Use merge for upsert behavior
                        session.commit()
                    except Exception as individual_error:
                        session.rollback()
                        if verbose:
                            print(f"❌ Error with final individual rating: {individual_error}")
        
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
