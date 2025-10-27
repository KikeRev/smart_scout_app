#!/usr/bin/env python3
"""
🎯 Sistema de Rating de Jugadores - Implementación del Plan v2.0

Calcula el rating FIFA-style de un jugador basado en:
- Regresión a la media por minutos (1500 min = muestra suficiente)
- Rating base por nivel de liga
- 6 atributos: ATT, PLY, DEF, CTR, PHY, GKP
- Pesos específicos por posición

Uso:
    python scripts/calculate_player_rating.py "Toni Kroos"
"""

import os
import sys
import sqlalchemy as sa
from sqlalchemy import text

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://scout:scout@db:5432/scouting"
)

# Coeficientes de liga (Base Rating) - Ajustados por competitividad actual
LEAGUE_BASE_RATINGS = {
    'Premier League': 92,  # La liga más competitiva actualmente
    'La Liga': 90,         # Segunda en competitividad
    'Serie A': 88,         # Top 5 europeo
    'Bundesliga': 88,      # Top 5 europeo
    'Ligue 1': 88,         # Top 5 europeo (PSG/Monaco Champions)
    'Eredivisie': 79,      # Ajax en Europa
    'Primeira Liga': 79,   # Benfica/Porto en Europa
    'Belgian Pro League': 75,
    'default': 70,
}

# Pesos por posición - Balanceados para fútbol moderno (solo las 4 posiciones reales en BD)
POSITION_WEIGHTS = {
    # Porteros - Sin cambios (específico)
    'GK': {'ATT': 0.00, 'PLY': 0.00, 'DEF': 0.10, 'CTR': 0.00, 'PHY': 0.10, 'GKP': 0.80},
    
    # Defensas - Más balanceados (incluye centrales y laterales)
    'DF': {'ATT': 0.10, 'PLY': 0.20, 'DEF': 0.35, 'CTR': 0.10, 'PHY': 0.25, 'GKP': 0.00},
    
    # Mediocampistas - Más balanceados, menos peso defensivo
    'MF': {'ATT': 0.20, 'PLY': 0.35, 'DEF': 0.15, 'CTR': 0.20, 'PHY': 0.10, 'GKP': 0.00},
    
    # Delanteros - Más completos, menos solo gol
    'FW': {'ATT': 0.45, 'PLY': 0.20, 'DEF': 0.00, 'CTR': 0.25, 'PHY': 0.10, 'GKP': 0.00},
    
    # Posiciones mixtas/híbridas (promedio balanceado de ambas)
    'FW,MF': {'ATT': 0.30, 'PLY': 0.30, 'DEF': 0.05, 'CTR': 0.25, 'PHY': 0.10, 'GKP': 0.00},  # Delantero-mediocampista
    'MF,FW': {'ATT': 0.30, 'PLY': 0.30, 'DEF': 0.05, 'CTR': 0.25, 'PHY': 0.10, 'GKP': 0.00},  # Mediocampista-delantero
    'DF,MF': {'ATT': 0.15, 'PLY': 0.25, 'DEF': 0.25, 'CTR': 0.15, 'PHY': 0.20, 'GKP': 0.00},  # Defensa-mediocampista (lateral/pivote)
    'MF,DF': {'ATT': 0.15, 'PLY': 0.25, 'DEF': 0.25, 'CTR': 0.15, 'PHY': 0.20, 'GKP': 0.00},  # Mediocampista-defensa
    'DF,FW': {'ATT': 0.25, 'PLY': 0.20, 'DEF': 0.20, 'CTR': 0.20, 'PHY': 0.15, 'GKP': 0.00},  # Defensa-delantero (raro)
    'FW,DF': {'ATT': 0.25, 'PLY': 0.20, 'DEF': 0.20, 'CTR': 0.20, 'PHY': 0.15, 'GKP': 0.00},  # Delantero-defensa (raro)
    'DF,GK': {'ATT': 0.00, 'PLY': 0.10, 'DEF': 0.40, 'CTR': 0.00, 'PHY': 0.20, 'GKP': 0.30},  # Muy raro (portero-defensa)
    'SUB': {'ATT': 0.20, 'PLY': 0.25, 'DEF': 0.15, 'CTR': 0.20, 'PHY': 0.20, 'GKP': 0.00},   # Posición desconocida/suplente
    '': {'ATT': 0.20, 'PLY': 0.25, 'DEF': 0.15, 'CTR': 0.20, 'PHY': 0.20, 'GKP': 0.00},      # Posición vacía
}

