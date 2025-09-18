"""
dashboard_viz_tools.py - Herramientas de visualización para el dashboard de búsqueda manual

Funciones específicas para el dashboard de comparación de jugadores:
- radar_chart_single: Radar individual para 1 jugador
- radar_chart_comparison: Radar comparativo para 2-3 jugadores con leyenda
- get_available_metrics: Obtener métricas disponibles por posición
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
    """Devuelve el modelo Django si Django está configurado"""
    try:
        from django.conf import settings
        if settings.configured:
            module, cls = name.rsplit(".", 1)
            return getattr(importlib.import_module(module), cls)
    except Exception:
        return None

TempChart = _django_model("apps.charts.models.TempChart")

# Fuentes - inicializar de manera segura
try:
    robotto_bold = FontManager('apps/agent_service/fonts/robotto_bold.ttf')
    robotto_thin = FontManager('apps/agent_service/fonts/robotto_thin.ttf')
except:
    # Fallback a fuentes por defecto si no están disponibles
    robotto_bold = None
    robotto_thin = None

# Métricas del radar (6 métricas genéricas)
RADAR_METRICS = [
    ['Edad', 'age', 35],
    ['Min/Juego', None, 90],  # None significa que se calcula
    ['Partidos 90s', 'minutes_90s', 40],
    ['Goles', 'goals', 30],
    ['Asistencias', 'assists', 20],
    ['G+A', None, 50],  # Goles + Asistencias
]

# Métricas por posición (para el selector)
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
    """Guarda el gráfico y devuelve la URL"""
    charts_dir = Path(settings.MEDIA_ROOT) / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    final = charts_dir / f"{uuid4().hex}.png"
    fig.savefig(final, dpi=300, bbox_inches="tight", facecolor="white")

    chart = TempChart.objects.create(image=f"charts/{final.name}")
    return {
        "text": f"Aquí tienes el gráfico{': ' + label if label else ''}.",
        "attachments": [
            {"type": "image", "url": chart.image.url}
        ],
    }



def get_available_metrics(position: str) -> List[str]:
    """
    Obtiene las métricas disponibles para una posición específica
    
    Parameters
    ----------
    position : str
        Posición del jugador (GK, DF, MF, FW)
        
    Returns
    -------
    List[str]
        Lista de métricas disponibles para esa posición
    """
    return POSITION_METRICS.get(position.upper(), POSITION_METRICS['MF'])

def get_all_metrics() -> Dict[str, List[str]]:
    """
    Obtiene todas las métricas disponibles por posición
    
    Returns
    -------
    Dict[str, List[str]]
        Diccionario con métricas por posición
    """
    return POSITION_METRICS


# =============================================================================
# FUNCIONES ESPECÍFICAS PARA EL DASHBOARD DE BÚSQUEDA MANUAL
# =============================================================================

# Cache global para los percentiles 95 - se calcula una sola vez
_METRICS_PERCENTILES_95_CACHE = None

def get_metrics_percentiles_95() -> Dict[str, float]:
    """
    Obtiene el percentil 95 de todas las métricas para normalización correcta
    Se calcula una sola vez y se cachea para evitar recálculos
    
    Returns
    -------
    Dict[str, float]
        Diccionario con percentil 95 de cada métrica
    """
    global _METRICS_PERCENTILES_95_CACHE
    
    # Si ya está cacheado, devolverlo
    if _METRICS_PERCENTILES_95_CACHE is not None:
        return _METRICS_PERCENTILES_95_CACHE
    
    try:
        import requests
        from apps.dashboard.search_services import API_BASE_URL
        
        print("Calculando percentiles 95 de toda la base de datos...")
        
        # Obtener TODOS los jugadores para calcular percentiles correctos
        response = requests.get(f"{API_BASE_URL}/players/all?limit=5000", timeout=60)
        response.raise_for_status()
        
        all_players = response.json().get('players', [])
        print(f"Obtenidos {len(all_players)} jugadores para calcular percentiles")
        
        if not all_players:
            # Valores por defecto si no hay datos
            _METRICS_PERCENTILES_95_CACHE = {
                # Métricas básicas
                'age': 35, 'minutes': 3000, 'minutes_90s': 40,
                
                # Goles y asistencias
                'goals': 20, 'assists': 15, 'goals_per90': 1.0, 'assists_per90': 0.8, 'goals_assists_per90': 1.5,
                
                # Expected Goals
                'expected_goals': 20, 'expected_assists': 15, 'expected_goals_per90': 0.8, 'expected_assists_per90': 0.8,
                'expected_goals_assists_per90': 1.5, 'no_penalty_expected_goals_plus_expected_assists': 30,
                
                # Pases
                'passes_completed': 2000, 'passes': 2500, 'passes_pct': 95, 'passes_progressive_distance': 10000,
                'passes_completed_long': 200, 'passes_long': 300, 'passes_pct_long': 80,
                'progressive_passes': 200, 'progressive_passes_received': 300,
                
                # Regates y carreras
                'progressive_carries': 150,
                
                # Defensivas
                'tackles': 100, 'tackles_won': 50, 'challenge_tackles': 30, 'challenges': 80, 'challenge_tackles_pct': 50,
                'challenges_lost': 50, 'blocks': 40, 'blocked_shots': 5, 'blocked_passes': 35,
                'interceptions': 30, 'tackles_interizations': 80, 'clearances': 40, 'errors': 5,
                
                # Porteros
                'gk_goals_against': 50, 'gk_pens_allowed': 5, 'gk_free_kick_goals_against': 3,
                'gk_corner_kick_goals_against': 10, 'gk_own_goals_against': 2, 'gk_psxg': 50,
                'gk_psnpxg_per_shot_on_target_against': 0.8
            }
            return _METRICS_PERCENTILES_95_CACHE
        
        # Calcular percentil 95 para cada métrica
        percentiles = {}
        
        # Todas las métricas numéricas disponibles en el sistema
        metrics_to_analyze = [
            # Métricas básicas
            'age', 'minutes', 'minutes_90s',
            
            # Goles y asistencias
            'goals', 'assists', 'goals_per90', 'assists_per90', 'goals_assists_per90',
            
            # Expected Goals
            'expected_goals', 'expected_assists', 'expected_goals_per90', 'expected_assists_per90',
            'expected_goals_assists_per90', 'no_penalty_expected_goals_plus_expected_assists',
            
            # Pases
            'passes_completed', 'passes', 'passes_pct', 'passes_progressive_distance',
            'passes_completed_long', 'passes_long', 'passes_pct_long',
            'progressive_passes', 'progressive_passes_received',
            
            # Regates y carreras
            'progressive_carries',
            
            # Defensivas
            'tackles', 'tackles_won', 'challenge_tackles', 'challenges', 'challenge_tackles_pct',
            'challenges_lost', 'blocks', 'blocked_shots', 'blocked_passes',
            'interceptions', 'tackles_interceptions', 'clearances', 'errors',
            
            # Porteros
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
                print(f"  {metric}: Sin datos, usando valor por defecto 100")
        
        # Cachear el resultado
        _METRICS_PERCENTILES_95_CACHE = percentiles
        print(f"Percentiles 95 calculados y cacheados para {len(percentiles)} métricas")
        return percentiles
        
    except Exception as e:
        print(f"Error calculando percentiles: {e}")
        # Valores por defecto en caso de error
        _METRICS_PERCENTILES_95_CACHE = {
            # Métricas básicas
            'age': 35, 'minutes': 3000, 'minutes_90s': 40,
            
            # Goles y asistencias
            'goals': 20, 'assists': 15, 'goals_per90': 1.0, 'assists_per90': 0.8, 'goals_assists_per90': 1.5,
            
            # Expected Goals
            'expected_goals': 20, 'expected_assists': 15, 'expected_goals_per90': 0.8, 'expected_assists_per90': 0.8,
            'expected_goals_assists_per90': 1.5, 'no_penalty_expected_goals_plus_expected_assists': 30,
            
            # Pases
            'passes_completed': 2000, 'passes': 2500, 'passes_pct': 95, 'passes_progressive_distance': 10000,
            'passes_completed_long': 200, 'passes_long': 300, 'passes_pct_long': 80,
            'progressive_passes': 200, 'progressive_passes_received': 300,
            
            # Regates y carreras
            'progressive_carries': 150,
            
            # Defensivas
            'tackles': 100, 'tackles_won': 50, 'challenge_tackles': 30, 'challenges': 80, 'challenge_tackles_pct': 50,
            'challenges_lost': 50, 'blocks': 40, 'blocked_shots': 5, 'blocked_passes': 35,
            'interceptions': 30, 'tackles_interceptions': 80, 'clearances': 40, 'errors': 5,
            
            # Porteros
            'gk_goals_against': 50, 'gk_pens_allowed': 5, 'gk_free_kick_goals_against': 3,
            'gk_corner_kick_goals_against': 10, 'gk_own_goals_against': 2, 'gk_psxg': 50,
            'gk_psnpxg_per_shot_on_target_against': 0.8
        }
        return _METRICS_PERCENTILES_95_CACHE

def dashboard_radar_single(player_data: dict, selected_metrics: List[str] = None) -> dict:
    """
    Crea un radar chart individual para el dashboard de búsqueda manual usando mplsoccer
    
    Parameters
    ----------
    player_data : dict
        Datos del jugador directamente de la API (sin campo 'stats')
    selected_metrics : List[str]
        Lista de métricas seleccionadas por el usuario
        
    Returns
    -------
    dict
        Diccionario con text y attachments (URL del gráfico)
    """
    # Los datos vienen directamente del jugador, no en un campo 'stats'
    stats = player_data  # Usar los datos del jugador directamente
    player_name = player_data['full_name']
    team = player_data['club']
    position = player_data['position']
    nationality = player_data['nationality']
    
    # Si no se especifican métricas, usar las por defecto
    if not selected_metrics:
        selected_metrics = ['age', 'goals', 'assists', 'minutes_90s', 'goals_per90']
    
    # Filtrar métricas disponibles
    available_metrics = [m for m in selected_metrics if m in stats]
    if not available_metrics:
        available_metrics = ['age', 'goals', 'assists', 'minutes_90s']
    
    # Preparar datos para el radar
    labels, vals = [], []
    
    for metric in available_metrics:
        if metric in stats and stats[metric] is not None:
            labels.append(metric.replace('_', ' ').title())
            vals.append(float(stats[metric]))
    
    if not labels:
        return {
            "text": f"No hay métricas disponibles para {player_name}",
            "attachments": []
        }
    
    # Calcular valores máximos basados en el jugador seleccionado + 1%
    max_vals = []
    for val in vals:
        max_val = val * 1.01  # Valor del jugador + 1%
        max_vals.append(max_val)
    
    # Crear el radar usando mplsoccer
    try:
        vals_arr = np.array(vals, dtype=float)
        low = np.zeros_like(vals_arr)
        high = max_vals

        # Crear el radar con mplsoccer
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
                                            fontproperties=robotto_thin.prop if robotto_thin else None)

        # Títulos y texto
        endnote_text = axs['endnote'].text(0.99, 1.4, 'Smart Scout Dashboard', fontsize=15,
                                        fontproperties=robotto_thin.prop if robotto_thin else None, ha='right', va='center')
        endnote_text2 = axs['endnote'].text(0.99, 0.7, 'Data Source: FBref.com', fontsize=15,
                                        fontproperties=robotto_thin.prop if robotto_thin else None, ha='right', va='center')
        
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

        # Guardar el gráfico
        chart_path = f'/app/media/charts/radar_single_{player_data["id"]}_{int(time.time())}.png'
        os.makedirs(os.path.dirname(chart_path), exist_ok=True)
        fig.savefig(chart_path, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        
        # URL relativa para el template
        chart_url = chart_path.replace('/app/media', '/media')
        
        return {
            "text": f"Radar chart de {player_name}",
            "attachments": [{"type": "image", "url": chart_url}]
        }
        
    except Exception as e:
        print(f"Error creando radar chart: {e}")
        return {
            "text": f"Error generando gráfico para {player_name}",
            "attachments": []
        }


def dashboard_radar_comparison(players_data: List[dict], selected_metrics: List[str] = None) -> dict:
    """
    Crea un radar chart comparativo para el dashboard de búsqueda manual usando mplsoccer
    
    Parameters
    ----------
    players_data : List[dict]
        Lista de datos de jugadores directamente de la API (sin campo 'stats')
    selected_metrics : List[str]
        Lista de métricas seleccionadas por el usuario
        
    Returns
    -------
    dict
        Diccionario con text y attachments (URL del gráfico)
    """
    if not players_data:
        return {"text": "No hay jugadores para comparar", "attachments": []}
    
    if len(players_data) > 3:
        return {"text": "Máximo 3 jugadores para comparar", "attachments": []}
    
    # Si no se especifican métricas, usar las por defecto
    if not selected_metrics:
        selected_metrics = ['age', 'goals', 'assists', 'minutes_90s', 'goals_per90']
    
    # Preparar datos para todos los jugadores
    all_players_data = []
    for player_data in players_data:
        # Los datos vienen directamente del jugador, no en un campo 'stats'
        stats = player_data  # Usar los datos del jugador directamente
        player_name = player_data['full_name']
        team = player_data['club']
        position = player_data['position']
        nationality = player_data['nationality']
        
        # Filtrar métricas disponibles
        available_metrics = [m for m in selected_metrics if m in stats]
        if not available_metrics:
            available_metrics = ['age', 'goals', 'assists', 'minutes_90s']
        
        # Preparar datos para el radar
        labels, vals = [], []
        
        for metric in available_metrics:
            if metric in stats and stats[metric] is not None:
                labels.append(metric.replace('_', ' ').title())
                vals.append(float(stats[metric]))
        
        if labels:  # Solo añadir si hay métricas disponibles
            all_players_data.append({
                'name': player_name,
                'team': team,
                'position': position,
                'nationality': nationality,
                'labels': labels,
                'vals': vals
            })
    
    if not all_players_data:
        return {"text": "No hay métricas disponibles para comparar", "attachments": []}
    
    # Usar las etiquetas del primer jugador (todos deberían tener las mismas)
    labels = all_players_data[0]['labels']
    
    # Calcular valores máximos basados en el máximo de todos los jugadores seleccionados + 1%
    max_vals = []
    for i, metric_label in enumerate(labels):
        # Encontrar el valor máximo para esta métrica entre todos los jugadores
        max_val = 0
        for player_data in all_players_data:
            if i < len(player_data['vals']):
                max_val = max(max_val, player_data['vals'][i])
        
        # Añadir 1% para que el gráfico no quede justo
        max_val = max_val * 1.01
        max_vals.append(max_val)
    
    # Crear el radar usando mplsoccer
    try:
        # Preparar datos para mplsoccer
        low = [0] * len(labels)
        high = max_vals
        
        # Crear el radar con mplsoccer
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
        
        # Colores para cada jugador
        colors = ['#00f2c1', '#d80499', '#ff6b35']
        
        # Plotear cada jugador
        for i, player_data in enumerate(all_players_data):
            vals_arr = np.array(player_data['vals'], dtype=float)
            color = colors[i % len(colors)]
            
            radar_output = radar.draw_radar(vals_arr, ax=axs['radar'],
                                            kwargs_radar={'facecolor': color, 'alpha': 0.8},
                                            kwargs_rings={'facecolor': '#e0e0e0', 'alpha': 0.4})
            radar_poly, rings_outer, vertices = radar_output
            
            # Puntos en los vértices
            axs['radar'].scatter(vertices[:, 0], vertices[:, 1],
                                c=color, edgecolors='#6d6c6d', marker='o', s=150, zorder=2)
        
        # Etiquetas y rangos
        range_labels = radar.draw_range_labels(ax=axs['radar'], fontsize=25,
                                            fontproperties=robotto_thin.prop if robotto_thin else None)
        param_labels = radar.draw_param_labels(ax=axs['radar'], fontsize=25,
                                            fontproperties=robotto_thin.prop if robotto_thin else None)
        
        # Leyenda
        legend_elements = []
        for i, player_data in enumerate(all_players_data):
            legend_elements.append(plt.Line2D([0], [0], color=colors[i % len(colors)], lw=4, 
                                            label=f"{player_data['name']} ({player_data['team']})"))
        
        axs['radar'].legend(handles=legend_elements, loc='upper right', bbox_to_anchor=(1.1, 1.0))
        
        # Títulos y texto
        endnote_text = axs['endnote'].text(0.99, 1.4, 'Smart Scout Dashboard', fontsize=15,
                                        fontproperties=robotto_thin.prop if robotto_thin else None, ha='right', va='center')
        endnote_text2 = axs['endnote'].text(0.99, 0.7, 'Data Source: FBref.com', fontsize=15,
                                        fontproperties=robotto_thin.prop if robotto_thin else None, ha='right', va='center')
        
        # Título principal
        title_text = axs['title'].text(0.5, 0.65, 'Comparación de Jugadores', fontsize=25,
                                      fontproperties=robotto_bold.prop if robotto_bold else None, ha='center', va='center')
        
        # Guardar el gráfico
        chart_path = f'/app/media/charts/radar_comparison_{int(time.time())}.png'
        os.makedirs(os.path.dirname(chart_path), exist_ok=True)
        fig.savefig(chart_path, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        
        # URL relativa para el template
        chart_url = chart_path.replace('/app/media', '/media')
        
        return {
            "text": f"Comparación de {len(all_players_data)} jugadores",
            "attachments": [{"type": "image", "url": chart_url}]
        }
        
    except Exception as e:
        print(f"Error creando radar chart comparativo: {e}")
        return {
            "text": "Error generando gráfico comparativo",
            "attachments": []
        }
