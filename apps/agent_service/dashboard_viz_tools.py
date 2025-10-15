"""
dashboard_viz_tools.py - Visualization tools for the manual search dashboard

Specific functions for the player comparison dashboard:
- radar_chart_single: Individual radar for 1 player
- radar_chart_comparison: Comparative radar for 2-3 players with legend
- get_available_metrics: Get available metrics by position
"""

from __future__ import annotations
import tempfile
import time
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
import matplotlib.pyplot as plt
import numpy as np
from mplsoccer import PyPizza, Radar, FontManager, grid
from apps.agent_service.players_service import player_stats
from django.conf import settings
from shutil import move
from highlight_text import fig_text
from uuid import uuid4
import importlib

def _django_model(name):
    """Returns the Django model if Django is configured"""
    try:
        from django.conf import settings
        if settings.configured:
            module, cls = name.rsplit(".", 1)
            return getattr(importlib.import_module(module), cls)
    except Exception:
        return None

TempChart = _django_model("apps.charts.models.TempChart")

# Fonts - initialize safely
try:
    FONTS_PATH = Path(__file__).resolve().parent / "fonts"

    serif_regular     = FontManager((FONTS_PATH / "serif_regular.ttf").as_uri())
    serif_extra_light = FontManager((FONTS_PATH / "serif_extra_light.ttf").as_uri())
    rubik_regular     = FontManager((FONTS_PATH / "rubik_regular.ttf").as_uri())
    robotto_thin      = FontManager((FONTS_PATH / "robotto_thin.ttf").as_uri())
    robotto_bold      = FontManager((FONTS_PATH / "robotto_bold.ttf").as_uri())
    font_bold         = FontManager((FONTS_PATH / "RobotoSlab-Bold.ttf").as_uri())
    font_normal       = FontManager((FONTS_PATH / "RobotoSlab-Regular.ttf").as_uri())
    font_italic       = FontManager((FONTS_PATH / "RobotoSlab-Italic.ttf").as_uri())
except:
    # Fallback to default fonts if not available
    robotto_bold = None
    robotto_thin = None

# Radar metrics (6 generic metrics)
RADAR_METRICS = [
    ['Age', 'age', 35],
    ['Min/Game', None, 90],  # None means it's calculated
    ['Games 90s', 'minutes_90s', 40],
    ['Goals', 'goals', 30],
    ['Assists', 'assists', 20],
    ['G+A', None, 50],  # Goals + Assists
]

# Metrics by position (for the selector)
POSITION_METRICS = {
    'GK': [
        'age', 'minutes_90s', 'goals_against', 'saves', 'clean_sheets', 'saves_pct'
    ],
    'DF': [
        'age', 'minutes_90s', 'tackles_won', 'interceptions', 'clearances', 'blocks', 'passes_pct'
    ],
    'MF': [
        'age', 'minutes_90s', 'goals', 'assists', 'passes_pct', 'progressive_passes', 'tackles_won'
    ],
    'FW': [
        'age', 'minutes_90s', 'goals', 'assists', 'goals_per90', 'assists_per90', 'expected_goals_per90'
    ]
}

def _save(fig, label: str | None = None) -> dict:
    """Saves the chart and returns the URL"""
    charts_dir = Path(settings.MEDIA_ROOT) / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    final = charts_dir / f"{uuid4().hex}.png"
    fig.savefig(final, dpi=300, bbox_inches="tight", facecolor="white")

    chart = TempChart.objects.create(image=f"charts/{final.name}")
    return {
        "text": f"Here's the chart{': ' + label if label else ''}.",
        "attachments": [
            {"type": "image", "url": chart.image.url}
        ],
    }



def get_available_metrics(position: str) -> List[str]:
    """
    Gets available metrics for a specific position
    
    Parameters
    ----------
    position : str
        Player position (GK, DF, MF, FW)
        
    Returns
    -------
    List[str]
        List of available metrics for that position
    """
    return POSITION_METRICS.get(position.upper(), POSITION_METRICS['MF'])

def get_all_metrics() -> Dict[str, List[str]]:
    """
    Gets all available metrics by position
    
    Returns
    -------
    Dict[str, List[str]]
        Dictionary with metrics by position
    """
    return POSITION_METRICS


# =============================================================================
# SPECIFIC FUNCTIONS FOR THE MANUAL SEARCH DASHBOARD
# =============================================================================

# Global cache for 95th percentiles - calculated only once
_METRICS_PERCENTILES_95_CACHE = None

