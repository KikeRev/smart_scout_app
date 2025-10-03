#!/usr/bin/env python3
"""
Process historical data by league and season, then aggregate by player.
This script generates separate CSV files for each league/season combination
and then creates an aggregated dataset.
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict
import os
import re
import unicodedata

# Configuration
_WS_RE = re.compile(r"\s+")

def clean_name(name: str) -> str:
    """Normalize tildes, remove rare characters and collapse spaces."""
    if pd.isna(name) or name == "":
        return ""
    # 1) Normalize to NFKD and remove diacritics
    name_ascii = (
        unicodedata.normalize("NFKD", str(name))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    # 2) Collapse spaces and remove initial/final spaces
    name_ascii = _WS_RE.sub(" ", name_ascii).strip()
    # 3) Convert to Title Case (optional)
    return name_ascii.title()

def clean_team_name(team: str) -> str:
    """Clean team names by removing common suffixes and normalizing."""
    if pd.isna(team) or team == "":
        return ""
    
    # Remove common suffixes
    team = str(team)
    suffixes_to_remove = [
        " FC", " CF", " AFC", " United", " City", " Town", " Rovers", " Wanderers",
        " Athletic", " Club", " SC", " AC", " AS", " SS", " US", " FC Barcelona",
        " Real Madrid", " Atletico Madrid", " Atletico", " Real", " Barcelona"
    ]
    
    for suffix in suffixes_to_remove:
        if team.endswith(suffix):
            team = team[:-len(suffix)]
    
    # Normalize and clean
    team = clean_name(team)
    return team

WEIGHTED_AVERAGE_COLUMNS = [
    'goals', 'assists', 'goals_assists', 'goals_pens', 'pens_made', 'pens_att',
    'cards_yellow', 'cards_red', 'xg', 'npxg', 'xg_assist', 'npxg_xg_assist',
    'progressive_carries', 'progressive_passes', 'progressive_passes_received',
    'goals_per90', 'assists_per90', 'goals_assists_per90', 'goals_pens_per90',
    'goals_assists_pens_per90', 'xg_per90', 'xg_assist_per90', 'xg_xg_assist_per90',
    'npxg_per90', 'npxg_xg_assist_per90', 'gk_goals_against', 'gk_pens_allowed',
    'gk_free_kick_goals_against', 'gk_corner_kick_goals_against', 'gk_own_goals_against',
    'gk_psxg', 'gk_psnpxg_per_shot_on_target_against', 'gk_psxg_net', 'gk_psxg_net_per90',
    'gk_passes_completed_launched', 'gk_passes_launched', 'gk_passes_pct_launched',
    'gk_passes', 'gk_passes_throws', 'gk_pct_passes_launched', 'gk_passes_length_avg',
    'gk_goal_kicks', 'gk_pct_goal_kicks_launched', 'gk_goal_kick_length_avg',
    'gk_crosses', 'gk_crosses_stopped', 'gk_crosses_stopped_pct',
    'gk_def_actions_outside_pen_area', 'gk_def_actions_outside_pen_area_per90',
    'gk_avg_distance_def_actions', 'shots', 'shots_on_target', 'shots_on_target_pct',
    'shots_per90', 'shots_on_target_per90', 'goals_per_shot', 'goals_per_shot_on_target',
    'average_shot_distance', 'shots_free_kicks', 'npxg_per_shot', 'xg_net', 'npxg_net',
    'passes_completed', 'passes', 'passes_pct', 'passes_total_distance',
    'passes_progressive_distance', 'passes_completed_short', 'passes_short',
    'passes_pct_short', 'passes_completed_medium', 'passes_medium', 'passes_pct_medium',
    'passes_completed_long', 'passes_long', 'passes_pct_long', 'xg_assist', 'pass_xa',
    'xg_assist_net', 'assisted_shots', 'passes_into_final_third', 'passes_into_penalty_area',
    'crosses_into_penalty_area', 'progressive_passes', 'passes_live', 'passes_dead',
    'passes_free_kicks', 'through_balls', 'passes_switches', 'crosses', 'throw_ins',
    'corner_kicks', 'corner_kicks_in', 'corner_kicks_out', 'corner_kicks_straight',
    'passes_completed', 'passes_offsides', 'passes_blocked', 'sca', 'sca_per90',
    'sca_passes_live', 'sca_passes_dead', 'sca_take_ons', 'sca_shots', 'sca_fouled',
    'sca_defense', 'gca', 'gca_per90', 'gca_passes_live', 'gca_passes_dead',
    'gca_take_ons', 'gca_shots', 'gca_fouled', 'gca_defense', 'tackles', 'tackles_won',
    'tackles_def_3rd', 'tackles_mid_3rd', 'tackles_att_3rd', 'challenge_tackles',
    'challenges', 'challenge_tackles_pct', 'challenges_lost', 'blocks', 'blocked_shots',
    'blocked_passes', 'interceptions', 'tackles_interceptions', 'clearances', 'errors',
    'touches', 'touches_def_pen_area', 'touches_def_3rd', 'touches_mid_3rd',
    'touches_att_3rd', 'touches_att_pen_area', 'touches_live_ball', 'take_ons',
    'take_ons_won', 'take_ons_won_pct', 'take_ons_tackled', 'take_ons_tackled_pct',
    'carries', 'carries_distance', 'carries_progressive_distance', 'progressive_carries',
    'carries_into_final_third', 'carries_into_penalty_area', 'miscontrols',
    'dispossessed', 'passes_received', 'progressive_passes_received', 'minutes_per_game',
    'minutes_pct', 'minutes_per_start', 'minutes_per_sub', 'unused_subs',
    'points_per_game', 'on_goals_for', 'on_goals_against', 'plus_minus',
    'plus_minus_per90', 'plus_minus_wow', 'on_xg_for', 'on_xg_against',
    'xg_plus_minus', 'xg_plus_minus_per90', 'xg_plus_minus_wow'
]

MOST_RECENT_COLUMNS = [
    'player', 'nationalit', 'position', 'Team', 'League', 'Team_Logo'
]

SUM_COLUMNS = [
    'games', 'games_starts', 'minutes', 'minutes_90s', 'matches'
]

def clean_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and convert numeric columns"""
    for col in df.columns:
        if col not in MOST_RECENT_COLUMNS and col != 'Season':
            # Convert to numeric, replacing commas and other non-numeric characters
            df[col] = df[col].astype(str).str.replace(',', '').str.replace('+', '').str.replace('-', '0')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df

