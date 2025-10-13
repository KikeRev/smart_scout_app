#!/usr/bin/env python3
"""
🎯 Rating Calculator - Centralized logic for FIFA-style player ratings

This module contains all the logic for calculating player ratings.
Used both in mass calculation scripts and data ingestion.

Based on the system developed in scripts/calculate_player_rating.py
"""

import sqlalchemy as sa
from sqlalchemy import text
from typing import Dict, List, Tuple, Optional
import statistics

# ============================================================================
# CONFIGURATION
# ============================================================================

# League coefficients (Base Rating)
LEAGUE_BASE_RATINGS = {
    'Premier League': 92,
    'La Liga': 90,
    'Serie A': 88,
    'Bundesliga': 88,
    'Ligue 1': 88,
    'Eredivisie': 79,
    'Primeira Liga': 79,
    'Belgian Pro League': 75,
    'default': 70,
}

# Position weights
POSITION_WEIGHTS = {
    'GK': {'ATT': 0.00, 'PLY': 0.00, 'DEF': 0.10, 'CTR': 0.00, 'PHY': 0.10, 'GKP': 0.80},
    'DF': {'ATT': 0.10, 'PLY': 0.20, 'DEF': 0.35, 'CTR': 0.10, 'PHY': 0.25, 'GKP': 0.00},
    'MF': {'ATT': 0.20, 'PLY': 0.35, 'DEF': 0.15, 'CTR': 0.20, 'PHY': 0.10, 'GKP': 0.00},
    'FW': {'ATT': 0.45, 'PLY': 0.20, 'DEF': 0.00, 'CTR': 0.25, 'PHY': 0.10, 'GKP': 0.00},
    'FW,MF': {'ATT': 0.30, 'PLY': 0.30, 'DEF': 0.05, 'CTR': 0.25, 'PHY': 0.10, 'GKP': 0.00},
    'MF,FW': {'ATT': 0.30, 'PLY': 0.30, 'DEF': 0.05, 'CTR': 0.25, 'PHY': 0.10, 'GKP': 0.00},
    'DF,MF': {'ATT': 0.15, 'PLY': 0.25, 'DEF': 0.25, 'CTR': 0.15, 'PHY': 0.20, 'GKP': 0.00},
    'MF,DF': {'ATT': 0.15, 'PLY': 0.25, 'DEF': 0.25, 'CTR': 0.15, 'PHY': 0.20, 'GKP': 0.00},
    'DF,FW': {'ATT': 0.25, 'PLY': 0.20, 'DEF': 0.20, 'CTR': 0.20, 'PHY': 0.15, 'GKP': 0.00},
    'FW,DF': {'ATT': 0.25, 'PLY': 0.20, 'DEF': 0.20, 'CTR': 0.20, 'PHY': 0.15, 'GKP': 0.00},
    'DF,GK': {'ATT': 0.00, 'PLY': 0.10, 'DEF': 0.40, 'CTR': 0.00, 'PHY': 0.20, 'GKP': 0.30},
    'SUB': {'ATT': 0.20, 'PLY': 0.25, 'DEF': 0.15, 'CTR': 0.20, 'PHY': 0.20, 'GKP': 0.00},
    '': {'ATT': 0.20, 'PLY': 0.25, 'DEF': 0.15, 'CTR': 0.20, 'PHY': 0.20, 'GKP': 0.00},
}

SUFFICIENT_SAMPLE_MINUTES = 1500

