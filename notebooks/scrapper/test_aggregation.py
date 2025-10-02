#!/usr/bin/env python3
"""
test_aggregation.py

Test script to validate the aggregation functionality with sample data.

Usage:
    python test_aggregation.py

Requirements:
    pip install pandas numpy
"""
import pandas as pd
import numpy as np
from aggregate_historical_data import (
    clean_numeric_columns, 
    get_season_weight, 
    calculate_weighted_average,
    determine_player_status,
    get_last_season_played,
    get_seasons_played,
    aggregate_player_data
)
import os

def create_test_data():
    """Create sample test data for aggregation testing."""
    print("Creating test data...")
    
    # Sample data for a player across multiple seasons
    test_data = [
        {
            'player': 'Test Player',
            'nationalit': 'ESP',
            'position': 'MF',
            'age': 25,
            'Season': '2023-24',
            'Team': 'Real Madrid',
            'League': 'La Liga',
            'games': 30,
            'minutes': 2500,
            'goals': 5,
            'assists': 8,
            'xg': 4.5,
            'npxg': 4.0,
            'passes': 1500,
            'passes_pct': 85.5,
            'tackles': 45,
            'interceptions': 20,
        },
        {
            'player': 'Test Player',
            'nationalit': 'ESP',
            'position': 'MF',
            'age': 24,
            'Season': '2022-23',
            'Team': 'Real Madrid',
            'League': 'La Liga',
            'games': 28,
            'minutes': 2200,
            'goals': 3,
            'assists': 6,
            'xg': 3.2,
            'npxg': 2.8,
            'passes': 1300,
            'passes_pct': 82.1,
            'tackles': 50,
            'interceptions': 18,
        },
        {
            'player': 'Test Player',
            'nationalit': 'ESP',
            'position': 'MF',
            'age': 23,
            'Season': '2021-22',
            'Team': 'Real Madrid',
            'League': 'La Liga',
            'games': 25,
            'minutes': 1800,
            'goals': 2,
            'assists': 4,
            'xg': 2.1,
            'npxg': 1.9,
            'passes': 1100,
            'passes_pct': 80.5,
            'tackles': 40,
            'interceptions': 15,
        }
    ]
    
    # Create DataFrame
    df = pd.DataFrame(test_data)
    print(f"Created test data with {len(df)} records")
    
    return df

def test_individual_functions():
    """Test individual aggregation functions."""
    print("\n=== TESTING INDIVIDUAL FUNCTIONS ===")
    
    # Test season weights
    print("Testing season weights:")
    for season in ['2023-24', '2022-23', '2021-22', '2020-21']:
        weight = get_season_weight(season)
        print(f"  {season}: {weight}")
    
    # Test weighted average calculation
    print("\nTesting weighted average calculation:")
    test_df = create_test_data()
    
    # Test with goals column
    goals_avg = calculate_weighted_average(test_df, 'goals')
    print(f"  Weighted average goals: {goals_avg:.2f}")
    
    # Test with xg column
    xg_avg = calculate_weighted_average(test_df, 'xg')
    print(f"  Weighted average xG: {xg_avg:.2f}")
    
    # Test player status determination
    print("\nTesting player status determination:")
    status = determine_player_status(test_df)
    print(f"  Player status: {status}")
    
    last_season = get_last_season_played(test_df)
    print(f"  Last season played: {last_season}")
    
    seasons_count = get_seasons_played(test_df)
    print(f"  Seasons played: {seasons_count}")

def test_full_aggregation():
    """Test full aggregation process."""
    print("\n=== TESTING FULL AGGREGATION ===")
    
    # Create test data
    test_df = create_test_data()
    
    # Test aggregation
    print("Running aggregation...")
    aggregated = aggregate_player_data(test_df)
    
    if not aggregated.empty:
        print("Aggregation successful!")
        print("\nAggregated data:")
        print(f"  Player: {aggregated['player']}")
        print(f"  Nationality: {aggregated['nationalit']}")
        print(f"  Position: {aggregated['position']}")
        print(f"  Most common position: {aggregated['most_common_position']}")
        print(f"  Player status: {aggregated['player_status']}")
        print(f"  Last season: {aggregated['last_season_played']}")
        print(f"  Seasons played: {aggregated['seasons_played']}")
        print(f"  Total seasons: {aggregated['total_seasons']}")
        print(f"  Most recent team: {aggregated['most_recent_team']}")
        print(f"  Most recent league: {aggregated['most_recent_league']}")
        
        print("\nWeighted averages:")
        print(f"  Goals: {aggregated['goals']:.2f}")
        print(f"  Assists: {aggregated['assists']:.2f}")
        print(f"  xG: {aggregated['xg']:.2f}")
        print(f"  npxG: {aggregated['npxg']:.2f}")
        print(f"  Passes: {aggregated['passes']:.2f}")
        print(f"  Pass accuracy: {aggregated['passes_pct']:.2f}%")
        print(f"  Tackles: {aggregated['tackles']:.2f}")
        print(f"  Interceptions: {aggregated['interceptions']:.2f}")
        
        # Verify weighted average calculation manually
        print("\nManual verification:")
        weights = [1.0, 0.9, 0.8]  # 2023-24, 2022-23, 2021-22
        goals = [5, 3, 2]
        manual_goals_avg = np.average(goals, weights=weights)
        print(f"  Manual goals average: {manual_goals_avg:.2f}")
        print(f"  Script goals average: {aggregated['goals']:.2f}")
        print(f"  Match: {abs(manual_goals_avg - aggregated['goals']) < 0.01}")
        
    else:
        print("Aggregation failed!")

def test_with_real_data():
    """Test with real data if available."""
    print("\n=== TESTING WITH REAL DATA ===")
    
    # Check if test data exists
    test_file = 'data/test_historical_players_raw.csv'
    if os.path.exists(test_file):
        print(f"Loading real test data from {test_file}")
        df = pd.read_csv(test_file)
        print(f"Loaded {len(df)} records")
        
        # Group by player and test aggregation
        grouped = df.groupby(['player', 'nationalit'])
        print(f"Found {len(grouped)} unique players")
        
        # Test aggregation for first few players
        for i, (player_key, player_data) in enumerate(grouped):
            if i >= 3:  # Only test first 3 players
                break
                
            print(f"\nTesting player {i+1}: {player_key[0]} ({player_key[1]})")
            aggregated = aggregate_player_data(player_data)
            
            if not aggregated.empty:
                print(f"  Status: {aggregated['player_status']}")
                print(f"  Seasons: {aggregated['seasons_played']}")
                print(f"  Position: {aggregated['most_common_position']}")
                print(f"  Recent team: {aggregated['most_recent_team']}")
            else:
                print("  Aggregation failed")
    else:
        print("No real test data found. Run the scraper first.")

def main():
    """Main test function."""
    print("=== AGGREGATION TESTING ===")
    
    # Test individual functions
    test_individual_functions()
    
    # Test full aggregation
    test_full_aggregation()
    
    # Test with real data if available
    test_with_real_data()
    
    print("\n=== TESTING COMPLETED ===")

if __name__ == "__main__":
    main()
