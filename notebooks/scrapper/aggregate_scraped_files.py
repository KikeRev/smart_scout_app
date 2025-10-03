#!/usr/bin/env python3
"""
aggregate_scraped_files.py

Script to aggregate already scraped individual league/season CSV files.
Use this when scraping completed but aggregation failed.

Usage:
    python aggregate_scraped_files.py
"""
import pandas as pd
import glob
import os
from typing import List

def load_scraped_files(data_dir: str = "notebooks/scrapper/data") -> List[pd.DataFrame]:
    """Load all scraped league/season CSV files."""
    print("Loading scraped files...")
    
    # Find all league/season CSV files (exclude aggregated files)
    pattern = f"{data_dir}/*_*_*.csv"  # Matches: League_YYYY_YY.csv
    csv_files = glob.glob(pattern)
    
    # Filter out any previously generated aggregate files
    csv_files = [f for f in csv_files if not any(x in f for x in ['historical_players', 'all_players', 'complete'])]
    
    print(f"Found {len(csv_files)} league/season files")
    
    all_dfs = []
    for file in sorted(csv_files):
        try:
            df = pd.read_csv(file)
            if not df.empty:
                all_dfs.append(df)
                print(f"  ✓ Loaded {os.path.basename(file)}: {len(df)} records")
            else:
                print(f"  ⚠ Empty: {os.path.basename(file)}")
        except Exception as e:
            print(f"  ✗ Error loading {os.path.basename(file)}: {e}")
    
    return all_dfs

def main():
    """Main aggregation function."""
    print("=== AGGREGATE SCRAPED FILES ===\n")
    
    # Load all scraped files
    all_team_data = load_scraped_files()
    
    if not all_team_data:
        print("No data found to aggregate!")
        return
    
    print(f"\n=== PROCESSING {len(all_team_data)} FILES ===")
    
    try:
        # Reset index for each dataframe
        print("Resetting indexes...")
        for i, df in enumerate(all_team_data):
            all_team_data[i] = df.reset_index(drop=True)
        
        # Concatenate all data
        print("Concatenating all data...")
        df_raw = pd.concat(all_team_data, ignore_index=True, sort=False)
        
        # Remove duplicate columns if any
        print("Removing duplicate columns...")
        df_raw = df_raw.loc[:, ~df_raw.columns.duplicated()]
        
        # Save raw data
        output_file = 'notebooks/scrapper/data/historical_players_raw.csv'
        df_raw.to_csv(output_file, index=False)
        print(f"\n✓ Raw data saved: {output_file}")
        print(f"  Total records: {len(df_raw)}")
        print(f"  Total columns: {len(df_raw.columns)}")
        
        # Show statistics
        print(f"\n=== STATISTICS ===")
        print(f"Unique players: {df_raw['player'].nunique()}")
        print(f"Unique teams: {df_raw['Team'].nunique()}")
        print(f"Unique leagues: {df_raw['League'].nunique()}")
        
        print(f"\nRecords by season:")
        season_counts = df_raw['Season'].value_counts().sort_index()
        for season, count in season_counts.items():
            print(f"  {season}: {count} records")
        
        print(f"\nRecords by league:")
        league_counts = df_raw['League'].value_counts()
        for league, count in league_counts.head(10).items():
            print(f"  {league}: {count} records")
        
        print(f"\n=== SUCCESS ===")
        print("Historical data aggregation completed!")
        
    except Exception as e:
        print(f"\n✗ Error during aggregation: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