# Minimum minutes for percentile calculation (only compare against players with meaningful data)
MIN_MINUTES_FOR_PERCENTILE = {
    'GK': 1000,   # GKs need ~11 games for reliable stats
    'DF': 900,    # Defenders need ~10 games
    'MF': 900,    # Midfielders need ~10 games  
    'FW': 900,    # Forwards need ~10 games
    'default': 900,
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_confidence_factor(minutes_played: int) -> float:
    """
    Returns a confidence factor based on minutes played.
    
    More minutes = more confidence in the stats being real vs random variance.
    
    Args:
        minutes_played: Minutes played by the player
    
    Returns:
        Confidence factor between 0.5 and 1.0
    """
    if minutes_played >= 1500:
        return 1.0  # Full confidence
    elif minutes_played >= 1200:
        return 0.9
    elif minutes_played >= 900:
        return 0.8
    elif minutes_played >= 600:
        return 0.7
    elif minutes_played >= 300:
        return 0.6
    else:
        return 0.5  # Minimum confidence for <300 minutes


def weighted_stat_by_minutes(
    raw_stat_per90: float, 
    league_avg_per90: float, 
    minutes_played: int,
    inverse: bool = False
) -> float:
    """
    Weights the player's stat with the league average based on minutes played.
    
    Uses tiered confidence factors to penalize small sample sizes:
    - >= 1500 min: 100% player stats (1.0 weight)
    - 1200-1499:   90% player, 10% league avg
    - 900-1199:    80% player, 20% league avg
    - 600-899:     70% player, 30% league avg
    - 300-599:     60% player, 40% league avg
    - < 300:       50% player, 50% league avg
    
    For inverse stats (lower is better, like goals conceded):
    - If player has better (lower) stat with few minutes, regress UP toward league avg
    - If player has worse (higher) stat with few minutes, regress DOWN toward league avg
    - This prevents fluky good/bad performances from distorting ratings
    
    Args:
        raw_stat_per90: Player's stat per 90 minutes
        league_avg_per90: League average per 90 minutes
        minutes_played: Minutes played by the player
        inverse: If True, lower values are better (e.g., goals conceded)
    
    Returns:
        Weighted statistic
    """
    MIN_MINUTES = 90
    
    if minutes_played < MIN_MINUTES:
        return league_avg_per90
    
    # Get confidence factor based on minutes
    player_weight = get_confidence_factor(minutes_played)
    league_weight = 1.0 - player_weight
    
    # Blend player stats with league average based on confidence
    weighted = (raw_stat_per90 * player_weight) + (league_avg_per90 * league_weight)
    
    # Note: The regression works the same way for both normal and inverse stats
    # - For normal stats: bad performance (low) regresses up, good (high) regresses down
    # - For inverse stats: bad performance (high) regresses down, good (low) regresses up
    # The math is the same because we're always regressing toward the mean
    
    return weighted


def normalize_stat_percentile(value: float, values_list: List[float], inverse: bool = False) -> float:
    """
    Normalizes a stat using percentiles (0-100).
    
    Args:
        value: The player's value
        values_list: List of all values in the league
        inverse: If True, lower values are better (e.g., goals conceded)
    
    Returns:
        Normalized value 0-100
    """
    if not values_list:
        return 50.0
    
    sorted_vals = sorted(values_list)
    
    if value <= sorted_vals[0]:
        percentile = 0.0
    elif value >= sorted_vals[-1]:
        percentile = 100.0
    else:
        below = sum(1 for v in sorted_vals if v < value)
        equal = sum(1 for v in sorted_vals if v == value)
        percentile = 100.0 * (below + equal / 2.0) / len(sorted_vals)
    
    if inverse:
        percentile = 100.0 - percentile
    
    return percentile


def fetch_league_stats(engine: sa.Engine, league: str, position: str = None) -> Dict[str, List[float]]:
    """
    Fetches all league statistics for percentile normalization.
    
    Now filters by position AND minimum minutes to ensure fair comparisons:
    - Only compares against players with meaningful sample sizes
    - Defenders compared against defenders with 900+ minutes
    - GKs compared against GKs with 1000+ minutes
    - etc.
    
    Args:
        engine: SQLAlchemy engine
        league: League name
        position: Player position for filtering (if None, uses all players)
    
    Returns:
        Dictionary with lists of values for each metric
    """
    # Get minimum minutes threshold for this position
    min_minutes = MIN_MINUTES_FOR_PERCENTILE.get(position, MIN_MINUTES_FOR_PERCENTILE['default'])
    
    # Build position filter
    if position and position in ['GK', 'DF', 'MF', 'FW']:
        position_filter = "AND position = :position"
    elif position and ',' in position:
        # Handle mixed positions like 'DF,MF' - compare against both groups
        positions = position.split(',')
        position_filter = f"AND (position = :pos1 OR position = :pos2)"
    else:
        # For unknown positions, compare against all non-GK
        position_filter = "AND position != 'GK'"
    
    query = text(f"""
        SELECT 
            goals_per90, assists_per90,
            expected_goals_per90, expected_assists_per90,
            progressive_carries, progressive_passes, progressive_passes_received,
            passes_completed, passes_pct, passes_progressive_distance,
            tackles, interceptions, clearances, blocks,
            gk_goals_against, gk_psxg, gk_psnpxg_per_shot_on_target_against,
            minutes, minutes_90s
        FROM players
        WHERE league = :league
          AND minutes >= :min_minutes
          {position_filter}
    """)
    
    with engine.connect() as conn:
        # Build params for query
        params = {"league": league, "min_minutes": min_minutes}
        if position and position in ['GK', 'DF', 'MF', 'FW']:
            params["position"] = position
        elif position and ',' in position:
            positions = position.split(',')
            params["pos1"] = positions[0]
            params["pos2"] = positions[1] if len(positions) > 1 else positions[0]
        
        rows = conn.execute(query, params).fetchall()
        
        stats = {
            # Already per-90 in database
            'goals_per90': [],
            'assists_per90': [],
            'expected_goals_per90': [],
            'expected_assists_per90': [],
            # Will be converted to per-90
            'progressive_carries_per90': [],
            'progressive_passes_per90': [],
            'progressive_passes_received_per90': [],
            'tackles_per90': [],
            'interceptions_per90': [],
            'clearances_per90': [],
            'blocks_per90': [],
            # Totals and percentages (keep as-is)
            'passes_completed': [],
            'passes_pct': [],
            'passes_progressive_distance': [],
            # GK stats (per-90)
            'gk_goals_against_per90': [],
            'gk_psxg_per90': [],
            'gk_psnpxg_per_shot': [],
        }
        
        for row in rows:
            mins_90s = row[18] or 1.0  # Avoid division by zero
            
            # Already per-90 stats
            stats['goals_per90'].append(row[0] or 0.0)
            stats['assists_per90'].append(row[1] or 0.0)
            stats['expected_goals_per90'].append(row[2] or 0.0)
            stats['expected_assists_per90'].append(row[3] or 0.0)
            
            # Convert absolute to per-90
            stats['progressive_carries_per90'].append((row[4] or 0) / mins_90s)
            stats['progressive_passes_per90'].append((row[5] or 0) / mins_90s)
            stats['progressive_passes_received_per90'].append((row[6] or 0) / mins_90s)
            stats['tackles_per90'].append((row[10] or 0) / mins_90s)
            stats['interceptions_per90'].append((row[11] or 0) / mins_90s)
            stats['clearances_per90'].append((row[12] or 0) / mins_90s)
            stats['blocks_per90'].append((row[13] or 0) / mins_90s)
            
            # Totals and percentages
            stats['passes_completed'].append(row[7] or 0)
            stats['passes_pct'].append(row[8] or 0.0)
            stats['passes_progressive_distance'].append(row[9] or 0)
            
            # GK stats - normalize by minutes_90s
            stats['gk_goals_against_per90'].append((row[14] or 0) / mins_90s)
            stats['gk_psxg_per90'].append((row[15] or 0.0) / mins_90s)
            stats['gk_psnpxg_per_shot'].append(row[16] or 0.0)
        
        return stats


def calculate_player_rating(
    engine: sa.Engine,
    player_id: int,
    player_name: str,
    league: str,
    position: str,
    minutes: int,
    season: str,
    player_stats: Dict[str, float]
) -> Optional[Dict[str, any]]:
    """
    Calculates complete rating for a player.
    
    Args:
        engine: SQLAlchemy engine
        player_id: Player ID in database
        player_name: Player name
        league: Player's league
        position: Player's position
        minutes: Minutes played
        season: Season
        player_stats: Dictionary with all player stats
    
    Returns:
        Dictionary with all calculated ratings or None if failed
    """
    # ========================================================================
    # HANDLE EDGE CASE: VERY LOW MINUTES (<90 min = <1 full game)
    # ========================================================================
    MIN_PLAYABLE_MINUTES = 90
    
    if minutes < MIN_PLAYABLE_MINUTES:
        # Return minimum possible rating based on league
        league_base = LEAGUE_BASE_RATINGS.get(league, LEAGUE_BASE_RATINGS['default'])
        min_rating = round(league_base * 0.60 + 45 * 0.40)  # Floor performance at 45
        
        return {
            'player_id': player_id,
            'player_name': player_name,
            'season': season,
            'position': position,
            'minutes_played': minutes,
            'overall_rating': min_rating,
            'league_base_rating': league_base,
            'performance_rating': 45.0,
            'att': 45,
            'ply': 45,
            'def_rating': 45,
            'ctr': 45,
            'phy': 45,
            'gkp': 45 if position == 'GK' else None,
        }
    
    # Fetch league stats for normalization (filtered by position for fair comparison)
    league_stats = fetch_league_stats(engine, league, position)
    
    if not league_stats['goals_per90']:
        return None
    
    # Calculate league averages
    league_avgs = {
        key: statistics.mean(values) if values else 0.0
        for key, values in league_stats.items()
    }
    
    # ========================================================================
    # CONVERT ALL ABSOLUTE STATS TO PER-90 AND APPLY MINUTE WEIGHTING
    # ========================================================================
    weighted_stats = {}
    player_minutes_90s = max(player_stats.get('minutes_90s', minutes / 90.0), 0.01)
    
    # Stats that are already per 90 - apply minute weighting directly
    per90_stats = [
        'goals_per90', 'assists_per90', 
        'expected_goals_per90', 'expected_assists_per90'
    ]
    
    for stat_name in per90_stats:
        raw_value = player_stats.get(stat_name, 0.0)
        weighted_stats[stat_name] = weighted_stat_by_minutes(
            raw_value, league_avgs[stat_name], minutes
        )
    
    # Convert absolute stats to per-90 and apply weighting
    absolute_to_per90 = {
        'progressive_carries': 'progressive_carries_per90',
        'progressive_passes': 'progressive_passes_per90',
        'progressive_passes_received': 'progressive_passes_received_per90',
        'tackles': 'tackles_per90',
        'interceptions': 'interceptions_per90',
        'clearances': 'clearances_per90',
        'blocks': 'blocks_per90',
    }
    
    for abs_stat, per90_stat in absolute_to_per90.items():
        absolute_value = player_stats.get(abs_stat, 0)
        player_per90 = absolute_value / player_minutes_90s
        
        # Get league average per 90 (already calculated in league_stats)
        league_avg_per90 = league_avgs.get(per90_stat, 0.0)
        
        # Apply minute weighting
        weighted_stats[per90_stat] = weighted_stat_by_minutes(
            player_per90, league_avg_per90, minutes
        )
    
    # For percentage stats and totals, use as-is (already normalized)
    weighted_stats['passes_completed'] = player_stats.get('passes_completed', 0)
    weighted_stats['passes_pct'] = player_stats.get('passes_pct', 0.0)
    weighted_stats['passes_progressive_distance'] = player_stats.get('passes_progressive_distance', 0)
    
    # For GK: calculate per90 from absolute values and apply weighting
    if position == 'GK':
        gk_goals_against = player_stats.get('gk_goals_against', 0)
        gk_psxg = player_stats.get('gk_psxg', 0.0)
        
        player_gk_goals_per90 = gk_goals_against / player_minutes_90s
        player_gk_psxg_per90 = gk_psxg / player_minutes_90s
        
        # Apply minute weighting to GK stats
        weighted_stats['gk_goals_against_per90'] = weighted_stat_by_minutes(
            player_gk_goals_per90,
            league_avgs.get('gk_goals_against_per90', 1.0),
            minutes
        )
        weighted_stats['gk_psxg_per90'] = weighted_stat_by_minutes(
            player_gk_psxg_per90,
            league_avgs.get('gk_psxg_per90', 1.0),
            minutes
        )
        weighted_stats['gk_psnpxg_per_shot'] = player_stats.get('gk_psnpxg_per_shot', 0.0)
    
    # ========================================================================
    # NORMALIZE ALL STATS USING PERCENTILES
    # ========================================================================
    normalized = {}
    
    # Per-90 offensive stats (already weighted)
    for stat in per90_stats:
        value = weighted_stats[stat]
        normalized[stat] = normalize_stat_percentile(value, league_stats[stat], inverse=False)
    
    # Newly converted per-90 stats (already weighted, distributions already in league_stats)
    for per90_stat in absolute_to_per90.values():
        value = weighted_stats[per90_stat]
        # Use pre-calculated per-90 distributions from league_stats
        normalized[per90_stat] = normalize_stat_percentile(
            value, 
            league_stats.get(per90_stat, [50]),  # Already per-90 in league_stats
            inverse=False
        )
    
    # Percentage and total stats - use as-is
    normalized['passes_completed'] = normalize_stat_percentile(
        weighted_stats['passes_completed'], 
        league_stats['passes_completed'], 
        inverse=False
    )
    normalized['passes_pct'] = normalize_stat_percentile(
        weighted_stats['passes_pct'],
        league_stats['passes_pct'],
        inverse=False
    )
    normalized['passes_progressive_distance'] = normalize_stat_percentile(
        weighted_stats['passes_progressive_distance'],
        league_stats['passes_progressive_distance'],
        inverse=False
    )
    
    # GK stats (already weighted and calculated per-90)
    if position == 'GK':
        # Goals against per 90 - INVERSE (lower is better)
        normalized['gk_goals_against_per90'] = normalize_stat_percentile(
            weighted_stats['gk_goals_against_per90'],
            league_stats['gk_goals_against_per90'],
            inverse=True  # Lower goals conceded = better
        )
        # PSxG per 90 - INVERSE (lower is better - means conceding less than expected)
        normalized['gk_psxg_per90'] = normalize_stat_percentile(
            weighted_stats['gk_psxg_per90'],
            league_stats['gk_psxg_per90'],
            inverse=True  # Lower PSxG = better goalkeeper
        )
        # PSxG per shot - INVERSE (lower is better)
        normalized['gk_psnpxg_per_shot'] = normalize_stat_percentile(
            weighted_stats['gk_psnpxg_per_shot'],
            league_stats['gk_psnpxg_per_shot'],
            inverse=True  # Lower expected goals per shot = better
        )
    
    # ========================================================================
    # CALCULATE ATTRIBUTES
    # ========================================================================
    
    # ATT - Attacking (50% base - allows more differentiation)
    att = max(50, (
        normalized['goals_per90'] * 0.40 +
        normalized['expected_goals_per90'] * 0.30 +
        normalized['assists_per90'] * 0.20 +
        normalized['progressive_passes_received_per90'] * 0.10
    ))
    
    # PLY - Playmaking (45% base)
    ply = max(45, (
        normalized['assists_per90'] * 0.25 +
        normalized['expected_assists_per90'] * 0.20 +
        normalized['progressive_passes_per90'] * 0.25 +
        normalized['passes_pct'] * 0.15 +
        normalized['passes_progressive_distance'] * 0.15
    ))
    
    # DEF - Defending (45% base - was too high at 72)
    def_rating = max(45, (
        normalized['tackles_per90'] * 0.30 +
        normalized['interceptions_per90'] * 0.30 +
        normalized['clearances_per90'] * 0.25 +
        normalized['blocks_per90'] * 0.15
    ))
    
    # CTR - Ball Control (45% base)
    ctr = max(45, (
        normalized['passes_pct'] * 0.35 +
        normalized['passes_completed'] * 0.25 +
        normalized['progressive_carries_per90'] * 0.40
    ))
    
    # PHY - Physical (45% base)
    phy = max(45, (
        normalized['tackles_per90'] * 0.30 +
        normalized['progressive_carries_per90'] * 0.30 +
        normalized['clearances_per90'] * 0.20 +
        normalized['blocks_per90'] * 0.20
    ))
    
    # GKP - Goalkeeping (only for goalkeepers)
    gkp = None
    if position == 'GK':
        # Calculate GKP using weighted and normalized per-90 stats
        gkp_raw = (
            normalized.get('gk_goals_against_per90', 50) * 0.40 +  # Main factor: goals conceded
            normalized.get('gk_psxg_per90', 50) * 0.35 +           # Post-shot xG (shot-stopping)
            normalized.get('gk_psnpxg_per_shot', 50) * 0.25        # Quality of saves
        )
        # Lower floor for GK to allow more differentiation (45 instead of 60)
        gkp = max(45, gkp_raw)
    
    # ========================================================================
    # CALCULATE OVR
    # ========================================================================
    
    # Get position weights
    pos_weights = POSITION_WEIGHTS.get(position, POSITION_WEIGHTS[''])
    
    # Calculate performance rating (weighted average of attributes)
    attributes = {
        'ATT': att,
        'PLY': ply,
        'DEF': def_rating,
        'CTR': ctr,
        'PHY': phy,
    }
    
    if position == 'GK' and gkp is not None:
        attributes['GKP'] = gkp
    
    performance_rating = sum(
        attributes[attr] * pos_weights[attr]
        for attr in attributes
        if attr in pos_weights
    )
    
    # Get league base rating
    league_base = LEAGUE_BASE_RATINGS.get(league, LEAGUE_BASE_RATINGS['default'])
    
    # OVR = 60% League Base + 40% Performance
    overall_rating = round(league_base * 0.60 + performance_rating * 0.40)
    
    # ========================================================================
    # RETURN RESULT
    # ========================================================================
    
    return {
        'player_id': player_id,
        'player_name': player_name,
        'season': season,
        'position': position,
        'minutes_played': minutes,
        'overall_rating': overall_rating,
        'league_base_rating': league_base,
        'performance_rating': round(performance_rating, 2),
        'att': round(att),
        'ply': round(ply),
        'def_rating': round(def_rating),
        'ctr': round(ctr),
        'phy': round(phy),
        'gkp': round(gkp) if gkp is not None else None,
    }
