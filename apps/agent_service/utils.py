# apps/agent_service/utils.py
import pandas as pd
import numpy as np
import markdown                
from django.utils.safestring import mark_safe

# ── 0 · Constantes de estilo ───────────────────────────────
GREEN_TXT = 'style="color:#198754;font-weight:600"'
RED_TXT   = 'style="color:#dc3545;font-weight:600"'

GREEN_BG  = 'style="background-color:#198754;color:#fff;font-weight:700"'
RED_BG    = 'style="background-color:#dc3545;color:#fff;font-weight:700"'

# elige si quieres *_TXT o *_BG:
WIN_STYLE = GREEN_BG   # celda ganadora
LOSE_STYLE = RED_BG    # celda perdedora

def stats_to_html_table(stats: dict) -> str:
    """
    Devuelve una tabla <table> Bootstrap limpia y responsive.
    """
    # ── 1) Filtra sólo las claves escalares ────────────────
    clean = {k: v for k, v in stats.items()
             if pd.api.types.is_scalar(v) or isinstance(v, str)}

    clean.pop("team_logo") # Elimina 'team_logo' si existe
    clean.pop("id")        # Elimina 'id' si existe
    
    # ── 2) DataFrame ordenado (alfabético) ─────────────────
    df = (pd.DataFrame(clean, index=[0])
            .T
            .reset_index()
            .rename(columns={"index": "Estadística", 0: "Valor"}))

    # ── 3) DataFrame → HTML directamente ───────────────────
    html = df.to_html(
        index=False,
        border=0,
        classes="table table-sm table-striped table-bordered mb-0",
        escape=False,              # permite <img> en celdas (team_logo)
        justify="left",
    )

    # ── 4) Envolver en un div scrollable ───────────────────
    html = (
        '<div class="table-responsive my-2">'
        f'{html}'
        '</div>'
    )
    return mark_safe(html)


def compare_stats_to_html_table(stats_a: dict, stats_b: dict) -> str:
    """
    Tabla comparativa (dos jugadores) con la estadística más alta resaltada.
    Las filas se ordenan: nationality, league, club, age y después el resto.
    """
    name_a = stats_a.get("full_name", "Jugador A")
    name_b = stats_b.get("full_name", "Jugador B")

    # ── 1 · Limpieza ───────────────────────────────────────
    drop = {"id", "team_logo", "full_name"}
    numeric_or_str = lambda v: pd.api.types.is_scalar(v) or isinstance(v, str)

    clean_a = {k: v for k, v in stats_a.items() if k not in drop and numeric_or_str(v)}
    clean_b = {k: v for k, v in stats_b.items() if k not in drop and numeric_or_str(v)}

    # ── 2 · Orden deseado ──────────────────────────────────
    priority = ["nationality", "league", "club", "position","age"]
    rest = sorted(set(clean_a.keys()) | set(clean_b.keys()) - set(priority))
    rest = [k for k in rest if k not in priority]  # Asegura que priority va primero
    ordered_keys = priority + rest

    df = (
        pd.DataFrame({
            "Estadística": ordered_keys,
            name_a: [clean_a.get(k, "") for k in ordered_keys],
            name_b: [clean_b.get(k, "") for k in ordered_keys],
        })
    )

    # ── 3 · Resaltar mayor valor ───────────────────────────
    def highlight(row):
        a, b = row[name_a], row[name_b]
        if pd.api.types.is_number(a) and pd.api.types.is_number(b):
            if a > b:
                row[name_a] = f'<span {WIN_STYLE}>{a}</span>'
                row[name_b] = f'<span {LOSE_STYLE}>{b}</span>'
            elif b > a:
                row[name_b] = f'<span {WIN_STYLE}>{b}</span>'
                row[name_a] = f'<span {LOSE_STYLE}>{a}</span>'
        return row

    df = df.apply(highlight, axis=1)

    # ── 4 · DataFrame → HTML ───────────────────────────────
    html = (
        '<div class="table-wrapper table-responsive my-2">'
        + df.to_html(
            index=False,
            classes="table table-sm table-striped table-bordered mb-0 text-center align-middle",
            border=0,
            escape=False,   # conserva nuestros <span> con estilos
          )
        + '</div>'
    )
    return mark_safe(html)