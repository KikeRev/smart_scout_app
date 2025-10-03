#!/usr/bin/env python3
"""
aggregate_historical_data.py

Script to aggregate historical player data across multiple seasons using weighted averages.
This script processes raw historical data and creates aggregated player profiles.

Usage:
    python aggregate_historical_data.py

Requirements:
    pip install pandas numpy
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import os
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# -----------------------------
# Configuration
# -----------------------------

# Weight factors for different seasons (more recent = higher weight)
SEASON_WEIGHTS = {
    '2023-24': 1.0,  # Most recent season
    '2022-23': 0.9,
    '2021-22': 0.8,
    '2020-21': 0.7,
    '2019-20': 0.6,  # Oldest season
}

# Columns to aggregate using weighted average
WEIGHTED_AVERAGE_COLUMNS = [
    # Basic stats
    'age', 'games', 'games_starts', 'minutes', 'minutes_90s',
    'goals', 'assists', 'goals_assists', 'goals_pens', 'pens_made', 'pens_att',
    'cards_yellow', 'cards_red',
    
    # Advanced stats
    'xg', 'npxg', 'xg_assist', 'npxg_xg_assist',
    'progressive_carries', 'progressive_passes', 'progressive_passes_received',
    'goals_per90', 'assists_per90', 'goals_assists_per90', 'goals_pens_per90',
    'goals_assists_pens_per90', 'xg_per90', 'xg_assist_per90', 'xg_xg_assist_per90',
    'npxg_per90', 'npxg_xg_assist_per90',
    
    # Shooting stats
    'shots', 'shots_on_target', 'shots_on_target_pct', 'shots_per90', 'shots_on_target_per90',
    'goals_per_shot', 'goals_per_shot_on_target', 'average_shot_distance',
    'shots_free_kicks', 'npxg_per_shot', 'xg_net', 'npxg_net',
    
    # Passing stats
    'passes_completed', 'passes', 'passes_pct', 'passes_total_distance',
    'passes_progressive_distance', 'passes_completed_short', 'passes_short', 'passes_pct_short',
    'passes_completed_medium', 'passes_medium', 'passes_pct_medium',
    'passes_completed_long', 'passes_long', 'passes_pct_long',
    'pass_xa', 'xg_assist_net', 'assisted_shots', 'passes_into_final_third',
    'passes_into_penalty_area', 'crosses_into_penalty_area',
    'passes_live', 'passes_dead', 'passes_free_kicks', 'through_balls',
    'passes_switches', 'crosses', 'throw_ins', 'corner_kicks', 'corner_kicks_in',
    'corner_kicks_out', 'corner_kicks_straight', 'passes_completed', 'passes_offsides',
    'passes_blocked',
    
    # SCA/GCA stats
    'sca', 'sca_per90', 'sca_passes_live', 'sca_passes_dead', 'sca_take_ons',
    'sca_shots', 'sca_fouled', 'sca_defense', 'gca', 'gca_per90',
    'gca_passes_live', 'gca_passes_dead', 'gca_take_ons', 'gca_shots',
    'gca_fouled', 'gca_defense',
    
    # Defensive stats
    'tackles', 'tackles_won', 'tackles_def_3rd', 'tackles_mid_3rd', 'tackles_att_3rd',
    'challenge_tackles', 'challenges', 'challenge_tackles_pct', 'challenges_lost',
    'blocks', 'blocked_shots', 'blocked_passes', 'interceptions', 'tackles_interceptions',
    'clearances', 'errors',
    
    # Possession stats
    'touches', 'touches_def_pen_area', 'touches_def_3rd', 'touches_mid_3rd',
    'touches_att_3rd', 'touches_att_pen_area', 'touches_live_ball',
    'take_ons', 'take_ons_won', 'take_ons_won_pct', 'take_ons_tackled', 'take_ons_tackled_pct',
    'carries', 'carries_distance', 'carries_progressive_distance', 'progressive_carries',
    'carries_into_final_third', 'carries_into_penalty_area', 'miscontrols', 'dispossessed',
    'passes_received', 'progressive_passes_received',
    
    # Playing time stats
    'minutes_per_game', 'minutes_pct', 'minutes_per_start', 'games_complete',
    'games_subs', 'minutes_per_sub', 'unused_subs', 'points_per_game',
    'on_goals_for', 'on_goals_against', 'plus_minus', 'plus_minus_per90', 'plus_minus_wow',
    'on_xg_for', 'on_xg_against', 'xg_plus_minus', 'xg_plus_minus_per90', 'xg_plus_minus_wow',
    
    # Goalkeeper stats (if applicable)
    'gk_goals_against', 'gk_pens_allowed', 'gk_free_kick_goals_against',
    'gk_corner_kick_goals_against', 'gk_own_goals_against', 'gk_psxg',
    'gk_psnpxg_per_shot_on_target_against', 'gk_psxg_net', 'gk_psxg_net_per90',
    'gk_passes_completed_launched', 'gk_passes_launched', 'gk_passes_pct_launched',
    'gk_passes', 'gk_passes_throws', 'gk_pct_passes_launched', 'gk_passes_length_avg',
    'gk_goal_kicks', 'gk_pct_goal_kicks_launched', 'gk_goal_kick_length_avg',
    'gk_crosses', 'gk_crosses_stopped', 'gk_crosses_stopped_pct',
    'gk_def_actions_outside_pen_area', 'gk_def_actions_outside_pen_area_per90',
    'gk_avg_distance_def_actions',
]

# Columns to take the most recent value (not weighted average)
MOST_RECENT_COLUMNS = [
    'player', 'nationalit', 'position', 'Team', 'League', 'Team_Logo'
]

# Columns to sum across seasons
SUM_COLUMNS = [
    'matches'  # Total matches played across all seasons
]

# -----------------------------
# Helper Functions
# -----------------------------

def clean_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and convert numeric columns."""
    for col in df.columns:
        if col in WEIGHTED_AVERAGE_COLUMNS + SUM_COLUMNS:
            # Replace empty strings and non-numeric values with NaN
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df