def get_metrics_percentiles_95() -> Dict[str, float]:
    """
    Gets the 95th percentile of all metrics for correct normalization
    Calculated only once and cached to avoid recalculations
    
    Returns
    -------
    Dict[str, float]
        Dictionary with 95th percentile of each metric
    """
    global _METRICS_PERCENTILES_95_CACHE
    
    # If already cached, return it
    if _METRICS_PERCENTILES_95_CACHE is not None:
        return _METRICS_PERCENTILES_95_CACHE
    
    try:
        import requests
        from apps.dashboard.search_services import API_BASE_URL
        
        print("Calculating 95th percentiles of the entire database...")
        
        # Get ALL players to calculate correct percentiles
        response = requests.get(f"{API_BASE_URL}/players/all?limit=5000", timeout=60)
        response.raise_for_status()
        
        all_players = response.json().get('players', [])
        print(f"Retrieved {len(all_players)} players to calculate percentiles")
        
        if not all_players:
            # Default values if no data
            _METRICS_PERCENTILES_95_CACHE = {
                # Basic metrics
                'age': 35, 'minutes': 3000, 'minutes_90s': 40,
                
                # Goals and assists
                'goals': 20, 'assists': 15, 'goals_per90': 1.0, 'assists_per90': 0.8, 'goals_assists_per90': 1.5,
                
                # Expected Goals
                'expected_goals': 20, 'expected_assists': 15, 'expected_goals_per90': 0.8, 'expected_assists_per90': 0.8,
                'expected_goals_assists_per90': 1.5, 'no_penalty_expected_goals_plus_expected_assists': 30,
                
                # Passes
                'passes_completed': 2000, 'passes': 2500, 'passes_pct': 95, 'passes_progressive_distance': 10000,
                'passes_completed_long': 200, 'passes_long': 300, 'passes_pct_long': 80,
                'progressive_passes': 200, 'progressive_passes_received': 300,
                
                # Dribbles and carries
                'progressive_carries': 150,
                
                # Defensive
                'tackles': 100, 'tackles_won': 50, 'challenge_tackles': 30, 'challenges': 80, 'challenge_tackles_pct': 50,
                'challenges_lost': 50, 'blocks': 40, 'blocked_shots': 5, 'blocked_passes': 35,
                'interceptions': 30, 'tackles_interizations': 80, 'clearances': 40, 'errors': 5,
                
                # Goalkeepers
                'gk_goals_against': 50, 'gk_pens_allowed': 5, 'gk_free_kick_goals_against': 3,
                'gk_corner_kick_goals_against': 10, 'gk_own_goals_against': 2, 'gk_psxg': 50,
                'gk_psnpxg_per_shot_on_target_against': 0.8
            }
            return _METRICS_PERCENTILES_95_CACHE
        
        # Calculate 95th percentile for each metric
        percentiles = {}
        
        # All numeric metrics available in the system
        metrics_to_analyze = [
            # Basic metrics
            'age', 'minutes', 'minutes_90s',
            
            # Goals and assists
            'goals', 'assists', 'goals_per90', 'assists_per90', 'goals_assists_per90',
            
            # Expected Goals
            'expected_goals', 'expected_assists', 'expected_goals_per90', 'expected_assists_per90',
            'expected_goals_assists_per90', 'no_penalty_expected_goals_plus_expected_assists',
            
            # Passes
            'passes_completed', 'passes', 'passes_pct', 'passes_progressive_distance',
            'passes_completed_long', 'passes_long', 'passes_pct_long',
            'progressive_passes', 'progressive_passes_received',
            
            # Dribbles and carries
            'progressive_carries',
            
            # Defensive
            'tackles', 'tackles_won', 'challenge_tackles', 'challenges', 'challenge_tackles_pct',
            'challenges_lost', 'blocks', 'blocked_shots', 'blocked_passes',
            'interceptions', 'tackles_interceptions', 'clearances', 'errors',
            
            # Goalkeepers
            'gk_goals_against', 'gk_pens_allowed', 'gk_free_kick_goals_against',
            'gk_corner_kick_goals_against', 'gk_own_goals_against', 'gk_psxg',
            'gk_psnpxg_per_shot_on_target_against'
        ]
        
        for metric in metrics_to_analyze:
            values = []
            for player in all_players:
                if metric in player and player[metric] is not None:
                    try:
                        values.append(float(player[metric]))
                    except (ValueError, TypeError):
                        continue
            
            if values:
                # Calcular percentil 95
                sorted_values = sorted(values)
                p95_index = int(0.95 * len(sorted_values))
                percentiles[metric] = sorted_values[min(p95_index, len(sorted_values) - 1)]
                print(f"  {metric}: P95 = {percentiles[metric]:.2f} (de {len(values)} valores)")
            else:
                # Valor por defecto si no hay datos
                percentiles[metric] = 100
                print(f"  {metric}: No data, using default value 100")
        
        # Cache the result
        _METRICS_PERCENTILES_95_CACHE = percentiles
        print(f"95th percentiles calculated and cached for {len(percentiles)} metrics")
        return percentiles
        
    except Exception as e:
        print(f"Error calculating percentiles: {e}")
        # Default values in case of error
        _METRICS_PERCENTILES_95_CACHE = {
            # Basic metrics
            'age': 35, 'minutes': 3000, 'minutes_90s': 40,
            
            # Goals and assists
            'goals': 20, 'assists': 15, 'goals_per90': 1.0, 'assists_per90': 0.8, 'goals_assists_per90': 1.5,
            
            # Expected Goals
            'expected_goals': 20, 'expected_assists': 15, 'expected_goals_per90': 0.8, 'expected_assists_per90': 0.8,
            'expected_goals_assists_per90': 1.5, 'no_penalty_expected_goals_plus_expected_assists': 30,
            
            # Passes
            'passes_completed': 2000, 'passes': 2500, 'passes_pct': 95, 'passes_progressive_distance': 10000,
            'passes_completed_long': 200, 'passes_long': 300, 'passes_pct_long': 80,
            'progressive_passes': 200, 'progressive_passes_received': 300,
            
            # Dribbles and carries
            'progressive_carries': 150,
            
            # Defensive
            'tackles': 100, 'tackles_won': 50, 'challenge_tackles': 30, 'challenges': 80, 'challenge_tackles_pct': 50,
            'challenges_lost': 50, 'blocks': 40, 'blocked_shots': 5, 'blocked_passes': 35,
            'interceptions': 30, 'tackles_interceptions': 80, 'clearances': 40, 'errors': 5,
            
            # Goalkeepers
            'gk_goals_against': 50, 'gk_pens_allowed': 5, 'gk_free_kick_goals_against': 3,
            'gk_corner_kick_goals_against': 10, 'gk_own_goals_against': 2, 'gk_psxg': 50,
            'gk_psnpxg_per_shot_on_target_against': 0.8
        }
        return _METRICS_PERCENTILES_95_CACHE

