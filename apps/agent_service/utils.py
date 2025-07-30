# apps/agent_service/utils.py
import pandas as pd
import numpy as np
import markdown                
from django.utils.safestring import mark_safe

def stats_to_html_table(stats: dict) -> str:
    """
    Devuelve una tabla <table> Bootstrap limpia y responsive.
    """
    # ── 1) Filtra sólo las claves escalares ────────────────
    clean = {k: v for k, v in stats.items()
             if pd.api.types.is_scalar(v) or isinstance(v, str)}

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