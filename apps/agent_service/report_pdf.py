from __future__ import annotations
import os, uuid, datetime, textwrap
from pathlib import Path
from typing import List
import requests
from weasyprint import HTML
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.utils import timezone
try:
    # Solo funcionará cuando Django esté inicializado (proceso web)
    from django.conf import settings        # noqa: WPS433  (runtime import)

    MEDIA_DIR = Path(settings.MEDIA_ROOT) / "reports"

except Exception:                           # settings no existe → FastAPI
    # Usa una ruta genérica o variable de entorno
    MEDIA_ROOT_FALLBACK = os.getenv("MEDIA_ROOT", "/app/media")
    MEDIA_DIR = Path(MEDIA_ROOT_FALLBACK) / "reports"

# crea el directorio si no existe
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

TEMPLATE = """
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<style>
  body{ font-family:Arial,Helvetica,sans-serif;margin:0 2rem;color:#222 }
  h1,h2{ color:#236192; margin-bottom:.2em }
  h1{ border-bottom:3px solid #236192; padding-bottom:.1em }
  table{ width:100%; border-collapse:collapse; margin:1rem 0 }
  th,td{ border:1px solid #999; padding:.4em; text-align:center }
  img{ max-width:100%; }
  .charts{ display:flex; justify-content:space-between; gap:.5rem; }
  .charts img{ flex:1; }
  .proscons li{ margin-bottom:.2em; }
</style>
</head><body>

<h1>Informe de Scouting</h1>

<h2>1. Objetivo</h2>
<p>{{ objective }}</p>

<h2>2. Jugadores alternativos propuestos</h2>
<ul>
  {% for p in alt_players %}
    <li>{{ p["full_name"] }} ({{ p["club"] }}, {{ p["age"] }} a)</li>
  {% endfor %}
</ul>

<h2>3. Recomendación</h2>
<p><strong>Jugador elegido:</strong> {{ chosen["full_name"] }} ({{ chosen["club"] }})</p>
<p>{{ recommendation }}</p>

<h3>Pros</h3><ul class="proscons">
  {% for item in pros %}<li>✔️ {{ item }}</li>{% endfor %}
</ul>
<h3>Contras</h3><ul class="proscons">
  {% for item in cons %}<li>⚠️ {{ item }}</li>{% endfor %}
</ul>

<h3>Resumen de prensa reciente</h3>
<ul>
  {% for n in news %}
   <li>{{ n }}</li>
  {% endfor %}
</ul>

<h2>4. Comparativa estadística</h2>
{{ table_html|safe }}

<div class="charts">
  <img src="{{ radar_base }}">
  <img src="{{ radar_cand }}">
</div>
<img src="{{ pizza_cmp }}">

<small>Generado el {{ now }}</small>
</body></html>
"""


def render_html(context: dict) -> str:
    """Rellena el template con {{ mustaches }} muy simples."""
    html = TEMPLATE
    for k, v in context.items():
        placeholder = "{{ "+k+" }}"
        html = html.replace(placeholder, str(v))
    # templating muy rudimentario para listas
    # (o instala jinja2 si prefieres)
    return html

from urllib.parse import urljoin, urlparse

def _abs_uri(url: str) -> str:
    """Convierte /media/… o /static/… en file://… para WeasyPrint."""
    if url.startswith("/media/"):
        abs_path = Path(settings.MEDIA_ROOT, url.replace("/media/", "", 1))
        return abs_path.resolve(strict=True).as_uri()
    if url.startswith("/static/"):
        # STATIC_ROOT ya contiene los archivos recolectados con collectstatic
        abs_path = Path(settings.STATIC_ROOT, url.replace("/static/", "", 1))
        return abs_path.resolve(strict=True).as_uri()
    # Si ya es absoluta devuélvela tal cual
    if bool(urlparse(url).netloc):
        return url
    return url  # último recurso


def build_report_pdf(
    *,
    objective: str,
    base_id: int,
    candidate_ids: List[int],
    chosen_id: int,
    recommendation: str,
    pros: List[str],
    cons: List[str],
) -> dict:
    """
    Devuelve {"file_url": "/media/reports/<uuid>.pdf"}

    El agente debe pasar:
        • objective          → objetivo del informe
        • base_id            → jugador referencia
        • candidate_ids      → lista completa sugerida
        • chosen_id          → jugador recomendado
        • recommendation     → texto libre resumen
        • pros, cons         → listas de bullets
    """
    from apps.agent_service.agents.tools import player_news_tool
    from apps.dashboard.views import _context, _fetch_stats

    # 1) recopila stats + gráficos
    ctx_dash= _context(base_id, chosen_id, candidate_ids, metrics=[])
    from pprint import pprint
    print("=" * 40, "CTX", "=" * 40)
    pprint(ctx_dash, depth=2, compact=True)
    print("=" * 80)
    # 2) info jugadores
    players_map = {p["id"]: p for p in _fetch_stats(candidate_ids+[base_id]).values()}
    alt_players = [players_map[i] for i in candidate_ids if i != chosen_id]

    # 3) últimas noticias resumidas
    news_raw = player_news_tool.invoke(
    {
        "player_id":   chosen_id,                      
        "player_name": players_map[chosen_id]["full_name"], 
        "n": 5
    }
    )

    if isinstance(news_raw, list):                 
        news_items = news_raw                      # el tool ya devuelve la lista
    else:
        news_items = news_raw.get("items", [])     # compatibilidad por si cambia

    news_summary = [item["summary"] for item in news_items]

    # ---  tabla de candidatos --------------------------------
    import pandas as pd
    df_alt = pd.DataFrame(alt_players)[["id", "full_name", "club", "age"]]
    table_alt_html = (
        df_alt.rename(columns={
            "id": "ID", "full_name": "Jugador", "club": "Club", "age": "Edad"})
        .to_html(index=False, classes="table table-sm table-striped")
    )

    # 4) monta el HTML
    html_str = render_to_string(
        "reports/report.html",
        {
            "objective":   objective,
            "date":        timezone.now(),        # dd/mm/aaaa hh:mm
            "candidates":  table_alt_html,
            "chosen":      players_map[chosen_id],# dict completo
            "summary":     recommendation,
            "pros":        pros,
            "cons":        cons,
            "news":        news_summary,
            "table_html":  ctx_dash["table_html"],
            "radar_base_url": _abs_uri(ctx_dash["radar_base"]),
            "radar_comp_url": _abs_uri(ctx_dash["radar_cand"]),
            "pizza_url":      _abs_uri(ctx_dash["pizza_cmp"]),
            "logo_url":       _abs_uri(static("img/app_logo_6.png")),
        },
    )

    # 5) HTML → PDF
    file_id   = uuid.uuid4().hex
    rel_path  = f"reports/{file_id}.pdf"           #   reports/… dentro de MEDIA_ROOT
    pdf_path  = MEDIA_DIR / f"{file_id}.pdf"
    HTML(string=html_str, base_url=settings.MEDIA_ROOT).write_pdf(target=pdf_path)

    # URL pública (relativa) → /media/reports/…
    report_url = settings.MEDIA_URL + rel_path     # «/media/…» por defecto

    return {
    "text": (
        "He generado el informe en PDF. "
        "Pulsa el botón para descargarlo."
    ),
    "attachments": [
        {
            "type": "file",
            "title": "informe_scouting.pdf",
            "url": report_url,   
        }
    ],
}
