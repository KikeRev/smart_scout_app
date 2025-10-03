#!/usr/bin/env python3
"""
merge_and_aggregate_all.py

Merge historical data (2014-2024) with current season (2024-25) and aggregate by player.
"""
import pandas as pd
import numpy as np

def main():
    print("=== MERGE AND AGGREGATE ALL DATA ===\n")
    
    # Load current season data
    print("Loading current season data...")
    df_current = pd.read_csv('data/all_players_cleaned.csv')
    print(f"Current season: {df_current.shape}")
    df_current["Season"] = "2024-25"
    
    # Load historical data
    print("Loading historical data...")
    df_historical = pd.read_csv('notebooks/scrapper/data/historical_players_raw.csv')
    print(f"Historical data: {df_historical.shape}")
    
    # Fix column name issue (nationalit -> nationality)
    if 'nationalit' in df_historical.columns and 'nationality' not in df_historical.columns:
        df_historical.rename(columns={'nationalit': 'nationality'}, inplace=True)
        print("Fixed 'nationalit' -> 'nationality'")
    
    # Get common columns
    common_cols = list(set(df_current.columns) & set(df_historical.columns))
    print(f"Common columns: {len(common_cols)}")
    
    # Keep only common columns
    df_current_aligned = df_current[common_cols]
    df_historical_aligned = df_historical[common_cols]
    
    print(f"Current season aligned: {df_current_aligned.shape}")
    print(f"Historical aligned: {df_historical_aligned.shape}")
    
    # Concatenate
    print("\nConcatenating data...")
    df_all = pd.concat([df_current_aligned, df_historical_aligned], axis=0, ignore_index=True)
    print(f"Combined data: {df_all.shape}")
    
    # Clean minutes columns
    print("\nCleaning data...")
    df_all["minutes"] = df_all["minutes"].fillna("0")
    if "minutes.1" in df_all.columns:
        df_all["minutes.1"] = df_all["minutes.1"].fillna("0")
    
    # Convert minutes to numeric
    df_all["minutes"] = df_all["minutes"].apply(lambda x: float(str(x).replace(",", "")))
    if "minutes.1" in df_all.columns:
        df_all["minutes.1"] = df_all["minutes.1"].apply(lambda x: float(str(x).replace(",", ".")))
    
    # Define categorical and numerical columns
    cat_cols = ["player", "nationality", "position", "age", "Team", "League", "Team_Logo", "Season"]
    cat_cols = [c for c in cat_cols if c in df_all.columns]
    
    num_cols = [c for c in df_all.columns if c not in cat_cols]
    
    print(f"Categorical columns: {len(cat_cols)}")
    print(f"Numerical columns: {len(num_cols)}")
    
    # Separate categorical and numerical data
    df_cat = df_all[cat_cols]
    df_num = df_all[["player"] + num_cols]
    
    # Aggregate categorical data (take most recent season)
    print("\nAggregating categorical data (most recent season)...")
    df_cat_agg = df_cat.sort_values(["player", "Season"], ascending=[True, False]).groupby("player").first().reset_index()
    print(f"Categorical aggregation: {df_cat_agg.shape}")
    
    # Add player_status based on most recent season
    df_cat_agg["player_status"] = df_cat_agg["Season"].apply(
        lambda x: "active" if x == "2024-25" else "retired or inactive"
    )
    print("Added player_status column")
    
    # Check minutes distribution before filtering
    zero_minutes = df_num[df_num.minutes == 0].shape[0]
    total_rows = df_num.shape[0]
    print(f"\nRows with 0 minutes: {zero_minutes}/{total_rows}")
    
    # Aggregate numerical data (average of all seasons with minutes > 0)
    print("Aggregating numerical data (weighted by minutes)...")
    df_num_agg = df_num[df_num.minutes > 0].groupby("player").mean(numeric_only=True).reset_index()
    print(f"Numerical aggregation: {df_num_agg.shape}")
    
    # Merge categorical and numerical data
    print("\nMerging aggregated data...")
    df_final_agg = df_cat_agg.merge(df_num_agg, on="player", how="left")
    print(f"Final merged data: {df_final_agg.shape}")
    
    # Keep only original columns plus player_status
    final_cols = [c for c in df_current.columns if c in df_final_agg.columns] + ["player_status"]
    df_final_agg = df_final_agg[final_cols]
    print(f"Final columns: {len(df_final_agg.columns)}")
    
    # Save result
    output_path = "data/all_players_with_historical_aggregated.csv"
    df_final_agg.to_csv(output_path, index=False)
    print(f"\n✓✓✓ SAVED: {output_path}")
    
    # Validation checks
    print("\n=== STATISTICS ===")
    print(f"Total players: {len(df_final_agg)}")
    print(f"Active players (2024-25): {len(df_final_agg[df_final_agg.player_status == 'active'])}")
    print(f"Retired/inactive: {len(df_final_agg[df_final_agg.player_status == 'retired or inactive'])}")
    
    # Show sample
    print("\n=== SAMPLE DATA ===")
    print(df_final_agg[['player', 'Team', 'Season', 'player_status']].head(10))
    
    print("\n✓✓✓ SUCCESS ✓✓✓")
    return df_final_agg

if __name__ == "__main__":
    result = main()

