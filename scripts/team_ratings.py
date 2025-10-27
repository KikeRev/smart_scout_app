#!/usr/bin/env python3
"""
🎯 Sistema de Rating de Plantilla Completa

Calcula el rating de todos los jugadores de un equipo y lo muestra en formato tabla.

Uso:
    python scripts/team_ratings.py "Real Madrid"
    python scripts/team_ratings.py "Manchester City" --season "2024-25"
    python scripts/team_ratings.py "Real Madrid" --export ratings.csv
"""

import os
import sys
import sqlalchemy as sa
from sqlalchemy import text
import argparse

# Importar funciones del script original
from calculate_player_rating import (
    DATABASE_URL,
    LEAGUE_BASE_RATINGS,
    POSITION_WEIGHTS,
    SUFFICIENT_SAMPLE_MINUTES,
    weighted_stat_by_minutes,
    normalize_stat_percentile
)

def calculate_team_ratings(team_name, season=None, export_csv=None):
    """
    Calcula ratings de todos los jugadores de un equipo.
    
    Args:
        team_name: Nombre del equipo
        season: Temporada (ej: "2024-25"). Si es None, usa todas las temporadas
        export_csv: Ruta para exportar a CSV
    """
    engine = sa.create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        # 1. Primero verificar que el equipo existe
        query_check_team = f"""
        SELECT DISTINCT club, COUNT(*) as total_players
        FROM players 
        WHERE club ILIKE '%{team_name}%'
        GROUP BY club;
        """
        
        result = conn.execute(text(query_check_team))
        teams = result.fetchall()
        
        if not teams:
            print(f"❌ No se encontró el equipo '{team_name}'")
            return
        
        # Si hay múltiples coincidencias, mostrar opciones
        if len(teams) > 1:
            print(f"\n⚠️  Se encontraron {len(teams)} equipos con ese nombre:")
            for i, team in enumerate(teams, 1):
                print(f"   {i}. {team.club} ({team.total_players} jugadores)")
            print(f"\n💡 Usa el nombre exacto del equipo para mejores resultados")
            print(f"   Ejemplo: python scripts/team_ratings.py \"{teams[0].club}\"")
            return
        
        # Usar el nombre exacto del equipo encontrado
        exact_team_name = teams[0].club
        total_players = teams[0].total_players
        
        print(f"✅ Equipo encontrado: {exact_team_name} ({total_players} jugadores en total)")
        
        # 2. Si se especifica temporada, verificar que existe
        if season:
            query_check_season = f"""
            SELECT COUNT(*) as players_in_season
            FROM players 
            WHERE club = '{exact_team_name}' AND season = '{season}';
            """
            
            result = conn.execute(text(query_check_season))
            season_check = result.fetchone()
            
            if season_check.players_in_season == 0:
                # Mostrar temporadas disponibles
                query_available_seasons = f"""
                SELECT DISTINCT season, COUNT(*) as player_count
                FROM players 
                WHERE club = '{exact_team_name}' AND season IS NOT NULL
                GROUP BY season
                ORDER BY season DESC;
                """
                
                result = conn.execute(text(query_available_seasons))
                available_seasons = result.fetchall()
                
                print(f"\n❌ No se encontraron jugadores para la temporada '{season}'")
                print(f"\n📅 Temporadas disponibles para {exact_team_name}:")
                for s in available_seasons:
                    print(f"   - {s.season} ({s.player_count} jugadores)")
                return
            
            print(f"✅ Temporada {season}: {season_check.players_in_season} jugadores")
        
        # 3. Obtener jugadores del equipo (con o sin filtro de temporada)
        season_filter = f"AND season = '{season}'" if season else ""
        
        query_team = f"""
        SELECT 
            full_name, position, club, league, age,
            minutes, minutes_90s, season,
            goals, assists, 
            expected_goals, expected_assists,
            progressive_carries, progressive_passes, progressive_passes_received,
            passes_completed, passes, passes_pct,
            tackles, tackles_won, interceptions, blocks, clearances,
            challenges, challenges_lost, errors,
            gk_goals_against, gk_psxg
        FROM players 
        WHERE club = '{exact_team_name}'
        {season_filter}
        ORDER BY position, minutes DESC;
        """
        
        result = conn.execute(text(query_team))
        players = result.fetchall()
        
        if not players:
            print(f"❌ Error inesperado: No se pudieron cargar los jugadores")
            return
        
        season_str = f" | Temporada: {season}" if season else " (Datos históricos agregados)"
        print(f"\n{'='*130}")
        print(f"🏆 RATINGS DE PLANTILLA: {players[0].club}")
        print(f"   Liga: {players[0].league} | Total Jugadores: {len(players)}{season_str}")
        print(f"{'='*130}\n")
        
        # Preparar datos para cada jugador
        team_ratings = []
        
        for player in players:
            try:
                # Obtener promedios de la liga para esta posición
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
                
                # Obtener todas las stats de la liga para percentiles
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
                
                # Calcular stats per 90
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
                
                gk_goals_against_per90 = player.gk_goals_against / minutes_90s if player.gk_goals_against else 0
                gk_psxg_per90 = player.gk_psxg / minutes_90s if player.gk_psxg else 0
                
                # Aplicar regresión a la media
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
                
                gk_goals_against_w = weighted_stat_by_minutes(gk_goals_against_per90, league_avg.avg_gk_goals_against_per90 or 1.0, player.minutes)
                gk_psxg_w = weighted_stat_by_minutes(gk_psxg_per90, league_avg.avg_gk_psxg_per90 or 1.0, player.minutes)
                
                # Normalizar usando percentiles
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
                
                gk_goals_against_norm = normalize_stat_percentile(gk_goals_against_w, gk_goals_against_values, inverse=True)
                gk_psxg_norm = normalize_stat_percentile(gk_psxg_w, gk_psxg_values, inverse=True)
                
                # Calcular atributos
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
                    65 * 0.15
                )
                
                DEF = round(
                    tackles_won_norm * 0.25 +
                    interceptions_norm * 0.25 +
                    blocks_norm * 0.15 +
                    clearances_norm * 0.25 +
                    72 * 0.10
                )
                
                CTR = round(
                    prog_carries_norm * 0.35 +
                    65 * 0.25 +
                    prog_passes_norm * 0.25 +
                    passes_pct_norm * 0.15
                )
                
                PHY = round(
                    65 * 0.40 +
                    prog_carries_norm * 0.35 +
                    tackles_won_norm * 0.25
                )
                
                GKP = round(
                    gk_goals_against_norm * 0.50 +
                    gk_psxg_norm * 0.30 +
                    passes_pct_norm * 0.10 +
                    blocks_norm * 0.10
                )
                
                # Calcular Performance Rating
                position = player.position
                if position not in POSITION_WEIGHTS:
                    position = 'MF'
                
                weights = POSITION_WEIGHTS[position]
                
                performance_rating = (
                    ATT * weights['ATT'] +
                    PLY * weights['PLY'] +
                    DEF * weights['DEF'] +
                    CTR * weights['CTR'] +
                    PHY * weights['PHY'] +
                    GKP * weights['GKP']
                )
                
                # Calcular Overall Rating
                league_base_rating = LEAGUE_BASE_RATINGS.get(player.league, LEAGUE_BASE_RATINGS['default'])
                league_weight = 0.60
                perf_weight = 0.40
                
                overall_rating = (league_base_rating * league_weight) + (performance_rating * perf_weight)
                
                # Guardar datos
                player_data = {
                    'name': player.full_name,
                    'position': player.position,
                    'age': player.age,
                    'minutes': player.minutes,
                    'season': player.season if hasattr(player, 'season') else 'N/A',
                    'ovr': round(overall_rating),
                    'att': ATT,
                    'ply': PLY,
                    'def': DEF,
                    'ctr': CTR,
                    'phy': PHY,
                    'gkp': GKP if player.position == 'GK' else None,
                    'performance': round(performance_rating, 1)
                }
                
                team_ratings.append(player_data)
                
            except Exception as e:
                print(f"⚠️  Error calculando rating de {player.full_name}: {e}")
                continue
    
    # Ordenar por OVR descendente
    team_ratings.sort(key=lambda x: x['ovr'], reverse=True)
    
    # Clasificar jugadores por minutos
    titulares = [p for p in team_ratings if p['minutes'] >= 1300]
    suplentes = [p for p in team_ratings if 300 <= p['minutes'] < 1300]
    canteranos = [p for p in team_ratings if p['minutes'] < 300]
    
    # Mostrar tabla
    print_team_table(team_ratings, titulares, suplentes, canteranos)
    
    # Calcular rating ponderado del equipo
    calculate_team_weighted_rating(titulares, suplentes, canteranos)
    
    # Exportar a CSV si se solicita
    if export_csv:
        export_to_csv(team_ratings, export_csv)
        print(f"\n✅ Datos exportados a: {export_csv}")


