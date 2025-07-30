from __future__ import annotations
"""viz_tools.py  ·  Radar & Pizza charts (mplsoccer ≥ 1.4)

Exposes two LangChain tools that generate PNG files with **mplsoccer**:

* **radar_chart**  – 6 métricas genéricas (edad, min/juego, etc.)
* **pizza_chart**  – 9 métricas por rol con porciones codificadas por color
  (🌿 verde = ataque, 🔵 azul = posesión, 🟠 naranja = defensa)

Each tool returns the *filesystem path* to a temporary PNG stored under `/tmp`;
Django/FastAPI should serve the file and embed an `<img>` tag.

All metrics are expected to be already comparable (per‑90 or cumulative where
appropriate). No global normalisation is applied beyond flipping defensive
metrics where a lower raw value is better (see `INVERSE`).
"""
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
import matplotlib.pyplot as plt
import numpy as np
from langchain.tools import tool
from mplsoccer import PyPizza, Radar, FontManager, grid
from apps.agent_service.players_service import player_stats
from django.conf import settings
from shutil import move

# ─── Opcional │ registrar la imagen en la BD SOLO cuando hay Django ───
import importlib

def _django_model(name):
    """
    Devuelve el modelo Django si Django está configurado;
    si no, devuelve None para que FastAPI no intente importarlo.
    """
    try:
        from django.conf import settings  # noqa: WPS433
        if settings.configured:
            module, cls = name.rsplit(".", 1)
            return getattr(importlib.import_module(module), cls)
    except Exception:         # FastAPI: settings no existe
        return None

TempChart = _django_model("apps.charts.models.TempChart")

# ────────────────────────────────────────────────────────────────────────────
# Fonts 
# ────────────────────────────────────────────────────────────────────────────
FONTS_PATH = Path(__file__).resolve().parent / "fonts"

serif_regular     = FontManager((FONTS_PATH / "serif_regular.ttf").as_uri())
serif_extra_light = FontManager((FONTS_PATH / "serif_extra_light.ttf").as_uri())
rubik_regular     = FontManager((FONTS_PATH / "rubik_regular.ttf").as_uri())
robotto_thin      = FontManager((FONTS_PATH / "robotto_thin.ttf").as_uri())
robotto_bold      = FontManager((FONTS_PATH / "robotto_bold.ttf").as_uri())
font_bold         = FontManager((FONTS_PATH / "RobotoSlab-Bold.ttf").as_uri())
font_normal       = FontManager((FONTS_PATH / "RobotoSlab-Regular.ttf").as_uri())
font_italic       = FontManager((FONTS_PATH / "RobotoSlab-Italic.ttf").as_uri())

# ────────────────────────────────────────────────────────────────────────────
# Colour palette (light tones)
# ────────────────────────────────────────────────────────────────────────────
ATT_CLR = "#8ED18E"   # light green  – attacking
POS_CLR = "#9CCAF9"   # light blue   – possession
DEF_CLR = "#F9B97C"   # light orange – defending
COLORS = {"att": ATT_CLR, "pos": POS_CLR, "def": DEF_CLR}
TEXT_CLR = "#000000"

# ────────────────────────────────────────────────────────────────────────────
# Metric definitions
# ────────────────────────────────────────────────────────────────────────────
RADAR_METRICS: List[Tuple[str, str, Any | None]] = [
    ("Edad", "age", 45),
    ("Min/juego", None, 100),          # minutes ÷ 90s
    ("Partidos_90s", "minutes_90s", 50),
    ("Goles", "goals", 50),
    ("Asist", "assists", 20),
    ("G+A", None, 50),
]

