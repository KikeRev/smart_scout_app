import pandas as pd
import numpy as np

def normalize_position(pos):
    """
    Normalize position to one of the 4 main positions: GK, DF, MF, FW
    Priority: GK > FW > MF > DF
    """
    if not pos or pd.isna(pos):
        return ''
    pos = str(pos).upper().strip()
    
    # If has GK, it's GK
    if 'GK' in pos:
        return 'GK'
    # If has FW, it's FW
    elif 'FW' in pos:
        return 'FW'
    # If has MF, it's MF
    elif 'MF' in pos:
        return 'MF'
    # If has DF, it's DF
    elif 'DF' in pos:
        return 'DF'
    else:
        return ''

def calculate_birth_year(row):
    """
    Calculate birth year from age and season.
    Season format: "2024-25" -> use first year (2024)
    birth_year = season_year - age
    """
    try:
        if pd.isna(row['age']) or pd.isna(row['Season']):
            return None
        
        # Extract first year from season (e.g., "2024-25" -> 2024)
        season_year = int(str(row['Season']).split('-')[0])
        age = int(float(row['age']))
        birth_year = season_year - age
        
        return birth_year
    except:
        return None

def main():
    print("=== Loading data ===")
    # Load current season data
    df1 = pd.read_csv('data/all_players_cleaned.csv')
    print(f"Current season (all_players_cleaned): {df1.shape}")
    
    # Load historical data
    df2 = pd.read_csv('data/all_historical_raw_2014_2024.csv')
    df3 = pd.read_csv('data/historical_secondary_leagues_players_raw.csv')
    df2 = pd.concat([df2, df3], axis=0)
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
    
    # Calculate birth_year for player disambiguation
    print("\n=== Player disambiguation ===")
    df_final['birth_year'] = df_final.apply(calculate_birth_year, axis=1)
    print(f"Calculated birth_year for {df_final['birth_year'].notna().sum()} rows")
    
    # Normalize positions to 4 main categories
    df_final['position_normalized'] = df_final['position'].apply(normalize_position)
    print(f"Normalized positions: {df_final['position_normalized'].value_counts().to_dict()}")
    
    # Create unique player ID: player_birth_year
    df_final['player_uid'] = df_final.apply(
        lambda row: f"{row['player']}_{int(row['birth_year'])}" if pd.notna(row['birth_year']) else row['player'],
        axis=1
    )
    print(f"Created player_uid for disambiguation")
    
    # Show example: Rodri
    rodri_data = df_final[df_final.player == "Rodri"][['player', 'player_uid', 'birth_year', 'position', 'position_normalized', 'Team', 'Season', 'age']].sort_values(['player_uid', 'Season'])
    if len(rodri_data) > 0:
        print("\nExample - Rodri disambiguation:")
        print(rodri_data.head(20))
        print(f"\nUnique Rodri players: {rodri_data['player_uid'].nunique()}")
    
    # Clean minutes columns (as in notebook)
    df_final["minutes"] = df_final["minutes"].fillna("0")
    if "minutes.1" in df_final.columns:
        df_final["minutes.1"] = df_final["minutes.1"].fillna("0")
    
    # Convert minutes to numeric
    df_final["minutes"] = df_final["minutes"].apply(lambda x: float(str(x).replace(",", "")))
    if "minutes.1" in df_final.columns:
        df_final["minutes.1"] = df_final["minutes.1"].apply(lambda x: float(str(x).replace(",", ".")))
    
    print("Cleaned minutes columns")
    df_final = df_final.sort_values(["player_uid", "position_normalized", "Season"], ascending=[False, False, False])
    # Save result
    output_path = "data/all_players_plus_historic_data_non_aggregated_v3.csv"
    df_final.to_csv(output_path, index=False)
    print(f"Saved to: {output_path}")
    
    # Define categorical and numerical columns (updated to use player_uid)
    # birth_year is categorical (for identification), position_normalized is categorical (most recent)
    cat_cols = ["player", "player_uid", "birth_year", "nationality", "position", "position_normalized", "age", "Team", "League", "Team_Logo", "Season"]
    num_cols = ["player_uid"] + [c for c in df_final.columns if c not in cat_cols]
    
    print(f"Categorical columns: {len(cat_cols)}")
    print(f"Numerical columns: {len(num_cols)}")
    
    # Separate categorical and numerical data
    df_cat = df_final[cat_cols]
    df_num = df_final[num_cols]
    
    # Aggregate categorical data (take most recent season)
    # Use only player_uid for grouping (one player = one record)
    # Position is categorical: use the most recent one
    df_cat_agg = df_cat.sort_values(["player_uid", "Season"], ascending=[False, False]).groupby("player_uid").first().reset_index()
    print(f"Categorical aggregation: {df_cat_agg.shape}")
    
    # Verify no duplicates
    assert df_cat_agg.shape[0] == df_final.groupby("player_uid").ngroups, "Duplicate players found!"
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
    # Use only player_uid for grouping (average all seasons of the same player)
    df_num_agg = df_num[df_num.minutes > 0].groupby("player_uid").mean().reset_index()
    print(f"Numerical aggregation (minutes > 0): {df_num_agg.shape}")
    
    # Merge categorical and numerical data
    df_final_agg = df_cat_agg.merge(df_num_agg, on="player_uid", how="left")
    print(f"Final merged data: {df_final_agg.shape}")
    
    # Keep original columns plus new ones (player_uid, birth_year, position_normalized, player_status)
    original_cols = list(df1.columns) + ["player_uid", "birth_year", "position_normalized", "player_status"]
    # Filter to only existing columns
    original_cols = [c for c in original_cols if c in df_final_agg.columns]
    df_final_agg = df_final_agg[original_cols].sort_values(["player", "position_normalized"], ascending=[False, False])
    print(f"Final columns: {len(df_final_agg.columns)}")
    
    # Save result
    output_path = "data/all_players_plus_historic_data_aggregated_v3.csv"
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
    
    print("\n=== Sample data: Rodri disambiguation ===")
    print("Non-aggregated data:")
    print(df_final[df_final.player == "Rodri"][['player', 'player_uid', 'birth_year', 'position', 'position_normalized', 'Team', 'Season', 'age']].head(20))
    print("\nAggregated data:")
    print(df_final_agg[df_final_agg.player == "Rodri"][['player', 'player_uid', 'birth_year', 'position_normalized', 'Team', 'Season', 'age', 'player_status']].head(10))
    
    return df_final_agg

if __name__ == "__main__":
    result = main()
