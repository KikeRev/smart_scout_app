#!/usr/bin/env python3
"""
aggregate_historical_only.py

Script to aggregate ONLY the historical files (2014-15 to 2023-24) from historical_2014_2024 directory.

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
        
        # Save
        output_file = f"{data_dir}/ALL_HISTORICAL_RAW_2014_2024.csv"
        df_raw.to_csv(output_file, index=False)
        
        print(f"\n✓✓✓ SUCCESS ✓✓✓")
        print(f"File: {output_file}")
        print(f"Total records: {len(df_raw)}")
        print(f"Total columns: {len(df_raw.columns)}")
        print(f"Unique players: {df_raw['player'].nunique()}")
        
        # Show seasons
        print(f"\nRecords by season:")
        season_counts = df_raw['Season'].value_counts().sort_index()
        for season, count in season_counts.items():
            print(f"  {season}: {count} records")
        
        print(f"\nRecords by league:")
        league_counts = df_raw['League'].value_counts()
        for league, count in league_counts.items():
            print(f"  {league}: {count} records")
            
    except Exception as e:
        print(f"\n✗✗✗ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