def get_season_weight(season: str) -> float:
    """Get weight for a season based on recency."""
    return SEASON_WEIGHTS.get(season, 0.5)  # Default weight for unknown seasons

def calculate_weighted_average(group: pd.DataFrame, column: str) -> float:
    """Calculate weighted average for a column based on season weights."""
    if column not in group.columns:
        return np.nan
    
    # Get season weights
    weights = group['Season'].apply(get_season_weight).values
    values = group[column].values
    
    # Remove NaN values
    mask = ~np.isnan(values)
    if not mask.any():
        return np.nan
    
    values = values[mask]
    weights = weights[mask]
    
    # Calculate weighted average
    return np.average(values, weights=weights)

def determine_player_status(player_data: pd.DataFrame) -> str:
    """
    Determine if a player is active, inactive, or retired based on recent seasons.
    """
    # Get unique seasons for this player, sorted by most recent
    seasons = sorted(player_data['Season'].unique(), reverse=True)
    
    if not seasons:
        return 'unknown'
    
    # Check if player played in the most recent season
    most_recent_season = seasons[0]
    recent_data = player_data[player_data['Season'] == most_recent_season]
    
    if recent_data.empty:
        return 'retired'
    
    # Check if player had significant minutes in recent season
    recent_minutes = recent_data['minutes'].sum()
    
    if recent_minutes >= 500:  # At least 500 minutes in most recent season
        return 'active'
    elif recent_minutes >= 100:  # Some minutes but not much
        return 'inactive'
    else:
        return 'retired'

def get_last_season_played(player_data: pd.DataFrame) -> str:
    """Get the last season a player played."""
    seasons = sorted(player_data['Season'].unique(), reverse=True)
    return seasons[0] if seasons else 'unknown'

def get_seasons_played(player_data: pd.DataFrame) -> int:
    """Get total number of seasons a player played."""
    return len(player_data['Season'].unique())

