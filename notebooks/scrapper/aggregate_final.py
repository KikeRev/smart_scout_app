import pandas as pd
import numpy as np

def normalize_position(pos):
    """Normalize position to one of the 4 main positions: GK, DF, MF, FW"""
    if not pos or pd.isna(pos):
        return ''
    pos = str(pos).upper().strip()
    
    if 'GK' in pos:
        return 'GK'
    elif 'FW' in pos:
        return 'FW'
    elif 'MF' in pos:
        return 'MF'
    elif 'DF' in pos:
        return 'DF'
    else:
        return ''

def calculate_birth_year(row):
    """Calculate birth year from age and season."""
    try:
        if pd.isna(row['age']) or pd.isna(row['Season']):
            return None
        
        season_year = int(row['Season'])
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
    
    # Remove matches column from historical data
    if "matches" in df2.columns:
        df2.drop("matches", axis=1, inplace=True)
        print("Removed 'matches' column from historical data")
    
    # Ensure both dataframes have same columns
    df2 = df2[df1.columns]
    print(f"Aligned columns. Historical data shape: {df2.shape}")
    
    # Concatenate dataframes
    df_final = pd.concat([df1, df2], axis=0)
    print(f"Concatenated data: {df_final.shape}")
    
    # STEP 1: Normalize Season to int
    print("\n=== Step 1: Normalizing Season column ===")
    df_final['Season'] = df_final['Season'].apply(lambda x: int(str(x).split('-')[0]))
    print(f"Season normalized to: {sorted(df_final['Season'].unique())}")
    
    # STEP 2: Remove exact duplicates (player, Team, Season)
    print("\n=== Step 2: Removing duplicates ===")
    before_dedup = len(df_final)
    df_final = df_final.drop_duplicates(subset=['player', 'Team', 'Season'], keep='first')
    after_dedup = len(df_final)
    print(f"Removed {before_dedup - after_dedup} duplicate rows")
    
    # STEP 3: Fix age inconsistencies with iterative window operation (cascade corrections)
    print("\n=== Step 3: Fixing age inconsistencies (iterative cascade) ===")
    df_final = df_final.sort_values(['player', 'Team', 'Season']).reset_index(drop=True)
    
    # Iterative correction until no more changes (max 5 iterations to avoid infinite loop)
    total_corrections = 0
    
    for iteration in range(5):
        # Recalculate window for this iteration
        df_final['Season_prev'] = df_final.groupby(['player', 'Team'])['Season'].shift(1)
        df_final['age_prev'] = df_final.groupby(['player', 'Team'])['age'].shift(1)
        df_final['season_diff'] = df_final['Season'] - df_final['Season_prev']
        df_final['expected_age'] = df_final['age_prev'] + df_final['season_diff']
        
        # Apply corrections
        corrections_this_iter = 0
        for idx, row in df_final.iterrows():
            if pd.notna(row['expected_age']) and pd.notna(row['age']):
                if row['season_diff'] >= 1 and row['age'] != row['expected_age']:
                    df_final.at[idx, 'age'] = row['expected_age']
                    corrections_this_iter += 1
        
        total_corrections += corrections_this_iter
        print(f"Iteration {iteration + 1}: {corrections_this_iter} corrections")
        
        # Stop if no more corrections needed
        if corrections_this_iter == 0:
            break
        
        # Drop temp columns for next iteration
        df_final.drop(['Season_prev', 'age_prev', 'season_diff', 'expected_age'], axis=1, inplace=True)
    
    print(f"\n✅ Total corrections: {total_corrections}")
    
    # Final cleanup of temp columns (in case loop ended with them)
    for col in ['Season_prev', 'age_prev', 'season_diff', 'expected_age']:
        if col in df_final.columns:
            df_final.drop(col, axis=1, inplace=True)
    
    # Debug: Check Marcelo Ortiz AFTER all corrections
    marcelo_after = df_final[df_final['player'] == 'Marcelo Ortiz'][['player', 'Team', 'Season', 'age']].sort_values(['Team', 'Season'])
    if len(marcelo_after) > 0:
        print("\nDEBUG - Marcelo Ortiz AFTER all corrections:")
        print(marcelo_after.to_string(index=False))
    
    # STEP 4: Calculate birth_year
    print("\n=== Step 4: Player disambiguation ===")
    df_final['birth_year'] = df_final.apply(calculate_birth_year, axis=1)
    print(f"Calculated birth_year for {df_final['birth_year'].notna().sum()} rows")
    
    # STEP 5: Normalize positions
    df_final['position_normalized'] = df_final['position'].apply(normalize_position)
    print(f"Normalized positions: {df_final['position_normalized'].value_counts().to_dict()}")
    
    # STEP 6: Create player_uid
    df_final['player_uid'] = df_final.apply(
        lambda row: f"{row['player']}_{int(row['birth_year'])}" if pd.notna(row['birth_year']) else row['player'],
        axis=1
    )
    print(f"Created player_uid for disambiguation")
    
    # Verification examples
    print("\n=== Verification Examples ===")
    
    # Rodri
    rodri = df_final[df_final.player == "Rodri"][['player', 'player_uid', 'birth_year', 'Team', 'Season', 'age']].sort_values(['player_uid', 'Season']).head(20)
    print(f"\nRodri: {df_final[df_final.player == 'Rodri']['player_uid'].nunique()} unique UIDs")
    print(rodri)
    
    # Marlon Freitas
    marlon = df_final[df_final.player == "Marlon Freitas"][['player', 'player_uid', 'birth_year', 'Team', 'Season', 'age']].sort_values(['player_uid', 'Season'])
    print(f"\nMarlon Freitas: {marlon['player_uid'].nunique()} unique UIDs")
    print(marlon)
    
    # Toni Kroos
    kroos = df_final[df_final.player == "Toni Kroos"][['player', 'player_uid', 'birth_year', 'Team', 'Season', 'age']].sort_values(['player_uid', 'Season'])
    print(f"\nToni Kroos: {kroos['player_uid'].nunique()} unique UIDs")
    print(kroos)
    
    # Clean minutes columns
    print("\n=== Cleaning minutes columns ===")
    df_final["minutes"] = df_final["minutes"].fillna("0")
    if "minutes.1" in df_final.columns:
        df_final["minutes.1"] = df_final["minutes.1"].fillna("0")
    
    df_final["minutes"] = df_final["minutes"].apply(lambda x: float(str(x).replace(",", "")))
    if "minutes.1" in df_final.columns:
        df_final["minutes.1"] = df_final["minutes.1"].apply(lambda x: float(str(x).replace(",", ".")))
    
    df_final = df_final.sort_values(["player_uid", "position_normalized", "Season"], ascending=[False, False, False])
    
    # Save non-aggregated
    output_path = "data/all_players_plus_historic_data_non_aggregated_v3_5.csv"
    df_final.to_csv(output_path, index=False)
    print(f"Saved to: {output_path}")
    
    # AGGREGATION
    print("\n=== Aggregation ===")
    cat_cols = ["player", "player_uid", "birth_year", "nationality", "position", "position_normalized", "age", "Team", "League", "Team_Logo", "Season"]
    num_cols = ["player_uid"] + [c for c in df_final.columns if c not in cat_cols]
    
    df_cat = df_final[cat_cols]
    df_num = df_final[num_cols]
    
    # Aggregate categorical (most recent season)
    df_cat_agg = df_cat.sort_values(["player_uid", "Season"], ascending=[False, False]).groupby("player_uid").first().reset_index()
    print(f"Categorical aggregation: {df_cat_agg.shape}")
    
    # Verify no duplicates
    assert df_cat_agg.shape[0] == df_final.groupby("player_uid").ngroups, "Duplicate players found!"
    print("✓ No duplicate players")
    
    # Add player_status
    df_cat_agg["player_status"] = df_cat_agg["Season"].apply(
        lambda x: "active" if x == 2024 else "retired or inactive"
    )
    print("Added player_status column")
    
    # Aggregate numerical (average with minutes > 0)
    df_num_agg = df_num[df_num.minutes > 0].groupby("player_uid").mean().reset_index()
    print(f"Numerical aggregation: {df_num_agg.shape}")
    
    # Merge
    df_final_agg = df_cat_agg.merge(df_num_agg, on="player_uid", how="left")
    print(f"Final merged data: {df_final_agg.shape}")
    
    # Save aggregated
    output_path = "data/all_players_plus_historic_data_aggregated_v3_5.csv"
    df_final_agg.to_csv(output_path, index=False)
    print(f"Saved to: {output_path}")
    
    print("\n=== Validation ===")
    print(f"Total players: {len(df_final_agg)}")
    print(f"Active players: {len(df_final_agg[df_final_agg.player_status == 'active'])}")
    print(f"Retired/inactive: {len(df_final_agg[df_final_agg.player_status == 'retired or inactive'])}")
    
    return df_final_agg

if __name__ == "__main__":
    result = main()

