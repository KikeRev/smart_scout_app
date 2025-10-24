#!/usr/bin/env python3
"""
🎯 Calculate Ratings to CSV - Generates ratings and saves to CSV

This script calculates FIFA-style ratings for all players and saves them to a CSV file.
The CSV can then be imported using seed_and_ingest.py with --ratings-csv.

Usage:
    python scripts/calculate_ratings_to_csv.py [--output ratings.csv] [--verbose]
"""

import os
import sys
import argparse
import pandas as pd
from pathlib import Path

# Add root directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlalchemy as sa
from sqlalchemy import orm
from tqdm import tqdm

from apps.ingestion.seed_and_ingest import Player, get_engine
from scripts.calculate_player_rating import calculate_rating

# Importar constantes y funciones del script original
from scripts.calculate_player_rating import (
    LEAGUE_BASE_RATINGS, POSITION_WEIGHTS, SUFFICIENT_SAMPLE_MINUTES,
    weighted_stat_by_minutes, normalize_stat_percentile
)

def calculate_rating_from_row(player_row: pd.Series, league_avg_data: dict, league_all_stats: dict) -> dict:
    """
    Calcula rating a partir de una fila de DataFrame con todos los datos del jugador.
    
    Args:
        player_row: pd.Series con todos los datos del jugador
        league_avg_data: dict con promedios de la liga para la posición
        league_all_stats: dict con todas las stats de la liga para percentiles
    
    Returns:
        dict con todos los datos del rating calculado
    """
    # 1. Obtener datos básicos del jugador
    player_id = player_row['id']
    player_uid = player_row['player_uid']
    player_name = player_row['full_name']
    position = player_row['position']
    league = player_row['league']
    club = player_row['club']
    
    # Asegurar que los minutos estén en formato numérico
    try:
        minutes = float(player_row['minutes']) if player_row['minutes'] is not None else 0.0
        minutes_90s = float(player_row['minutes_90s']) if player_row['minutes_90s'] is not None and player_row['minutes_90s'] > 0 else 1.0
    except (ValueError, TypeError):
        # Si hay error en la conversión, usar valores por defecto
        minutes = 0.0
        minutes_90s = 1.0
    
    # 2. Calcular stats per 90 (con validación numérica)
    def safe_float(value, default=0.0):
        """Convierte valor a float de forma segura"""
        try:
            return float(value) if value is not None else default
        except (ValueError, TypeError):
            return default
    
    goals_per90 = safe_float(player_row['goals']) / minutes_90s
    assists_per90 = safe_float(player_row['assists']) / minutes_90s
    xg_per90 = safe_float(player_row['expected_goals']) / minutes_90s
    xa_per90 = safe_float(player_row['expected_assists']) / minutes_90s
    prog_carries_per90 = safe_float(player_row['progressive_carries']) / minutes_90s
    prog_passes_per90 = safe_float(player_row['progressive_passes']) / minutes_90s
    passes_pct = safe_float(player_row['passes_pct'], 0.0)
    tackles_won_per90 = safe_float(player_row['tackles_won']) / minutes_90s
    interceptions_per90 = safe_float(player_row['interceptions']) / minutes_90s
    blocks_per90 = safe_float(player_row['blocks']) / minutes_90s
    clearances_per90 = safe_float(player_row['clearances']) / minutes_90s
    
    # Stats de portero
    gk_goals_against_per90 = safe_float(player_row['gk_goals_against']) / minutes_90s
    gk_psxg_per90 = safe_float(player_row['gk_psxg']) / minutes_90s
    
    # 3. Aplicar regresión a la media usando datos de la liga
    goals_w = weighted_stat_by_minutes(goals_per90, league_avg_data['avg_goals_per90'], minutes)
    assists_w = weighted_stat_by_minutes(assists_per90, league_avg_data['avg_assists_per90'], minutes)
    xg_w = weighted_stat_by_minutes(xg_per90, league_avg_data['avg_xg_per90'], minutes)
    xa_w = weighted_stat_by_minutes(xa_per90, league_avg_data['avg_xa_per90'], minutes)
    prog_carries_w = weighted_stat_by_minutes(prog_carries_per90, league_avg_data['avg_prog_carries_per90'], minutes)
    prog_passes_w = weighted_stat_by_minutes(prog_passes_per90, league_avg_data['avg_prog_passes_per90'], minutes)
    tackles_won_w = weighted_stat_by_minutes(tackles_won_per90, league_avg_data['avg_tackles_won_per90'], minutes)
    interceptions_w = weighted_stat_by_minutes(interceptions_per90, league_avg_data['avg_interceptions_per90'], minutes)
    blocks_w = weighted_stat_by_minutes(blocks_per90, league_avg_data['avg_blocks_per90'], minutes)
    clearances_w = weighted_stat_by_minutes(clearances_per90, league_avg_data['avg_clearances_per90'], minutes)
    
    # Regresión para stats de portero con blending específico
    if position == 'GK':
        gk_goals_against_w = weighted_stat_by_minutes(gk_goals_against_per90, league_avg_data['avg_gk_goals_against_per90'] or 1.0, minutes, is_gkp=True)
        gk_psxg_w = weighted_stat_by_minutes(gk_psxg_per90, league_avg_data['avg_gk_psxg_per90'] or 1.0, minutes, is_gkp=True)
    else:
        gk_goals_against_w = 0
        gk_psxg_w = 0
    
    # 4. Normalizar usando percentiles (0-100)
    goals_norm = normalize_stat_percentile(goals_w, league_all_stats['goals_values'])
    assists_norm = normalize_stat_percentile(assists_w, league_all_stats['assists_values'])
    xg_norm = normalize_stat_percentile(xg_w, league_all_stats['xg_values'])
    xa_norm = normalize_stat_percentile(xa_w, league_all_stats['xa_values'])
    prog_carries_norm = normalize_stat_percentile(prog_carries_w, league_all_stats['prog_carries_values'])
    prog_passes_norm = normalize_stat_percentile(prog_passes_w, league_all_stats['prog_passes_values'])
    passes_pct_norm = normalize_stat_percentile(passes_pct, league_all_stats['passes_pct_values'])
    tackles_won_norm = normalize_stat_percentile(tackles_won_w, league_all_stats['tackles_won_values'])
    interceptions_norm = normalize_stat_percentile(interceptions_w, league_all_stats['interceptions_values'])
    blocks_norm = normalize_stat_percentile(blocks_w, league_all_stats['blocks_values'])
    clearances_norm = normalize_stat_percentile(clearances_w, league_all_stats['clearances_values'])
    
    # Normalizar stats de portero (inverso: menos es mejor) - solo para porteros
    if position == 'GK':
        gk_goals_against_norm = normalize_stat_percentile(gk_goals_against_w, league_all_stats['gk_goals_against_values'], inverse=True)
        gk_psxg_norm = normalize_stat_percentile(gk_psxg_w, league_all_stats['gk_psxg_values'], inverse=True)
    else:
        gk_goals_against_norm = 0
        gk_psxg_norm = 0
    
    # 5. Calcular 6 atributos
    ATT = round(
        goals_norm * 0.30 +
        xg_norm * 0.25 +
        xa_norm * 0.25 +
        assists_norm * 0.20
    )
    
    PLY = round(
        passes_pct_norm * 0.30 +
        prog_passes_norm * 0.30 +
        xa_norm * 0.25 +
        65 * 0.15  # Piso más alto
    )
    
    DEF = round(
        tackles_won_norm * 0.25 +
        interceptions_norm * 0.25 +
        blocks_norm * 0.15 +
        clearances_norm * 0.25 +
        72 * 0.10  # Piso más alto para profesionales
    )
    
    CTR = round(
        prog_carries_norm * 0.35 +
        65 * 0.25 +  # Piso más alto
        prog_passes_norm * 0.25 +
        passes_pct_norm * 0.15
    )
    
    # Obtener el base rating de la liga para PHY y GKP
    league_base_rating = LEAGUE_BASE_RATINGS.get(league, LEAGUE_BASE_RATINGS['default'])
    
    # PHY - Físico (promedio de base de liga + performance)
    phy_performance = (
        tackles_won_norm * 0.30 +
        prog_carries_norm * 0.30 +
        clearances_norm * 0.20 +
        blocks_norm * 0.20
    )
    PHY = round((league_base_rating + phy_performance) / 2)
    
    # Atributo GKP (solo para porteros, promedio de base de liga + performance)
    if position == 'GK':
        gkp_performance = (
            gk_goals_against_norm * 0.40 +  # Lo más importante: pocos goles
            gk_psxg_norm * 0.35 +            # Calidad de paradas (vs xG)
            gk_psxg_norm * 0.25              # Calidad de paradas por disparo
        )
        GKP = round((league_base_rating + gkp_performance) / 2)
    else:
        GKP = league_base_rating / 2
    
    # 6. Aplicar penalización por minutos a todos los atributos
    def get_minutes_penalty(minutes_played):
        """Aplica penalización basada en minutos jugados"""
        if minutes_played >= 1500:
            return 1.00  # Sin penalización
        elif minutes_played >= 1200:
            return 0.95
        elif minutes_played >= 900:
            return 0.90
        elif minutes_played >= 600:
            return 0.85
        elif minutes_played >= 300:
            return 0.80
        elif minutes_played >= 100:
            return 0.75
        else:
            return 0.70  # Máxima penalización
    
    penalty_factor = get_minutes_penalty(minutes)
    
    # Aplicar penalización a todos los atributos
    ATT = round(ATT * penalty_factor)
    PLY = round(PLY * penalty_factor)
    DEF = round(DEF * penalty_factor)
    CTR = round(CTR * penalty_factor)
    PHY = round(PHY * penalty_factor)
    GKP = round(GKP * penalty_factor)
    
    # 7. Calcular Performance Rating
    if position not in POSITION_WEIGHTS:
        position = 'MF'  # Default
    
    weights = POSITION_WEIGHTS[position]
    
    performance_rating = (
        ATT * weights['ATT'] +
        PLY * weights['PLY'] +
        DEF * weights['DEF'] +
        CTR * weights['CTR'] +
        PHY * weights['PHY'] +
        GKP * weights['GKP']
    )
    
    # 8. Calcular Overall Rating (60-40 liga base vs performance)
    league_weight = 0.60
    perf_weight = 0.40
    overall_rating = (league_base_rating * league_weight) + (performance_rating * perf_weight)
    
    # 9. Devolver diccionario con todos los datos calculados
    return {
        'player_id': player_id,
        'player_uid': player_uid,
        'player_name': player_name,
        'overall_rating': round(overall_rating),
        'league_base_rating': league_base_rating,
        'performance_rating': round(performance_rating, 1),
        'att': round(ATT, 0),
        'ply': round(PLY, 0),
        'def_rating': round(DEF, 0),
        'ctr': round(CTR, 0),
        'phy': round(PHY, 0),
        'gkp': round(GKP, 0),
        'season': '2024',  # TODO: obtener de la base de datos
        'position': position,
        'minutes_played': minutes,
        'league': league,
        'club': club
    }