# label, df‑column, category
ROLE_METRICS = {
    'GK': [
          ['PSxG_ev', 'gk_psxg', 'def', 73.5],
          ['GA', 'gk_goals_against', 'def', 77.0],
          ['Pens', 'gk_pens_allowed', 'def', 13.0],
          ['GA_FK', 'gk_free_kick_goals_against', 'def', 3.0],
          ['GA_CK', 'gk_corner_kick_goals_against', 'def', 11.0],
          ['OwnGA', 'gk_own_goals_against', 'def', 5.0],
          ['ProgDist', 'passes_progressive_distance', 'pos', 28154.0],
          ['%Pass', 'passes_pct', 'pos', 100.0],
          ['LongCmp', 'passes_completed_long', 'pos', 462.0]
    ],
     'DF': [
          ['Interc', 'interceptions', 'def', 72.0],
          ['Tackles', 'tackles', 'def', 151.0],
          ['Tk_Won', 'tackles_won', 'def', 99.0],
          ['BlkShot', 'blocked_shots', 'def', 57.0],
          ['Clear', 'clearances', 'def', 352.0],
          ['Duel%', 'challenge_tackles_pct', 'def', 100.0],
          ['ProgDist', 'passes_progressive_distance', 'pos', 28154.0],
          ['%Pass', 'passes_pct', 'pos', 100.0],
          ['LongCmp', 'passes_completed_long', 'pos', 462.0]
     ],
     'MF': [
          ['xA/90', 'expected_assists_per90', 'att', 2.0],
          ['G+A/90', 'goals_assists_per90', 'att', 3.0],
          ['xG/90', 'expected_goals_per90', 'att', 1.5],
          ['ProgCarr', 'progressive_carries', 'pos', 213.0],
          ['ProgDist', 'passes_progressive_distance', 'pos', 28154.0],
          ['%Pass', 'passes_pct', 'pos', 100.0],
          ['Interc', 'interceptions', 'def', 72.0],
          ['Tk+Int', 'tackles_interceptions', 'def', 207.0],
          ['Blocks', 'blocks', 'def', 77.0]
     ],
     'FW': [
          ['G/90', 'goals_per90', 'att', 1.5],
          ['xG/90', 'expected_goals_per90', 'att', 1.5],
          ['A/90', 'assists_per90', 'att', 2.0],
          ['G+A/90', 'goals_assists_per90', 'att', 3.0],
          ['xGA/90', 'expected_goals_assists_per90', 'att', 3.0],
          ['ProgRec', 'progressive_passes_received', 'pos', 488.0],
          ['ProgPass', 'progressive_passes', 'pos', 440.0],
          ['ProgCarr', 'progressive_carries', 'pos', 213.0],
          ['%Pass', 'passes_pct', 'pos', 100.0]
    ]
}

INVERSE = {
    "gk_goals_against", "gk_free_kick_goals_against",
    "gk_corner_kick_goals_against", "gk_own_goals_against",
}

# ────────────────────────────────────────────────────────────────────────────
# Utility: save figure
# ────────────────────────────────────────────────────────────────────────────

def _save(fig, *, label: str) -> dict:
    """Guarda el PNG, crea modelo y devuelve dict para el agente."""
    # 1. PNG temporal
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    fig.savefig(tmp.name, dpi=300, bbox_inches="tight", facecolor="white")
    tmp.close()

    # 2. Copiar a MEDIA_ROOT/charts/
    charts_dir = Path(settings.MEDIA_ROOT) / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    final = charts_dir / Path(tmp.name).name
    move(tmp.name, final)

    # 3. Registrar en BD
    chart = TempChart.objects.create(image=f"charts/{final.name}")

    # 4. Dict que entiende nuestro output‑parser
    return {
        "text": f"Aquí tienes el gráfico de {label}:",
        "attachments": [
            {"type": "image", "url": chart.image.url}
        ]
    }