def print_team_table(team_ratings, titulares, suplentes, canteranos):
    """
    Imprime la tabla de ratings en consola, separando por categorías.
    """
    
    def print_category(players, category_name):
        if not players:
            return
        
        print(f"\n{'='*130}")
        print(f"📋 {category_name} ({len(players)} jugadores)")
        print(f"{'='*130}")
        print(f"{'Jugador':<25} {'Pos':<4} {'Edad':<4} {'Min':<5} {'Temp':<8} {'OVR':<4} {'ATT':<4} {'PLY':<4} {'DEF':<4} {'CTR':<4} {'PHY':<4} {'GKP':<4} {'Perf':<5}")
        print("-" * 130)
        
        for player in players:
            gkp_str = f"{player['gkp']:<4}" if player['gkp'] is not None else "  - "
            season_str = f"{player.get('season', 'N/A'):<8}"
            print(
                f"{player['name']:<25} "
                f"{player['position']:<4} "
                f"{player['age']:<4} "
                f"{player['minutes']:<5} "
                f"{season_str} "
                f"{player['ovr']:<4} "
                f"{player['att']:<4} "
                f"{player['ply']:<4} "
                f"{player['def']:<4} "
                f"{player['ctr']:<4} "
                f"{player['phy']:<4} "
                f"{gkp_str} "
                f"{player['performance']:<5.1f}"
            )
        
        avg_ovr = sum(p['ovr'] for p in players) / len(players)
        print(f"\n   📊 OVR Promedio: {avg_ovr:.1f}")
    
    # Imprimir por categorías
    print_category(titulares, "TITULARES (≥1300 minutos)")
    print_category(suplentes, "SUPLENTES (300-1299 minutos)")
    print_category(canteranos, "CANTERANOS/ROTACIÓN (<300 minutos)")
    
    # Estadísticas generales
    print(f"\n{'='*130}")
    print(f"📊 ESTADÍSTICAS GENERALES")
    print(f"{'='*130}")
    if team_ratings:
        print(f"   Total Jugadores: {len(team_ratings)}")
        print(f"   OVR Promedio: {sum(p['ovr'] for p in team_ratings) / len(team_ratings):.1f}")
        print(f"   OVR Más Alto: {max(p['ovr'] for p in team_ratings)} ({[p['name'] for p in team_ratings if p['ovr'] == max(p['ovr'] for p in team_ratings)][0]})")
        print(f"   OVR Más Bajo: {min(p['ovr'] for p in team_ratings)} ({[p['name'] for p in team_ratings if p['ovr'] == min(p['ovr'] for p in team_ratings)][0]})")


