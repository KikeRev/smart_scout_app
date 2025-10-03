#!/usr/bin/env python3
"""
aggregate_historical_only.py

Script to aggregate historical files (2014-15 to 2023-24) from historical_2014_2024 directory
and add the current season (2024-25) to create a complete historical dataset.

Usage:
    python aggregate_historical_only.py
"""
import pandas as pd
import glob
import os

def main():
    """Main aggregation function."""
    print("=== AGGREGATE HISTORICAL FILES (2014-2024) ===\n")
    
    # Load files from historical directory only
    data_dir = "notebooks/scrapper/data/historical_2014_2024"
    pattern = f"{data_dir}/*.csv"
    
    csv_files = glob.glob(pattern)
    # Exclude aggregate files
    csv_files = [f for f in csv_files if 'ALL_HISTORICAL' not in f and 'Premier_League_2014_15' not in os.path.basename(f)]
    
    print(f"Found {len(csv_files)} historical files")
    
    all_dfs = []
    for file in sorted(csv_files):
        try:
            df = pd.read_csv(file)
            if not df.empty:
                all_dfs.append(df)
                print(f"  ✓ {os.path.basename(file)}: {len(df)} records")
        except Exception as e:
            print(f"  ✗ {os.path.basename(file)}: {e}")
    
    if not all_dfs:
        print("No data found!")
        return
    
    print(f"\n=== PROCESSING {len(all_dfs)} FILES ===")
    
    try:
        # Reset indexes
        for i, df in enumerate(all_dfs):
            all_dfs[i] = df.reset_index(drop=True)
        
        # Concatenate with join='outer' for different column sets
        df_raw = pd.concat(all_dfs, ignore_index=True, sort=False, join='outer')
        
        # Remove duplicate columns
        df_raw = df_raw.loc[:, ~df_raw.columns.duplicated()]
        
        print(f"\nHistorical data (2014-2024): {len(df_raw)} records")
        
        # === Add current season (2024-25) ===
        print(f"\n=== ADDING CURRENT SEASON (2024-25) ===")
        current_season_file = "data/all_players_cleaned.csv"
        
        if os.path.exists(current_season_file):
            df_current = pd.read_csv(current_season_file)
            df_current['Season'] = '2024-25'
            
            # Rename nationality column if needed to match historical
            if 'nationalit' in df_raw.columns and 'nationality' in df_current.columns:
                df_raw.rename(columns={'nationalit': 'nationality'}, inplace=True)
            
            print(f"Current season (2024-25): {len(df_current)} records")
            
            # Align columns - use outer join
            all_columns = sorted(set(df_raw.columns) | set(df_current.columns))
            df_raw_aligned = df_raw.reindex(columns=all_columns)
            df_current_aligned = df_current.reindex(columns=all_columns)
            
            # Concatenate
            df_complete = pd.concat([df_raw_aligned, df_current_aligned], ignore_index=True)
            
            print(f"Complete historical data: {len(df_complete)} records")
        else:
            print(f"Warning: Current season file not found at {current_season_file}")
            print(f"Proceeding with historical data only (2014-2024)")
            df_complete = df_raw
        
        # Save complete historical file
        output_file = "notebooks/scrapper/data/historical_players_raw.csv"
        df_complete.to_csv(output_file, index=False)
        
        print(f"\n✓✓✓ SUCCESS ✓✓✓")
        print(f"File: {output_file}")
        print(f"Total records: {len(df_complete)}")
        print(f"Total columns: {len(df_complete.columns)}")
        print(f"Unique players: {df_complete['player'].nunique()}")
        
        # Show seasons
        print(f"\nRecords by season:")
        season_counts = df_complete['Season'].value_counts().sort_index()
        for season, count in season_counts.items():
            print(f"  {season}: {count} records")
        
        print(f"\nRecords by league:")
        league_counts = df_complete['League'].value_counts()
        for league, count in league_counts.items():
            print(f"  {league}: {count} records")
            
    except Exception as e:
        print(f"\n✗✗✗ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