# ────────────────────────────────────────────────────────────────────────────
# Radar chart tool
# ────────────────────────────────────────────────────────────────────────────
#@tool(description=(
#    "Radar de 6 métricas genéricas para un jugador (edad, minutos/juego, partidos_90s, goles, asistencias, G+A)."
#    "Requiere:  un dict con las player stats, el player_name, club, position (role) y nationality.")
#    )
def radar_chart(
    player_name: str,
    *,
    stats: Optional[Dict[str, Any]] = None,
    team: str = "",
    position: str | None = None,
    nationality: str |None = None,
) -> str:
    """Create a radar chart for a single player.

    Parameters
    ----------
    stats : dict
        A DataFrame row converted to dict (`row.to_dict()`).
    player_name, club, position (role), nationality : str
        Metadata for figure title and optional badge.
    """
    if stats is None:
        fetched     = player_stats.invoke({"player_name": player_name})
        stats       = fetched["stats"]
        team        = team or fetched["stats"]["team"]
        position    = position or fetched["stats"]["position"]
        nationality = nationality or fetched["stats"]["nationality"]

    labels, vals, max_vals = [], [], []
    for label, col, max_val in RADAR_METRICS:
        if col is None and label == "G+A":
            v = stats.get("goals", 0) + stats.get("assists", 0)
        elif col is None:  # minutes per game
            games = stats.get("minutes_90s", 1) or 1
            v = stats.get("minutes", 0) / games
        else:
            v = stats.get(col, 0)
        labels.append(label)
        vals.append(float(v))
        max_vals.append(max_val)

    vals_arr = np.array(vals, dtype=float)
    low = np.zeros_like(vals_arr)
    high = max_vals

    params = [s[0] for s in RADAR_METRICS]

    lower_is_better = ['Miscontrol']

    radar = Radar(params, low, high,
                lower_is_better=lower_is_better,
                round_int=[False]*len(params),
                num_rings=5, 
                ring_width=1, center_circle_radius=1)

    # creating the figure using the grid function from mplsoccer:
    fig, axs = grid(figheight=14, grid_height=0.915, title_height=0.06, endnote_height=0.025,
                    title_space=0, endnote_space=0, grid_key='radar', axis=False)

    # plot the radar
    radar.setup_axis(ax=axs['radar'])
    rings_inner = radar.draw_circles(ax=axs['radar'], facecolor='#ffb2b2', edgecolor='#fc5f5f')
    radar_output = radar.draw_radar(vals_arr, ax=axs['radar'],
                                    kwargs_radar={'facecolor': '#aa65b2'},
                                    kwargs_rings={'facecolor': '#66d8ba'})
    radar_poly, rings_outer, vertices = radar_output
    range_labels = radar.draw_range_labels(ax=axs['radar'], fontsize=25,
                                        fontproperties=robotto_thin.prop)
    param_labels = radar.draw_param_labels(ax=axs['radar'], fontsize=25,
                                        fontproperties=robotto_thin.prop)
    endnote_text = axs['endnote'].text(0.99, 1.4, 'Inspired By: StatsBomb / Rami Moghadam', fontsize=15,
                                    fontproperties=robotto_thin.prop, ha='right', va='center')
    endnote_text2 = axs['endnote'].text(0.99, 0.7, 'Created by: Enrique Revuelta', fontsize=15,
                                    fontproperties=robotto_thin.prop, ha='right', va='center')
    endnote_text2 = axs['endnote'].text(0.99, 0.0, 'Data Source: FBref.com', fontsize=15,
                                    fontproperties=robotto_thin.prop, ha='right', va='center')
    title1_text = axs['title'].text(0.01, 0.65, player_name, fontsize=25,
                                    fontproperties=robotto_bold.prop, ha='left', va='center')
    title2_text = axs['title'].text(0.01, 0.25, nationality, fontsize=20,
                                    fontproperties=robotto_thin.prop,
                                    ha='left', va='center', color='#B6282F')
    title3_text = axs['title'].text(0.99, 0.65, team, fontsize=25,
                                    fontproperties=robotto_bold.prop, ha='right', va='center')
    title4_text = axs['title'].text(0.99, 0.25, position, fontsize=20,
                                    fontproperties=robotto_thin.prop,
                                    ha='right', va='center', color='#B6282F')

    return _save(fig, label=player_name)