def aggregate_player_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate data for a single player across multiple seasons.
    """
    if df.empty:
        return pd.DataFrame()
    
    # Clean numeric columns
    df = clean_numeric_columns(df)
    
    # Create aggregated record
    aggregated = {}
    
    # Most recent values
    for col in MOST_RECENT_COLUMNS:
        if col in df.columns:
            # Take the most recent non-null value
            recent_data = df.sort_values('Season', ascending=False)
            aggregated[col] = recent_data[col].dropna().iloc[0] if not recent_data[col].dropna().empty else None
    
    # Sum columns
    for col in SUM_COLUMNS:
        if col in df.columns:
            aggregated[col] = df[col].sum()
    
    # Weighted average columns
    for col in WEIGHTED_AVERAGE_COLUMNS:
        if col in df.columns:
            aggregated[col] = calculate_weighted_average(df, col)
    
    # Player status information
    aggregated['player_status'] = determine_player_status(df)
    aggregated['last_season_played'] = get_last_season_played(df)
    aggregated['seasons_played'] = get_seasons_played(df)
    
    # Additional metadata
    aggregated['total_seasons'] = len(df['Season'].unique())
    aggregated['total_teams'] = len(df['Team'].unique())
    aggregated['total_leagues'] = len(df['League'].unique())
    
    # Most common position across seasons
    if 'position' in df.columns:
        position_counts = df['position'].value_counts()
        aggregated['most_common_position'] = position_counts.index[0] if not position_counts.empty else None
    else:
        aggregated['most_common_position'] = None
    
    # Most recent team and league
    recent_data = df.sort_values('Season', ascending=False).iloc[0]
    aggregated['most_recent_team'] = recent_data.get('Team', None)
    aggregated['most_recent_league'] = recent_data.get('League', None)
    
    return pd.Series(aggregated)

# -----------------------------
# Main Processing Functions
# -----------------------------

def load_historical_data(data_dir: str = 'data') -> pd.DataFrame:
    """Load all historical data from CSV files."""
    print("Loading historical data...")
    
    # Look for historical data files
    historical_files = []
    for file in os.listdir(data_dir):
        if file.startswith('historical_players_raw') and file.endswith('.csv'):
            historical_files.append(os.path.join(data_dir, file))
    
    if not historical_files:
        print("No historical data files found. Please run the scraper first.")
        return pd.DataFrame()
    
    print(f"Found {len(historical_files)} historical data files")
    
    # Load and combine all files
    all_data = []
    for file in historical_files:
        print(f"  Loading: {file}")
        df = pd.read_csv(file)
        all_data.append(df)
    
    if not all_data:
        return pd.DataFrame()
    
    combined_df = pd.concat(all_data, ignore_index=True, sort=False)
    print(f"Total records loaded: {len(combined_df)}")
    
    return combined_df

def process_historical_data(df: pd.DataFrame) -> pd.DataFrame:
    """Process and aggregate historical data by player."""
    print("Processing historical data...")
    
    if df.empty:
        print("No data to process.")
        return pd.DataFrame()
    
    # Group by player name and nationality (to handle players with same name)
    print("Grouping data by player...")
    grouped = df.groupby(['player', 'nationalit'])
    
    print(f"Found {len(grouped)} unique players")
    
    # Aggregate each player's data
    print("Aggregating player data...")
    aggregated_data = []
    
    for i, (player_key, player_data) in enumerate(grouped):
        if i % 100 == 0:
            print(f"  Processed {i}/{len(grouped)} players...")
        
        aggregated_player = aggregate_player_data(player_data)
        if not aggregated_player.empty:
            aggregated_data.append(aggregated_player)
    
    if not aggregated_data:
        print("No aggregated data generated.")
        return pd.DataFrame()
    
    # Combine all aggregated data
    result_df = pd.DataFrame(aggregated_data)
    
    print(f"Aggregated data for {len(result_df)} players")
    
    return result_df

def save_aggregated_data(df: pd.DataFrame, output_dir: str = 'data') -> None:
    """Save aggregated data to CSV files."""
    if df.empty:
        print("No data to save.")
        return
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Save aggregated data
    output_file = os.path.join(output_dir, 'historical_players_aggregated.csv')
    df.to_csv(output_file, index=False)
    print(f"Aggregated data saved to: {output_file}")
    
    # Save summary statistics
    summary_file = os.path.join(output_dir, 'aggregation_summary.txt')
    with open(summary_file, 'w') as f:
        f.write("HISTORICAL DATA AGGREGATION SUMMARY\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Total players aggregated: {len(df)}\n")
        f.write(f"Active players: {len(df[df['player_status'] == 'active'])}\n")
        f.write(f"Inactive players: {len(df[df['player_status'] == 'inactive'])}\n")
        f.write(f"Retired players: {len(df[df['player_status'] == 'retired'])}\n\n")
        
        f.write("SEASONS COVERED:\n")
        f.write("-" * 20 + "\n")
        for season in sorted(SEASON_WEIGHTS.keys(), reverse=True):
            f.write(f"{season}: Weight {SEASON_WEIGHTS[season]}\n")
        
        f.write(f"\nCOLUMNS PROCESSED:\n")
        f.write("-" * 20 + "\n")
        f.write(f"Weighted average columns: {len(WEIGHTED_AVERAGE_COLUMNS)}\n")
        f.write(f"Most recent columns: {len(MOST_RECENT_COLUMNS)}\n")
        f.write(f"Sum columns: {len(SUM_COLUMNS)}\n")
        
        f.write(f"\nSAMPLE DATA:\n")
        f.write("-" * 20 + "\n")
        f.write(df[['player', 'nationalit', 'most_common_position', 'player_status', 
                   'last_season_played', 'seasons_played']].head(10).to_string(index=False))
    
    print(f"Summary saved to: {summary_file}")

# -----------------------------
# Main
# -----------------------------

def main():
    """Main function to process historical data."""
    print("=== HISTORICAL DATA AGGREGATION ===")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Load historical data
    df = load_historical_data()
    
    if df.empty:
        print("No historical data found. Please run the scraper first.")
        return
    
    # Process data
    aggregated_df = process_historical_data(df)
    
    if aggregated_df.empty:
        print("No aggregated data generated.")
        return
    
    # Save results
    save_aggregated_data(aggregated_df)
    
    print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Aggregation completed successfully!")

if __name__ == "__main__":
    main()
