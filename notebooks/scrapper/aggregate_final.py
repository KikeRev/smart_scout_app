import pandas as pd
import numpy as np

def main():
    print("=== Loading data ===")
    # Load current season data
    df1 = pd.read_csv('data/all_players_cleaned.csv')
    print(f"Current season (all_players_cleaned): {df1.shape}")
    
    # Load historical data
    df2 = pd.read_csv('data/historical_players_raw.csv')
    print(f"Historical data: {df2.shape}")
    
    # Add season column to current data
    df1["Season"] = "2024-25"
    print("Added Season column to current data")
    
    # Remove matches column from historical data (as in notebook)
    if "matches" in df2.columns:
        df2.drop("matches", axis=1, inplace=True)
        print("Removed 'matches' column from historical data")
    
    # Ensure both dataframes have same columns
    df2 = df2[df1.columns]
    print(f"Aligned columns. Historical data shape: {df2.shape}")
    
    # Concatenate dataframes
    df_final = pd.concat([df1, df2], axis=0)
    print(f"Concatenated data: {df_final.shape}")
    
    # Clean minutes columns (as in notebook)
    df_final["minutes"] = df_final["minutes"].fillna("0")
    if "minutes.1" in df_final.columns:
        df_final["minutes.1"] = df_final["minutes.1"].fillna("0")
    
    # Convert minutes to numeric
    df_final["minutes"] = df_final["minutes"].apply(lambda x: float(str(x).replace(",", "")))
    if "minutes.1" in df_final.columns:
        df_final["minutes.1"] = df_final["minutes.1"].apply(lambda x: float(str(x).replace(",", ".")))
    
    print("Cleaned minutes columns")
    # Save result
    output_path = "data/all_players_plus_historic_data_non_aggregated_v2.csv"
    df_final.to_csv(output_path, index=False)
    print(f"Saved to: {output_path}")
    
    # Define categorical and numerical columns (as in notebook)
    cat_cols = ["player", "nationality", "position", "age", "Team", "League", "Team_Logo", "Season"]
    num_cols = ["player"] + [c for c in df_final.columns if c not in cat_cols]
    
    print(f"Categorical columns: {len(cat_cols)}")
    print(f"Numerical columns: {len(num_cols)}")
    
    # Separate categorical and numerical data
    df_cat = df_final[cat_cols]
    df_num = df_final[num_cols]
    
    # Aggregate categorical data (take most recent season)
    df_cat_agg = df_cat.sort_values(["player", "Season"], ascending=[False, False]).groupby("player").first().reset_index()
    print(f"Categorical aggregation: {df_cat_agg.shape}")
    
    # Verify no duplicates
    assert df_cat_agg.shape[0] == df_final["player"].nunique(), "Duplicate players found!"
    print("✓ No duplicate players")
    
    # Add player_status based on most recent season
    df_cat_agg["player_status"] = df_cat_agg["Season"].apply(
        lambda x: "active" if x == "2024-25" else "retired or inactive"
    )
    print("Added player_status column")
    
    # Check minutes distribution before filtering
    zero_minutes = df_num[df_num.minutes == 0].shape[0]
    total_rows = df_num.shape[0]
    print(f"Rows with 0 minutes: {zero_minutes}/{total_rows}")
    
    # Aggregate numerical data (average of all seasons with minutes > 0)
    df_num_agg = df_num[df_num.minutes > 0].groupby("player").mean().reset_index()
    print(f"Numerical aggregation (minutes > 0): {df_num_agg.shape}")
    
    # Merge categorical and numerical data
    df_final_agg = df_cat_agg.merge(df_num_agg, on="player", how="left")
    print(f"Final merged data: {df_final_agg.shape}")
    
    # Keep only original columns plus player_status
    original_cols = list(df1.columns) + ["player_status"]
    df_final_agg = df_final_agg[original_cols]
    print(f"Final columns: {len(df_final_agg.columns)}")
    
    # Save result
    output_path = "data/all_players_plus_historic_data_aggregated_v2.csv"
    df_final_agg.to_csv(output_path, index=False)
    print(f"Saved to: {output_path}")
    
    # Validation checks
    print("\n=== Validation ===")
    print(f"Total players: {len(df_final_agg)}")
    print(f"Active players: {len(df_final_agg[df_final_agg.player_status == 'active'])}")
    print(f"Retired/inactive: {len(df_final_agg[df_final_agg.player_status == 'retired or inactive'])}")
    
    # Real Madrid check
    rm = df_final_agg[df_final_agg.Team == "Real Madrid"]
    print(f"Real Madrid players: {len(rm)}")
    if len(rm) > 0:
        print(f"  - Active: {len(rm[rm.player_status == 'active'])}")
        print(f"  - Retired: {len(rm[rm.player_status == 'retired or inactive'])}")
    
    print("\n=== Sample data ===")
    print(df_final_agg[['player', 'Team', 'Season', 'player_status']].head(10))
    
    return df_final_agg

if __name__ == "__main__":
    result = main()