def get_season_weight(season: str) -> float:
    """Get weight for season (more recent = higher weight)"""
    try:
        year = int(season.split('-')[0])
        current_year = datetime.now().year
        return min(1.0, max(0.1, (year - 2020) / (current_year - 2020)))
    except:
        return 0.5

def calculate_weighted_average(data: pd.Series, weights: pd.Series) -> float:
    """Calculate weighted average safely"""
    if weights.sum() == 0:
        return data.mean() if len(data) > 0 else 0
    return (data * weights).sum() / weights.sum()

def determine_player_status(player_data: pd.DataFrame) -> str:
    """Determine if player is active, inactive, or retired based on last season played"""
    current_year = datetime.now().year
    
    # Get the most recent season year
    last_season = player_data['Season'].iloc[-1]
    last_year = int(last_season.split('-')[0])
    
    # More precise status determination
    if last_year >= current_year:
        # Played in current year or future (shouldn't happen but just in case)
        return 'active'
    elif last_year == current_year - 1:
        # Played last season - likely still active
        return 'active'
    elif last_year == current_year - 2:
        # Missed one season - could be inactive or temporary absence
        return 'inactive'
    elif last_year >= current_year - 4:
        # 2-3 seasons ago - likely inactive but not retired
        return 'inactive'
    else:
        # 4+ seasons ago - likely retired
        return 'retired'

def aggregate_player_data(player_data: pd.DataFrame) -> Dict:
    """Aggregate player data across seasons using weighted averages"""
    if len(player_data) == 1:
        # Single season - just add metadata
        row = player_data.iloc[0].to_dict()
        row['seasons_played'] = 1
        row['last_season_played'] = row['Season']
        row['player_status'] = 'active'
        return row
    
    # Multiple seasons - calculate weighted averages
    player_data = player_data.sort_values('Season')
    
    # Calculate weights based on minutes played
    weights = pd.to_numeric(player_data['minutes_90s'], errors='coerce').fillna(0)
    if weights.sum() == 0:
        # Fallback to matches if no minutes data
        weights = pd.to_numeric(player_data['matches'], errors='coerce').fillna(0)
    
    if weights.sum() == 0:
        # Fallback to equal weights
        weights = pd.Series([1.0] * len(player_data))
    
    # Normalize weights
    weights = weights / weights.sum()
    
    # Calculate weighted averages for numeric columns
    result = {}
    for col in WEIGHTED_AVERAGE_COLUMNS:
        if col in player_data.columns:
            numeric_data = pd.to_numeric(player_data[col], errors='coerce').fillna(0)
            result[col] = calculate_weighted_average(numeric_data, weights)
    
    # Priority for Team/League: 24-25 first, then most recent
    current_season_data = player_data[player_data['Season'] == '2024-25']
    if not current_season_data.empty:
        # Use 24-25 data for Team/League if available
        for col in ['Team', 'League', 'Team_Logo']:
            if col in player_data.columns:
                result[col] = current_season_data[col].iloc[0]
    else:
        # Use most recent season data
        for col in ['Team', 'League', 'Team_Logo']:
            if col in player_data.columns:
                result[col] = player_data[col].iloc[-1]
    
    # Use most recent values for other specific columns
    for col in ['player', 'nationalit', 'position']:
        if col in player_data.columns:
            result[col] = player_data[col].iloc[-1]
    
    # Sum columns
    for col in SUM_COLUMNS:
        if col in player_data.columns:
            numeric_data = pd.to_numeric(player_data[col], errors='coerce').fillna(0)
            result[col] = numeric_data.sum()
    
    # Add metadata
    result['seasons_played'] = len(player_data)
    result['last_season_played'] = player_data['Season'].iloc[-1]
    result['player_status'] = determine_player_status(player_data)
    result['Season'] = f"{player_data['Season'].min()}-{player_data['Season'].max()}"
    
    return result