SUFFICIENT_SAMPLE_MINUTES = 1500
LEAGUE_WEIGHT_MAX = 0.35

# ============================================================================
# FUNCIONES
# ============================================================================

def weighted_stat_by_minutes(raw_stat_per90, league_avg_per90, minutes_played, is_gkp=False):
    """
    Pondera la estadística del jugador con la media de la liga según minutos.
    
    Para GKP usa blending específico con 1100 minutos:
    - Usa blending ponderado: (m/(m+1100))*player + (1100/(m+1100))*league_avg
    
    Para otras stats usa factores de confianza:
    - >= 1500 min → 100% confianza en stat del jugador
    - < 1500 min → regresión a la media de la liga
    """
    MIN_MINUTES = 90
    
    if minutes_played < MIN_MINUTES:
        return league_avg_per90
    
    # Blending específico para GKP
    if is_gkp:
        BLEND_MINUTES = 1100.0
        player_weight = minutes_played / (minutes_played + BLEND_MINUTES)
        league_weight = 1.0 - player_weight
        weighted = (raw_stat_per90 * player_weight) + (league_avg_per90 * league_weight)
        return weighted
    
    # Blending estándar para otras stats
    player_weight = min(minutes_played / SUFFICIENT_SAMPLE_MINUTES, 1.0)
    league_weight = 1.0 - player_weight
    
    weighted = (raw_stat_per90 * player_weight) + (league_avg_per90 * league_weight)
    return weighted


def normalize_stat_percentile(value, values_list, inverse=False):
    """
    Normaliza una stat usando percentiles (0-100).
    Más realista que min-max: el 50th percentil = 50, no solo los extremos.
    
    Args:
        value: el valor del jugador
        values_list: lista de todos los valores de la liga
        inverse: True si menor es mejor (ej: goles en contra)
    """
    if not values_list or len(values_list) == 0:
        return 50.0
    
    # Calcular en qué percentil está el jugador
    sorted_values = sorted(values_list)
    position = sum(1 for v in sorted_values if v <= value)
    percentile = (position / len(sorted_values)) * 100
    
    # Si inverse, invertir (menos es mejor)
    if inverse:
        percentile = 100 - percentile
    
    return max(0, min(100, percentile))