def dashboard_radar_single(player_data: dict, selected_metrics: List[str] = None) -> dict:
    """
    Creates an individual radar chart for the manual search dashboard using mplsoccer
    
    Parameters
    ----------
    player_data : dict
        Player data directly from the API (without 'stats' field)
    selected_metrics : List[str]
        List of metrics selected by the user
        
    Returns
    -------
    dict
        Dictionary with text and attachments (chart URL)
    """
    # Data comes directly from the player, not in a 'stats' field
    stats = player_data  # Use player data directly
    player_name = player_data['full_name']
    team = player_data['club']
    position = player_data['position']
    nationality = player_data['nationality']
    
    # If no metrics specified, use defaults
    if not selected_metrics:
        selected_metrics = ['age', 'goals', 'assists', 'minutes_90s', 'goals_per90']
    
    # Filter available metrics
    available_metrics = [m for m in selected_metrics if m in stats]
    if not available_metrics:
        available_metrics = ['age', 'goals', 'assists', 'minutes_90s']
    
    # Prepare data for radar
    labels, vals = [], []
    
    for metric in available_metrics:
        if metric in stats and stats[metric] is not None:
            labels.append(metric.replace('_', ' ').title())
            vals.append(float(stats[metric]))
    
    if not labels:
        return {
            "text": f"No metrics available for {player_name}",
            "attachments": []
        }
    
    # Calculate maximum values based on selected player + 1%
    max_vals = []
    for val in vals:
        max_val = val * 1.01  # Player value + 1%
        max_vals.append(max_val)
    
    # Create radar using mplsoccer
    try:
        vals_arr = np.array(vals, dtype=float)
        low = np.zeros_like(vals_arr)
        high = max_vals

        # Create radar with mplsoccer
        radar = Radar(labels, low, high,
                    round_int=[False]*len(labels),
                    num_rings=5, 
                    ring_width=1, center_circle_radius=1)

        # Crear la figura usando grid de mplsoccer
        fig, axs = grid(figheight=14, grid_height=0.915, title_height=0.06, endnote_height=0.025,
                        title_space=0, endnote_space=0, grid_key='radar', axis=False)

        # Plotear el radar
        radar.setup_axis(ax=axs['radar'])
        rings_inner = radar.draw_circles(ax=axs['radar'], facecolor='#f0f0f0', edgecolor='#d0d0d0')
        radar_output = radar.draw_radar(vals_arr, ax=axs['radar'],
                                        kwargs_radar={'facecolor': '#aa65b2', 'alpha': 0.8},
                                        kwargs_rings={'facecolor': '#e0e0e0', 'alpha': 0.4})
        radar_poly, rings_outer, vertices = radar_output
        range_labels = radar.draw_range_labels(ax=axs['radar'], fontsize=25,
                                            fontproperties=robotto_thin.prop if robotto_thin else None)
        param_labels = radar.draw_param_labels(ax=axs['radar'], fontsize=25,
                                            fontproperties=robotto_bold.prop if robotto_bold else None)

        # Titles and text
        endnote_text = axs['endnote'].text(0.99, 1.4, 'Inspired By: StatsBomb / Rami Moghadam', fontsize=15,
                                    fontproperties=robotto_thin.prop, ha='right', va='center')
        endnote_text2 = axs['endnote'].text(0.99, 0.7, 'Created by: Enrique Revuelta - Smart Scout App', fontsize=15,
                                        fontproperties=robotto_thin.prop, ha='right', va='center')
        endnote_text2 = axs['endnote'].text(0.99, 0.0, 'Data Source: FBref.com', fontsize=15,
                                        fontproperties=robotto_thin.prop, ha='right', va='center')
        
        title1_text = axs['title'].text(0.01, 0.65, player_name, fontsize=25,
                                        fontproperties=robotto_bold.prop if robotto_bold else None, ha='left', va='center')
        title2_text = axs['title'].text(0.01, 0.25, nationality, fontsize=20,
                                        fontproperties=robotto_thin.prop if robotto_thin else None,
                                        ha='left', va='center', color='#B6282F')
        title3_text = axs['title'].text(0.99, 0.65, team, fontsize=25,
                                        fontproperties=robotto_bold.prop if robotto_bold else None, ha='right', va='center')
        title4_text = axs['title'].text(0.99, 0.25, position, fontsize=20,
                                        fontproperties=robotto_thin.prop if robotto_thin else None,
                                        ha='right', va='center', color='#B6282F')

        # Save the chart
        chart_path = f'/app/media/charts/radar_single_{player_data["id"]}_{int(time.time())}.png'
        os.makedirs(os.path.dirname(chart_path), exist_ok=True)
        fig.savefig(chart_path, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        
        # URL relativa para el template
        chart_url = chart_path.replace('/app/media', '/media')
        
        return {
            "text": f"Radar chart for {player_name}",
            "attachments": [{"type": "image", "url": chart_url}]
        }
        
    except Exception as e:
        print(f"Error creating radar chart: {e}")
        return {
            "text": f"Error generating chart for {player_name}",
            "attachments": []
        }


def dashboard_radar_comparison(players_data: List[dict], selected_metrics: List[str] = None) -> dict:
    """
    Creates a comparative radar chart for the manual search dashboard using mplsoccer
    
    Parameters
    ----------
    players_data : List[dict]
        List of player data directly from the API (without 'stats' field)
    selected_metrics : List[str]
        List of metrics selected by the user
        
    Returns
    -------
    dict
        Dictionary with text and attachments (chart URL)
    """
    if not players_data:
        return {"text": "No players to compare", "attachments": []}
    
    if len(players_data) > 3:
        return {"text": "Maximum 3 players to compare", "attachments": []}
    
    # Si no se especifican métricas, usar las por defecto
    if not selected_metrics:
        selected_metrics = ['age', 'goals', 'assists', 'minutes_90s', 'goals_per90']
    
    # Prepare data for all players
    all_players_data = []
    for player_data in players_data:
        # Data comes directly from the player, not in a 'stats' field
        stats = player_data  # Use player data directly
        player_name = player_data['full_name']
        team = player_data['club']
        position = player_data['position']
        nationality = player_data['nationality']
        
        # Filter available metrics
        available_metrics = [m for m in selected_metrics if m in stats]
        if not available_metrics:
            available_metrics = ['age', 'goals', 'assists', 'minutes_90s']
        
        # Prepare data for radar
        labels, vals = [], []
        
        for metric in available_metrics:
            if metric in stats and stats[metric] is not None:
                labels.append(metric.replace('_', ' ').title())
                vals.append(float(stats[metric]))
        
        if labels:  # Only add if there are available metrics
            all_players_data.append({
                'name': player_name,
                'team': team,
                'position': position,
                'nationality': nationality,
                'labels': labels,
                'vals': vals
            })
    
    if not all_players_data:
        return {"text": "No metrics available for comparison", "attachments": []}
    
    # Use labels from the first player (all should have the same)
    labels = all_players_data[0]['labels']
    
    # Calculate maximum values based on the maximum of all selected players + 1%
    max_vals = []
    for i, metric_label in enumerate(labels):
        # Find the maximum value for this metric among all players
        max_val = 0
        for player_data in all_players_data:
            if i < len(player_data['vals']):
                max_val = max(max_val, player_data['vals'][i])
        
        # Add 1% so the chart doesn't look tight
        max_val = max_val * 1.01
        max_vals.append(max_val)
    
    # Create radar using mplsoccer
    try:
        # Prepare data for mplsoccer
        low = [0] * len(labels)
        high = max_vals
        
        # Create radar with mplsoccer
        radar = Radar(labels, low, high,
                    round_int=[False]*len(labels),
                    num_rings=5, 
                    ring_width=1, center_circle_radius=1)

        
        # Creating the figure using the grid function from mplsoccer:
        fig, axs = grid(figheight=14, grid_height=0.915, title_height=0.06, endnote_height=0.025,
                        title_space=0, endnote_space=0, grid_key='radar', axis=False)

    
        # Plot the radar
        radar.setup_axis(ax=axs['radar'])
        rings_inner = radar.draw_circles(ax=axs['radar'], facecolor='#f0f0f0', edgecolor='#d0d0d0')
        
        # Colors for each player
        colors = ['#00f2c1', '#d80499', '#ff6b35']
        
        # Plot each player
        for i, player_data in enumerate(all_players_data):
            vals_arr = np.array(player_data['vals'], dtype=float)
            color = colors[i % len(colors)]
            
            radar_output = radar.draw_radar(vals_arr, ax=axs['radar'],
                                            kwargs_radar={'facecolor': color, 'alpha': 0.9-((i/10)*3)},
                                            kwargs_rings={'facecolor': '#e0e0e0', 'alpha': 0.4})
            radar_poly, rings_outer, vertices = radar_output
            
            # Points in the vertices
            axs['radar'].scatter(vertices[:, 0], vertices[:, 1],
                                c=color, edgecolors='#6d6c6d', marker='o', s=150, zorder=2)
        
        # Labels and ranges
        range_labels = radar.draw_range_labels(ax=axs['radar'], fontsize=25,
                                            fontproperties=robotto_thin.prop if robotto_thin else None)
        param_labels = radar.draw_param_labels(ax=axs['radar'], fontsize=25,
                                            fontproperties=robotto_thin.prop if robotto_thin else None)
        
        # Legend
        legend_elements = []
        for i, player_data in enumerate(all_players_data):
            legend_elements.append(plt.Line2D([0], [0], color=colors[i % len(colors)], lw=4, 
                                            label=f"{player_data['name']} ({player_data['team']})"))
        
        axs['radar'].legend(handles=legend_elements, loc='upper right', bbox_to_anchor=(1.1, 1.0))
        
        # Titles and text
        endnote_text = axs['endnote'].text(0.99, 1.4, 'Inspired By: StatsBomb / Rami Moghadam', fontsize=15,
                                    fontproperties=robotto_thin.prop, ha='right', va='center')
        endnote_text2 = axs['endnote'].text(0.99, 0.7, 'Created by: Enrique Revuelta - Smart Scout App', fontsize=15,
                                        fontproperties=robotto_thin.prop, ha='right', va='center')
        endnote_text2 = axs['endnote'].text(0.99, 0.0, 'Data Source: FBref.com', fontsize=15,
                                        fontproperties=robotto_thin.prop, ha='right', va='center')
        
        # Main title
        title_text = axs['title'].text(0.5, 0.65, 'Player Comparison', fontsize=25,
                                      fontproperties=robotto_bold.prop if robotto_bold else None, ha='center', va='center')
        
        # Save the chart
        chart_path = f'/app/media/charts/radar_comparison_{int(time.time())}.png'
        os.makedirs(os.path.dirname(chart_path), exist_ok=True)
        fig.savefig(chart_path, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        
        # Relative URL for the template
        chart_url = chart_path.replace('/app/media', '/media')
        
        return {
            "text": f"Comparison of {len(all_players_data)} players",
            "attachments": [{"type": "image", "url": chart_url}]
        }
        
    except Exception as e:
        print(f"Error creating comparative radar chart: {e}")
        return {
            "text": "Error generating comparative chart",
            "attachments": []
        }