def calculate_team_weighted_rating(titulares, suplentes, canteranos):
    """
    Calcula el rating ponderado del equipo basado en:
    - Titulares (≥1300 min): 70% de peso
    - Suplentes (300-1299 min): 25% de peso
    - Canteranos (<300 min): 5% de peso
    """
    print(f"\n{'='*130}")
    print(f"⚡ RATING PONDERADO DEL EQUIPO")
    print(f"{'='*130}")
    
    if not titulares and not suplentes and not canteranos:
        print("   ❌ No hay suficientes datos para calcular el rating ponderado")
        return
    
    # Calcular promedios por categoría
    titular_ovr = sum(p['ovr'] for p in titulares) / len(titulares) if titulares else 0
    suplente_ovr = sum(p['ovr'] for p in suplentes) / len(suplentes) if suplentes else 0
    canterano_ovr = sum(p['ovr'] for p in canteranos) / len(canteranos) if canteranos else 0
    
    # Pesos
    peso_titulares = 0.70
    peso_suplentes = 0.25
    peso_canteranos = 0.05
    
    # Ajustar pesos si falta alguna categoría
    total_peso = 0
    if titulares:
        total_peso += peso_titulares
    if suplentes:
        total_peso += peso_suplentes
    if canteranos:
        total_peso += peso_canteranos
    
    # Normalizar pesos
    if total_peso > 0:
        peso_titulares = peso_titulares / total_peso if titulares else 0
        peso_suplentes = peso_suplentes / total_peso if suplentes else 0
        peso_canteranos = peso_canteranos / total_peso if canteranos else 0
    
    # Calcular rating ponderado
    team_rating = (
        titular_ovr * peso_titulares +
        suplente_ovr * peso_suplentes +
        canterano_ovr * peso_canteranos
    )
    
    print(f"\n   📊 Desglose por categoría:")
    if titulares:
        print(f"      Titulares ({len(titulares)}): OVR {titular_ovr:.1f} × {peso_titulares*100:.0f}% = {titular_ovr * peso_titulares:.1f}")
    if suplentes:
        print(f"      Suplentes ({len(suplentes)}): OVR {suplente_ovr:.1f} × {peso_suplentes*100:.0f}% = {suplente_ovr * peso_suplentes:.1f}")
    if canteranos:
        print(f"      Canteranos ({len(canteranos)}): OVR {canterano_ovr:.1f} × {peso_canteranos*100:.0f}% = {canterano_ovr * peso_canteranos:.1f}")
    
    print(f"\n   🏆 RATING PONDERADO DEL EQUIPO: {team_rating:.1f}")
    print(f"\n   💡 Interpretación:")
    if team_rating >= 85:
        print(f"      ⭐⭐⭐ Elite Mundial - Top 5 equipos")
    elif team_rating >= 80:
        print(f"      ⭐⭐ Élite Europeo - Top 20 equipos")
    elif team_rating >= 75:
        print(f"      ⭐ Muy Bueno - Top 50 equipos")
    elif team_rating >= 70:
        print(f"      ✅ Competitivo - Liga top")
    else:
        print(f"      🔵 En desarrollo")
    
    print(f"{'='*130}")


def export_to_csv(team_ratings, filename):
    """
    Exporta los ratings a un archivo CSV.
    """
    import csv
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['name', 'position', 'age', 'minutes', 'ovr', 'att', 'ply', 'def', 'ctr', 'phy', 'gkp', 'performance']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for player in team_ratings:
            writer.writerow(player)


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Calcular ratings de toda la plantilla de un equipo')
    parser.add_argument('team', type=str, help='Nombre del equipo (ej: "Real Madrid")')
    parser.add_argument('--season', type=str, help='Temporada (ej: "2024-25"). Por defecto usa 2024-25', default="2024-25")
    parser.add_argument('--all-seasons', action='store_true', help='Mostrar todas las temporadas (datos históricos agregados)')
    parser.add_argument('--export', type=str, help='Exportar a CSV (ej: ratings.csv)', default=None)
    
    args = parser.parse_args()
    
    # Si se especifica --all-seasons, no filtrar por temporada
    season = None if args.all_seasons else args.season
    
    calculate_team_ratings(args.team, season, args.export)

