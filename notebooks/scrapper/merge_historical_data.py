#!/usr/bin/env python3
"""
merge_historical_data.py

Script to merge historical data (2014-15 to 2023-24) with current season data (2024-25).
Creates a unified dataset for database storage and dashboard visualization.

Usage:
    python merge_historical_data.py

Requirements:
    pip install pandas
"""
import pandas as pd
import os
from pathlib import Path
from typing import List, Dict
import glob

def load_historical_files(data_dir: str = "notebooks/scrapper/data") -> pd.DataFrame:
    """
    Load all historical CSV files from the historical_raw directory.
    
    Args:
        data_dir: Directory containing historical CSV files
        
    Returns:
        Combined DataFrame with all historical data
    """
    print("Loading historical data files...")
    
    # Find all CSV files in the directory (excluding the combined files)
    csv_files = glob.glob(f"{data_dir}/*.csv")
    csv_files = [f for f in csv_files if not f.endswith(('all_historical_raw.csv', 'historical_players_aggregated.csv'))]
    
    if not csv_files:
        print(f"No CSV files found in {data_dir}")
        return pd.DataFrame()
    
    print(f"Found {len(csv_files)} historical files:")
    for file in csv_files:
        print(f"  - {os.path.basename(file)}")
    
    # Load and combine all files
    all_data = []
    for file in csv_files:
        try:
            df = pd.read_csv(file)
            if not df.empty:
                all_data.append(df)
                print(f"  ✓ Loaded {len(df)} records from {os.path.basename(file)}")
            else:
                print(f"  ⚠ Empty file: {os.path.basename(file)}")
        except Exception as e:
            print(f"  ✗ Error loading {os.path.basename(file)}: {e}")
    
    if all_data:
        combined_df = pd.concat(all_data, ignore_index=True, sort=False)
        print(f"\nTotal historical records: {len(combined_df)}")
        return combined_df
    else:
        print("No data loaded from historical files")
        return pd.DataFrame()

def load_current_season_data(file_path: str = "data/all_players_cleaned.csv") -> pd.DataFrame:
    """
    Load current season data (2024-25).
    
    Args:
        file_path: Path to current season CSV file
        
    Returns:
        DataFrame with current season data
    """
    print(f"\nLoading current season data from {file_path}...")
    
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found")
        return pd.DataFrame()
    
    try:
        df = pd.read_csv(file_path)
        # Add season column if not present
        if 'Season' not in df.columns:
            df['Season'] = '2024-25'
        if 'player_status' not in df.columns:
            df['player_status'] = 'active'
        
        print(f"✓ Loaded {len(df)} records from current season")
        return df
    except Exception as e:
        print(f"✗ Error loading current season data: {e}")
        return pd.DataFrame()

def merge_datasets(historical_df: pd.DataFrame, current_df: pd.DataFrame) -> pd.DataFrame:
    """
    Merge historical and current season data.
    
    Args:
        historical_df: Historical data (2014-15 to 2023-24)
        current_df: Current season data (2024-25)
        
    Returns:
        Combined DataFrame
    """
    print("\nMerging datasets...")
    
    if historical_df.empty and current_df.empty:
        print("No data to merge")
        return pd.DataFrame()
    
    if historical_df.empty:
        print("Only current season data available")
        return current_df
    
    if current_df.empty:
        print("Only historical data available")
        return historical_df
    
    # Combine datasets
    combined_df = pd.concat([historical_df, current_df], ignore_index=True, sort=False)
    
    print(f"✓ Combined dataset: {len(combined_df)} total records")
    print(f"  - Historical: {len(historical_df)} records")
    print(f"  - Current: {len(current_df)} records")
    
    return combined_df

def add_metadata(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add metadata columns for better data management.
    
    Args:
        df: Input DataFrame
        
    Returns:
        DataFrame with added metadata
    """
    print("\nAdding metadata...")
    
    # Add data source information
    df['data_source'] = 'fbref'
    df['scraped_at'] = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Ensure required columns exist
    required_cols = ['player', 'Team', 'League', 'Season', 'player_status']
    for col in required_cols:
        if col not in df.columns:
            if col == 'player_status':
                df[col] = 'unknown'
            else:
                df[col] = 'unknown'
    
    print("✓ Metadata added")
    return df

def save_merged_data(df: pd.DataFrame, output_dir: str = "notebooks/scrapper/data") -> None:
    """
    Save the merged dataset to CSV files.
    
    Args:
        df: Combined DataFrame
        output_dir: Output directory
    """
    print(f"\nSaving merged data to {output_dir}...")
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Save complete dataset
    complete_path = f"{output_dir}/complete_historical_dataset.csv"
    df.to_csv(complete_path, index=False)
    print(f"✓ Complete dataset saved: {complete_path} ({len(df)} records)")
    
    # Save summary statistics
    summary_path = f"{output_dir}/dataset_summary.txt"
    with open(summary_path, 'w') as f:
        f.write("HISTORICAL DATASET SUMMARY\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Total records: {len(df)}\n")
        f.write(f"Unique players: {df['player'].nunique()}\n")
        f.write(f"Seasons covered: {sorted(df['Season'].unique())}\n")
        f.write(f"Leagues: {sorted(df['League'].unique())}\n\n")
        
        f.write("Records by season:\n")
        season_counts = df['Season'].value_counts().sort_index()
        for season, count in season_counts.items():
            f.write(f"  {season}: {count} records\n")
        
        f.write("\nRecords by league:\n")
        league_counts = df['League'].value_counts()
        for league, count in league_counts.items():
            f.write(f"  {league}: {count} records\n")
        
        f.write("\nPlayer status distribution:\n")
        status_counts = df['player_status'].value_counts()
        for status, count in status_counts.items():
            f.write(f"  {status}: {count} records\n")
    
    print(f"✓ Summary saved: {summary_path}")

def main():
    """Main function to execute the data merging process."""
    print("=== HISTORICAL DATA MERGER ===")
    print("Merging historical data (2014-15 to 2023-24) with current season (2024-25)")
    
    # Load historical data
    historical_df = load_historical_files()
    
    # Load current season data
    current_df = load_current_season_data()
    
    # Merge datasets
    merged_df = merge_datasets(historical_df, current_df)
    
    if merged_df.empty:
        print("No data to process. Exiting.")
        return
    
    # Add metadata
    merged_df = add_metadata(merged_df)
    
    # Save merged data
    save_merged_data(merged_df)
    
    print("\n=== MERGE COMPLETE ===")
    print("Files created:")
    print("  - notebooks/scrapper/data/complete_historical_dataset.csv")
    print("  - notebooks/scrapper/data/dataset_summary.txt")
    print("\nReady for database import and dashboard visualization!")

if __name__ == "__main__":
    main()