def calculate_ratings_to_csv(
    engine: sa.Engine,
    output_file: str = "data/player_ratings.csv",
    verbose: bool = False
):
    """
    Calculates ratings for all players and saves them to CSV.
    
    Args:
        engine: SQLAlchemy engine
        output_file: Path to output CSV file
        verbose: Show detailed progress
    """
    print("📊 Loading players data...")
    
    # Load all players data into DataFrame with a single query
    query = """
    SELECT 
        id, full_name, player_uid, position, club, league, age,
        minutes, minutes_90s,
        goals, assists, 
        expected_goals, expected_assists,
        progressive_carries, progressive_passes, progressive_passes_received,
        passes_completed, passes, passes_pct,
        tackles, tackles_won, interceptions, blocks, clearances,
        challenges, challenges_lost, errors,
        gk_goals_against, gk_psxg
    FROM players 
    ORDER BY id
    """
    
    df_players = pd.read_sql(query, engine)
    
    if df_players.empty:
        print("⚠️  No players found to process")
        return
    
    print(f"📊 Processing {len(df_players)} players...")
    
    # Pre-calculate league averages and stats for all league-position combinations
    print("📊 Pre-calculating league averages...")
    league_data = {}
    
    # Get unique league-position combinations
    unique_combinations = df_players[['league', 'position']].drop_duplicates()
    
    for _, combo in unique_combinations.iterrows():
        league = combo['league']
        position = combo['position']
        key = f"{league}_{position}"
        
        # Get league averages for this combination
        avg_query = f"""
        SELECT 
            AVG(goals / NULLIF(minutes_90s, 0)) as avg_goals_per90,
            AVG(assists / NULLIF(minutes_90s, 0)) as avg_assists_per90,
            AVG(expected_goals / NULLIF(minutes_90s, 0)) as avg_xg_per90,
            AVG(expected_assists / NULLIF(minutes_90s, 0)) as avg_xa_per90,
            AVG(progressive_carries / NULLIF(minutes_90s, 0)) as avg_prog_carries_per90,
            AVG(progressive_passes / NULLIF(minutes_90s, 0)) as avg_prog_passes_per90,
            AVG(passes_pct) as avg_passes_pct,
            AVG(tackles_won / NULLIF(minutes_90s, 0)) as avg_tackles_won_per90,
            AVG(interceptions / NULLIF(minutes_90s, 0)) as avg_interceptions_per90,
            AVG(blocks / NULLIF(minutes_90s, 0)) as avg_blocks_per90,
            AVG(clearances / NULLIF(minutes_90s, 0)) as avg_clearances_per90,
            AVG(gk_goals_against / NULLIF(minutes_90s, 0)) as avg_gk_goals_against_per90,
            AVG(gk_psxg / NULLIF(minutes_90s, 0)) as avg_gk_psxg_per90
        FROM players
        WHERE league = '{league}' 
          AND position = '{position}'
          AND minutes >= 90;
        """
        
        avg_result = pd.read_sql(avg_query, engine).iloc[0].to_dict()
        
        # Get all stats for percentiles
        all_stats_query = f"""
        SELECT 
            goals / NULLIF(minutes_90s, 0) as goals_per90,
            assists / NULLIF(minutes_90s, 0) as assists_per90,
            expected_goals / NULLIF(minutes_90s, 0) as xg_per90,
            expected_assists / NULLIF(minutes_90s, 0) as xa_per90,
            progressive_carries / NULLIF(minutes_90s, 0) as prog_carries_per90,
            progressive_passes / NULLIF(minutes_90s, 0) as prog_passes_per90,
            passes_pct,
            tackles_won / NULLIF(minutes_90s, 0) as tackles_won_per90,
            interceptions / NULLIF(minutes_90s, 0) as interceptions_per90,
            blocks / NULLIF(minutes_90s, 0) as blocks_per90,
            clearances / NULLIF(minutes_90s, 0) as clearances_per90,
            gk_goals_against / NULLIF(minutes_90s, 0) as gk_goals_against_per90,
            gk_psxg / NULLIF(minutes_90s, 0) as gk_psxg_per90
        FROM players
        WHERE league = '{league}' 
          AND position = '{position}'
          AND minutes >= 90
          AND minutes_90s > 0;
        """
        
        all_stats_df = pd.read_sql(all_stats_query, engine)
        
        # Convert to lists for percentile calculations
        all_stats = {
            'goals_values': all_stats_df['goals_per90'].dropna().tolist(),
            'assists_values': all_stats_df['assists_per90'].dropna().tolist(),
            'xg_values': all_stats_df['xg_per90'].dropna().tolist(),
            'xa_values': all_stats_df['xa_per90'].dropna().tolist(),
            'prog_carries_values': all_stats_df['prog_carries_per90'].dropna().tolist(),
            'prog_passes_values': all_stats_df['prog_passes_per90'].dropna().tolist(),
            'passes_pct_values': all_stats_df['passes_pct'].dropna().tolist(),
            'tackles_won_values': all_stats_df['tackles_won_per90'].dropna().tolist(),
            'interceptions_values': all_stats_df['interceptions_per90'].dropna().tolist(),
            'blocks_values': all_stats_df['blocks_per90'].dropna().tolist(),
            'clearances_values': all_stats_df['clearances_per90'].dropna().tolist(),
            'gk_goals_against_values': all_stats_df['gk_goals_against_per90'].dropna().tolist(),
            'gk_psxg_values': all_stats_df['gk_psxg_per90'].dropna().tolist(),
        }
        
        league_data[key] = {
            'avg': avg_result,
            'all_stats': all_stats
        }
    
    print(f"📊 Pre-calculated data for {len(league_data)} league-position combinations")
    
    # Process players and collect results
    ratings_data = []
    processed = 0
    skipped = 0
    errors = 0
    
    iterator = tqdm(df_players.iterrows(), total=len(df_players), desc="Calculating ratings", unit="player", disable=False)
    
    for idx, player in iterator:
        try:
            # Get league data for this player
            key = f"{player['league']}_{player['position']}"
            if key not in league_data:
                skipped += 1
                continue
                
            league_avg_data = league_data[key]['avg']
            league_all_stats = league_data[key]['all_stats']
            
            # Calculate rating using the new function
            rating_data = calculate_rating_from_row(player, league_avg_data, league_all_stats)
            
            if rating_data is None:
                skipped += 1
                continue
                
            ratings_data.append(rating_data)
            processed += 1
            
        except Exception as e:
            errors += 1
            continue
    
    print(f"\n✅ Calculation completed:")
    print(f"   - Processed: {processed}")
    print(f"   - Skipped: {skipped}")
    print(f"   - Errors: {errors}")
    
    if not ratings_data:
        print("⚠️  No ratings calculated")
        return
    
    # Create DataFrame and save to CSV
    df = pd.DataFrame(ratings_data)
    
    # Ensure output directory exists
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save to CSV
    df.to_csv(output_file, index=False)
    print(f"💾 Ratings saved to: {output_file}")
    print(f"📊 CSV contains {len(df)} ratings")
    
    # Show sample of data (only if verbose)
    if verbose:
        print(f"\n📋 Sample of calculated ratings:")
        print(df[['player_name', 'player_uid', 'overall_rating', 'position', 'league']].head(10).to_string(index=False))


def main():
    parser = argparse.ArgumentParser(
        description="Calculate FIFA-style ratings and save to CSV"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/player_ratings.csv",
        help="Output CSV file path (default: data/player_ratings.csv)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed progress"
    )
    
    args = parser.parse_args()
    
    # Create engine
    engine = get_engine()
    
    # Calculate ratings and save to CSV
    calculate_ratings_to_csv(
        engine=engine,
        output_file=args.output,
        verbose=args.verbose
    )

if __name__ == "__main__":
    main()