# ────────────────────────────────────────────────────────────────────────────
# Pizza chart tool
# ────────────────────────────────────────────────────────────────────────────
#@tool(description=(
#        "Pizza chart de 9 métricas por rol (verde=ataque, azul=posesión, naranja=defensa)."
#        """Requiere: role (position) ('GK'|'DF'|'MF'|'FW') y stats (dict con las métricas), 
#        el player_name (full_name) y club (team)"""
#        )
#      )
def pizza_chart(
    player_name: str,
    *,
    role: str | None = None,
    stats: Optional[Dict[str, Any]] = None,
    team: str = "",
) -> str:
    """Crear un pizza plot coloreado por categoría para un jugador.

    Parameters
    ----------
    role : {'GK', 'DF', 'MF', 'FW'}
        Rol / posición del jugador.
    stats : dict
        Fila del DataFrame convertida a dict (`row.to_dict()`).
    player_name, team : str
        Metadatos para el encabezado del gráfico.

    Returns
    -------
    str
        Ruta del PNG temporal con el gráfico.
    """
    if stats is None or role is None:
        fetched = player_stats.invoke({"player_name": player_name})
        role    = role  or fetched["role"]
        stats   = stats or fetched["stats"]
        team    = team or fetched["team"]

    role = role.upper()
    if role not in ROLE_METRICS:
        raise ValueError(f"Rol '{role}' no soportado (GK, DF, MF, FW)")

    # ── valores y colores ───────────────────────────────────────────────────
    params, values, cats, max_vals = [], [], [], []
    for lbl, col, cat, max_val in ROLE_METRICS[role]:
        val = float(stats.get(col, 0.0))
        if col in INVERSE:          # invertir métricas donde menos es mejor
            val = -val
        params.append(lbl)
        values.append(val)
        cats.append(cat)
        max_vals.append(max_val)

    slice_colors = [COLORS[c] for c in cats]
    text_colors = ["#000000"] * len(cats)
    min_vals = [0.0] * len(max_vals)

    # instantiate PyPizza class
    baker = PyPizza(
        params=params,                  # list of parameters
        min_range=min_vals,        # min range values
        max_range=max_vals,        # max range values
        background_color="#EBEBE9",     # background color
        straight_line_color="#EBEBE9",  # color for straight lines
        straight_line_lw=1,             # linewidth for straight lines
        last_circle_lw=0,               # linewidth of last circle
        other_circle_lw=0,              # linewidth for other circles
        inner_circle_size=20            # size of inner circle
    )

    # plot pizza
    fig, ax = baker.make_pizza(
        values,                          # list of values
        figsize=(8, 8.5),                # adjust figsize according to your need
        color_blank_space="same",        # use same color to fill blank space
        slice_colors=slice_colors,       # color for individual slices
        value_colors=text_colors,        # color for the value-text
        value_bck_colors=slice_colors,   # color for the blank spaces
        blank_alpha=0.4,                 # alpha for blank-space colors
        kwargs_slices=dict(
            edgecolor="#F2F2F2", zorder=2, linewidth=1
        ),                               # values to be used when plotting slices
        kwargs_params=dict(
            color="#000000", fontsize=11,
            fontproperties=font_normal.prop, va="center"
        ),                               # values to be used when adding parameter
        kwargs_values=dict(
            color="#000000", fontsize=11,
            fontproperties=font_normal.prop, zorder=3,
            bbox=dict(
                edgecolor="#000000", facecolor="cornflowerblue",
                boxstyle="round,pad=0.2", lw=1
            )
        )                                # values to be used when adding parameter-values
    )

    # add title
    fig.text(
        0.515, 0.975, f"{player_name} - {team} - {role}", size=16,
        ha="center", fontproperties=font_bold.prop, color="#000000"
    )

    # add credits
    CREDIT_1 = "Data Source: fbref"
    CREDIT_2 = "Inspired by: @Worville, @FootballSlices, @somazerofc & @Soumyaj15209314"
    CREDIT_3 = "Created by: Enrique Revuelta"

    fig.text(
        0.99, 0.02, f"{CREDIT_3}\n{CREDIT_1}\n{CREDIT_2}", size=9,
        fontproperties=font_italic.prop, color="#000000",
        ha="right"
    )

    return _save(fig, label=player_name)