def process_historical_data_by_league_season(input_file: str, current_season_file: str = "data/current_season_players_normalized.csv", output_dir: str = "data"):
    """Process historical data by league and season"""
    
    print("Loading historical data...")
    df = pd.read_csv(input_file)
    print(f"Loaded {len(df)} historical records")
    
    # Load current season data (24-25) if available
    current_df = None
    if os.path.exists(current_season_file):
        print("Loading current season data (24-25)...")
        current_df = pd.read_csv(current_season_file)
        print(f"Loaded {len(current_df)} current season records")
        # Clean current season data
        current_df = clean_numeric_columns(current_df)
        # Clean names in current season data too
        current_df['player'] = current_df['player'].apply(clean_name)
        current_df['Team'] = current_df['Team'].apply(clean_team_name)
        current_df['League'] = current_df['League'].apply(clean_name)
    
    # Clean numeric columns for historical data
    df = clean_numeric_columns(df)
    
    # Clean player and team names
    print("Cleaning player and team names...")
    df['player'] = df['player'].apply(clean_name)
    df['Team'] = df['Team'].apply(clean_team_name)
    df['League'] = df['League'].apply(clean_name)
    
    # Filter out seasons with very few games (likely injury seasons)
    print("Filtering out injury seasons (games < 10)...")
    initial_count = len(df)
    df = df[df['games'] >= 10]
    filtered_count = initial_count - len(df)
    print(f"Filtered out {filtered_count} records with <10 games")
    
    # Combine historical and current season data
    if current_df is not None:
        print("Combining historical and current season data...")
        df = pd.concat([df, current_df], ignore_index=True)
        print(f"Combined dataset: {len(df)} records")
    
    # Sort by season to ensure proper ordering
    df = df.sort_values(['player', 'Season'])
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Process by league and season
    league_season_groups = df.groupby(['League', 'Season'])
    
    print(f"Found {len(league_season_groups)} league-season combinations")
    
    all_processed_data = []
    
    for (league, season), group_data in league_season_groups:
        print(f"Processing {league} - {season} ({len(group_data)} players)...")
        
        # Save individual league-season file
        filename = f"{league.replace(' ', '_')}_{season.replace('-', '_')}.csv"
        filepath = os.path.join(output_dir, filename)
        group_data.to_csv(filepath, index=False)
        print(f"  Saved: {filename}")
        
        # Add to combined data
        all_processed_data.append(group_data)
    
    # Create combined dataset
    print("\nCreating combined dataset...")
    combined_df = pd.concat(all_processed_data, ignore_index=True)
    combined_file = os.path.join(output_dir, "historical_players_by_league_season.csv")
    combined_df.to_csv(combined_file, index=False)
    print(f"Combined dataset saved: {combined_file}")
    
    # Now aggregate by player
    print("\nAggregating by player...")
    player_groups = combined_df.groupby('player')
    print(f"Found {len(player_groups)} unique players")
    
    aggregated_players = []
    processed_players = set()  # Track processed players to avoid duplicates
    
    for i, (player_name, player_data) in enumerate(player_groups):
        if i % 1000 == 0:
            print(f"  Processing player {i+1}/{len(player_groups)}: {player_name}")
        
        # Skip if already processed (duplicate name)
        if player_name in processed_players:
            print(f"    Skipping duplicate player: {player_name}")
            continue
            
        aggregated = aggregate_player_data(player_data)
        if aggregated:
            aggregated_players.append(aggregated)
            processed_players.add(player_name)
    
    # Save aggregated data
    aggregated_df = pd.DataFrame(aggregated_players)
    
    # Final duplicate check and removal
    print(f"\nFinal duplicate check...")
    initial_count = len(aggregated_df)
    aggregated_df = aggregated_df.drop_duplicates(subset=['player'], keep='first')
    final_count = len(aggregated_df)
    duplicates_removed = initial_count - final_count
    
    if duplicates_removed > 0:
        print(f"Removed {duplicates_removed} duplicate players")
    
    aggregated_file = os.path.join(output_dir, "historical_players_aggregated.csv")
    aggregated_df.to_csv(aggregated_file, index=False)
    print(f"Aggregated dataset saved: {aggregated_file}")
    print(f"Final aggregated dataset: {len(aggregated_df)} unique players")
    
    # Summary statistics
    print("\n=== SUMMARY ===")
    print(f"Total records processed: {len(combined_df)}")
    print(f"Unique players: {len(aggregated_df)}")
    print(f"Leagues processed: {combined_df['League'].nunique()}")
    print(f"Seasons processed: {combined_df['Season'].nunique()}")
    
    # Player status breakdown
    if 'player_status' in aggregated_df.columns:
        status_counts = aggregated_df['player_status'].value_counts()
        print(f"\nPlayer status breakdown:")
        for status, count in status_counts.items():
            percentage = (count / len(aggregated_df)) * 100
            print(f"  {status}: {count} ({percentage:.1f}%)")
    
    # Data quality checks
    print(f"\nData quality checks:")
    print(f"  Players with multiple seasons: {len(aggregated_df[aggregated_df['seasons_played'] > 1])}")
    print(f"  Players from 24-25 season: {len(aggregated_df[aggregated_df['last_season_played'] == '2024-25'])}")
    print(f"  Players with valid team data: {len(aggregated_df[aggregated_df['Team'].notna()])}")
    print(f"  Duplicates removed: {duplicates_removed}")
    
    # Active vs Retired breakdown
    active_players = len(aggregated_df[aggregated_df['player_status'] == 'active'])
    inactive_players = len(aggregated_df[aggregated_df['player_status'] == 'inactive'])
    retired_players = len(aggregated_df[aggregated_df['player_status'] == 'retired'])
    
    print(f"\nPlayer activity summary:")
    print(f"  Active players: {active_players} ({(active_players/len(aggregated_df)*100):.1f}%)")
    print(f"  Inactive players: {inactive_players} ({(inactive_players/len(aggregated_df)*100):.1f}%)")
    print(f"  Retired players: {retired_players} ({(retired_players/len(aggregated_df)*100):.1f}%)")
    
    # Save processing summary
    summary_file = os.path.join(output_dir, "processing_summary.txt")
    with open(summary_file, 'w') as f:
        f.write("Historical Data Processing Summary\n")
        f.write("=" * 40 + "\n\n")
        f.write(f"Total records processed: {len(combined_df)}\n")
        f.write(f"Unique players: {len(aggregated_df)}\n")
        f.write(f"Leagues processed: {combined_df['League'].nunique()}\n")
        f.write(f"Seasons processed: {combined_df['Season'].nunique()}\n\n")
        f.write("Player status breakdown:\n")
        for status, count in status_counts.items():
            f.write(f"  {status}: {count}\n")
        f.write(f"\nPlayers with multiple seasons: {len(aggregated_df[aggregated_df['seasons_played'] > 1])}\n")
        f.write(f"Players from 24-25 season: {len(aggregated_df[aggregated_df['last_season_played'] == '2024-25'])}\n")
        f.write(f"Players with valid team data: {len(aggregated_df[aggregated_df['Team'].notna()])}\n")
        f.write(f"Duplicates removed: {duplicates_removed}\n")
        f.write(f"\nPlayer activity summary:\n")
        f.write(f"  Active players: {active_players} ({(active_players/len(aggregated_df)*100):.1f}%)\n")
        f.write(f"  Inactive players: {inactive_players} ({(inactive_players/len(aggregated_df)*100):.1f}%)\n")
        f.write(f"  Retired players: {retired_players} ({(retired_players/len(aggregated_df)*100):.1f}%)\n")
    
    print(f"\nProcessing summary saved to: {summary_file}")
    
    return aggregated_df

if __name__ == "__main__":
    # Process the historical data
    input_file = "data/historical_players_raw.csv"
    current_season_file = "data/current_season_players_normalized.csv"
    output_dir = "data"
    
    if not os.path.exists(input_file):
        print(f"Error: Input file {input_file} not found!")
        exit(1)
    
    # Check if current season file exists
    if not os.path.exists(current_season_file):
        print(f"Warning: Current season file {current_season_file} not found!")
        print("Processing will continue with historical data only.")
        current_season_file = None
    
    aggregated_df = process_historical_data_by_league_season(input_file, current_season_file, output_dir)
    print("\nProcessing complete!")