def calculate_rating(player_name, player_uid=None):
    """
    Calcula el rating completo de un jugador.
    
    Args:
        player_name: Nombre del jugador
        player_uid: UID del jugador (opcional, para mayor precisión)
    
    Returns:
        dict: Diccionario con todos los ratings calculados o None si no se encuentra
    """
    engine = sa.create_engine(DATABASE_URL)
    
    # 1. Obtener datos del jugador
    if player_uid:
        query_player = f"""
        SELECT 
            id, full_name, player_uid, position, club, league, age,
            minutes, minutes_90s,
            goals, assists, 
            expected_goals, expected_assists,
            progressive_carries, progressive_passes, progressive_passes_received,
            passes_completed, passes, passes_pct,
            tackles, tackles_won, interceptions, blocks, clearances,
            challenges, challenges_lost, errors,
            -- Stats de portero
            gk_goals_against, gk_psxg
        FROM players 
        WHERE player_uid = '{player_uid}'
        LIMIT 1;
        """
    else:
        query_player = f"""
        SELECT 
            id, full_name, player_uid, position, club, league, age,
            minutes, minutes_90s,
            goals, assists, 
            expected_goals, expected_assists,
            progressive_carries, progressive_passes, progressive_passes_received,
            passes_completed, passes, passes_pct,
            tackles, tackles_won, interceptions, blocks, clearances,
            challenges, challenges_lost, errors,
            -- Stats de portero
            gk_goals_against, gk_psxg
        FROM players 
        WHERE full_name ILIKE '%{player_name}%'
        LIMIT 1;
        """
    
    with engine.connect() as conn:
        result = conn.execute(text(query_player))
        player = result.fetchone()
        
        if not player:
            print(f"❌ No se encontró a '{player_name}'")
            return None
        
        print(f"\n{'='*80}")
        print(f"✅ Jugador encontrado: {player.full_name}")
        print(f"   Posición: {player.position} | Club: {player.club} | Liga: {player.league}")
        print(f"   Edad: {player.age} | Minutos: {player.minutes} ({player.minutes_90s:.1f} partidos)")
        print(f"{'='*80}\n")
        
        # 2. Obtener promedios de la liga
        query_league_avg = f"""
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
        WHERE league = '{player.league}' 
          AND position = '{player.position}'
          AND minutes >= 500;
        """
        
        result = conn.execute(text(query_league_avg))
        league_avg = result.fetchone()
        
        # 3. Obtener TODAS las stats de la liga (para percentiles)
        query_league_all_stats = f"""
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
        WHERE league = '{player.league}' 
          AND position = '{player.position}'
          AND minutes >= 500
          AND minutes_90s > 0;
        """
        
        result = conn.execute(text(query_league_all_stats))
        league_all_stats = result.fetchall()
        
        # Extraer listas de valores para percentiles
        goals_values = [row.goals_per90 for row in league_all_stats if row.goals_per90 is not None]
        assists_values = [row.assists_per90 for row in league_all_stats if row.assists_per90 is not None]
        xg_values = [row.xg_per90 for row in league_all_stats if row.xg_per90 is not None]
        xa_values = [row.xa_per90 for row in league_all_stats if row.xa_per90 is not None]
        prog_carries_values = [row.prog_carries_per90 for row in league_all_stats if row.prog_carries_per90 is not None]
        prog_passes_values = [row.prog_passes_per90 for row in league_all_stats if row.prog_passes_per90 is not None]
        passes_pct_values = [row.passes_pct for row in league_all_stats if row.passes_pct is not None]
        tackles_won_values = [row.tackles_won_per90 for row in league_all_stats if row.tackles_won_per90 is not None]
        interceptions_values = [row.interceptions_per90 for row in league_all_stats if row.interceptions_per90 is not None]
        blocks_values = [row.blocks_per90 for row in league_all_stats if row.blocks_per90 is not None]
        clearances_values = [row.clearances_per90 for row in league_all_stats if row.clearances_per90 is not None]
        gk_goals_against_values = [row.gk_goals_against_per90 for row in league_all_stats if row.gk_goals_against_per90 is not None]
        gk_psxg_values = [row.gk_psxg_per90 for row in league_all_stats if row.gk_psxg_per90 is not None]
    
    # 4. Calcular stats per 90
    minutes_90s = player.minutes_90s if player.minutes_90s > 0 else 1
    
    goals_per90 = player.goals / minutes_90s
    assists_per90 = player.assists / minutes_90s
    xg_per90 = player.expected_goals / minutes_90s
    xa_per90 = player.expected_assists / minutes_90s
    prog_carries_per90 = player.progressive_carries / minutes_90s
    prog_passes_per90 = player.progressive_passes / minutes_90s
    passes_pct = player.passes_pct
    tackles_won_per90 = player.tackles_won / minutes_90s
    interceptions_per90 = player.interceptions / minutes_90s
    blocks_per90 = player.blocks / minutes_90s
    clearances_per90 = player.clearances / minutes_90s
    
    # Stats de portero
    gk_goals_against_per90 = player.gk_goals_against / minutes_90s if player.gk_goals_against else 0
    gk_psxg_per90 = player.gk_psxg / minutes_90s if player.gk_psxg else 0
    
    # 5. Aplicar regresión a la media
    player_weight = min(player.minutes / SUFFICIENT_SAMPLE_MINUTES, 1.0)
    
    print(f"⚖️  Factor de peso: {player_weight:.2f} ({player_weight*100:.0f}% confianza en stats del jugador)\n")
    
    goals_w = weighted_stat_by_minutes(goals_per90, league_avg.avg_goals_per90, player.minutes)
    assists_w = weighted_stat_by_minutes(assists_per90, league_avg.avg_assists_per90, player.minutes)
    xg_w = weighted_stat_by_minutes(xg_per90, league_avg.avg_xg_per90, player.minutes)
    xa_w = weighted_stat_by_minutes(xa_per90, league_avg.avg_xa_per90, player.minutes)
    prog_carries_w = weighted_stat_by_minutes(prog_carries_per90, league_avg.avg_prog_carries_per90, player.minutes)
    prog_passes_w = weighted_stat_by_minutes(prog_passes_per90, league_avg.avg_prog_passes_per90, player.minutes)
    tackles_won_w = weighted_stat_by_minutes(tackles_won_per90, league_avg.avg_tackles_won_per90, player.minutes)
    interceptions_w = weighted_stat_by_minutes(interceptions_per90, league_avg.avg_interceptions_per90, player.minutes)
    blocks_w = weighted_stat_by_minutes(blocks_per90, league_avg.avg_blocks_per90, player.minutes)
    clearances_w = weighted_stat_by_minutes(clearances_per90, league_avg.avg_clearances_per90, player.minutes)
    
    # Regresión para stats de portero con blending específico
    gk_goals_against_w = weighted_stat_by_minutes(gk_goals_against_per90, league_avg.avg_gk_goals_against_per90 or 1.0, player.minutes, is_gkp=True)
    gk_psxg_w = weighted_stat_by_minutes(gk_psxg_per90, league_avg.avg_gk_psxg_per90 or 1.0, player.minutes, is_gkp=True)
    
    # 6. Normalizar usando percentiles (0-100)
    goals_norm = normalize_stat_percentile(goals_w, goals_values)
    assists_norm = normalize_stat_percentile(assists_w, assists_values)
    xg_norm = normalize_stat_percentile(xg_w, xg_values)
    xa_norm = normalize_stat_percentile(xa_w, xa_values)
    prog_carries_norm = normalize_stat_percentile(prog_carries_w, prog_carries_values)
    prog_passes_norm = normalize_stat_percentile(prog_passes_w, prog_passes_values)
    passes_pct_norm = normalize_stat_percentile(passes_pct, passes_pct_values)
    tackles_won_norm = normalize_stat_percentile(tackles_won_w, tackles_won_values)
    interceptions_norm = normalize_stat_percentile(interceptions_w, interceptions_values)
    blocks_norm = normalize_stat_percentile(blocks_w, blocks_values)
    clearances_norm = normalize_stat_percentile(clearances_w, clearances_values)
    
    # Normalizar stats de portero (gk_goals_against es inverso: menos es mejor)
    # psxg también es inverso: menos xG permitido = mejor portero
    gk_goals_against_norm = normalize_stat_percentile(gk_goals_against_w, gk_goals_against_values, inverse=True)
    gk_psxg_norm = normalize_stat_percentile(gk_psxg_w, gk_psxg_values, inverse=True)
    
    # 7. Calcular 6 atributos
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
        clearances_norm * 0.25 +  # Importante para defensas centrales
        72 * 0.10  # Piso más alto para profesionales
    )
    
    CTR = round(
        prog_carries_norm * 0.35 +
        65 * 0.25 +  # Piso más alto
        prog_passes_norm * 0.25 +
        passes_pct_norm * 0.15
    )
    
    # Obtener el base rating de la liga para PHY y GKP
    league_base_rating = LEAGUE_BASE_RATINGS.get(player.league, LEAGUE_BASE_RATINGS['default'])
    
    # PHY - Físico (promedio de base de liga + performance)
    phy_performance = (
        tackles_won_norm * 0.30 +
        prog_carries_norm * 0.30 +
        clearances_norm * 0.20 +
        blocks_norm * 0.20
    )
    PHY = round((league_base_rating + phy_performance) / 2)
    
    # Atributo GKP (solo para porteros, promedio de base de liga + performance)
    # Usamos stats inversas: menos goles = mejor
    gkp_performance = (
        gk_goals_against_norm * 0.40 +  # Lo más importante: pocos goles
        gk_psxg_norm * 0.35 +            # Calidad de paradas (vs xG)
        gk_psxg_norm * 0.25              # Calidad de paradas por disparo
    )
    GKP = round((league_base_rating + gkp_performance) / 2)
    
    # Mostrar atributos (incluir GKP solo para porteros)
    if player.position == 'GK':
        print(f"🎯 Atributos:")
        print(f"   ATT: {ATT} | PLY: {PLY} | DEF: {DEF} | CTR: {CTR} | PHY: {PHY} | GKP: {GKP}\n")
    else:
        print(f"🎯 Atributos:")
        print(f"   ATT: {ATT} | PLY: {PLY} | DEF: {DEF} | CTR: {CTR} | PHY: {PHY}\n")
    
    # 8. Calcular Performance Rating
    position = player.position
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
    
    print(f"⚡ Performance Rating: {performance_rating:.1f}")
    if position == 'GK':
        print(f"   Pesos ({position}): ATT={weights['ATT']*100:.0f}%, PLY={weights['PLY']*100:.0f}%, DEF={weights['DEF']*100:.0f}%, CTR={weights['CTR']*100:.0f}%, PHY={weights['PHY']*100:.0f}%, GKP={weights['GKP']*100:.0f}%\n")
    else:
        print(f"   Pesos ({position}): ATT={weights['ATT']*100:.0f}%, PLY={weights['PLY']*100:.0f}%, DEF={weights['DEF']*100:.0f}%, CTR={weights['CTR']*100:.0f}%, PHY={weights['PHY']*100:.0f}%\n")
    
    # 9. Calcular Overall Rating (60-40 liga base vs performance)
    league_base_rating = LEAGUE_BASE_RATINGS.get(player.league, LEAGUE_BASE_RATINGS['default'])
    
    # Balance 60-40: Más peso a liga base (reconoce nivel elite de las ligas top)
    league_weight = 0.60
    perf_weight = 0.40
    
    overall_rating = (league_base_rating * league_weight) + (performance_rating * perf_weight)
    
    print(f"{'='*80}")
    print(f"🌟 OVERALL RATING: {round(overall_rating)}")
    print(f"{'='*80}")
    print(f"\n📊 Desglose:")
    print(f"   Liga Base ({player.league}): {league_base_rating} (peso: {league_weight*100:.1f}%)")
    print(f"   Performance: {performance_rating:.1f} (peso: {perf_weight*100:.1f}%)")
    print(f"   OVR = ({league_base_rating} × {league_weight:.3f}) + ({performance_rating:.1f} × {perf_weight:.3f})")
    print(f"   OVR = {league_base_rating * league_weight:.1f} + {performance_rating * perf_weight:.1f} = {overall_rating:.1f}")
    print(f"\n{'='*80}\n")
    
    # Devolver diccionario con todos los datos calculados
    return {
        'player_id': player.id,
        'player_uid': player.player_uid,
        'player_name': player.full_name,
        'overall_rating': round(overall_rating),
        'league_base_rating': league_base_rating,
        'performance_rating': round(performance_rating, 1),
        'att': round(ATT, 1),
        'ply': round(PLY, 1),
        'def_rating': round(DEF, 1),
        'ctr': round(CTR, 1),
        'phy': round(PHY, 1),
        'gkp': round(GKP, 1),
        'season': '2024',  # TODO: obtener de la base de datos
        'position': position,
        'minutes_played': player.minutes,
        'league': player.league,
        'club': player.club
    }


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/calculate_player_rating.py \"Nombre del Jugador\" [player_uid]")
        print("\nEjemplos:")
        print("  python scripts/calculate_player_rating.py \"Toni Kroos\"")
        print("  python scripts/calculate_player_rating.py \"Kylian Mbappe\"")
        print("  python scripts/calculate_player_rating.py \"Toni Kroos\" \"Toni_Kroos_1990\"")
        sys.exit(1)
    
    player_name = sys.argv[1]
    player_uid = sys.argv[2] if len(sys.argv) > 2 else None
    result = calculate_rating(player_name, player_uid)
    
    if result:
        print(f"\n✅ Rating calculado exitosamente para {result['player_name']} ({result['player_uid']})")
        print(f"   Overall Rating: {result['overall_rating']}")
    else:
        print(f"\n❌ No se pudo calcular el rating para {player_name}")


