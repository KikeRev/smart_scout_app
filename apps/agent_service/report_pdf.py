from __future__ import annotations
import os, uuid
from pathlib import Path
from typing import List
from weasyprint import HTML
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.utils import timezone
from urllib.parse import urlparse
try:
    # Only works when Django is initialized (web process)
    from django.conf import settings        # noqa: WPS433  (runtime import)

    MEDIA_DIR = Path(settings.MEDIA_ROOT) / "reports"

except Exception:                           # settings doesn't exist → FastAPI
    # Use a generic path or environment variable
    MEDIA_ROOT_FALLBACK = os.getenv("MEDIA_ROOT", "/app/media")
    MEDIA_DIR = Path(MEDIA_ROOT_FALLBACK) / "reports"

# create directory if it doesn't exist
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

def _abs_uri(url: str) -> str:
    """Converts /media/… or /static/… to file://… for WeasyPrint."""
    if url.startswith("/media/"):
        abs_path = Path(settings.MEDIA_ROOT, url.replace("/media/", "", 1))
        return abs_path.resolve(strict=True).as_uri()
    if url.startswith("/static/"):
        # STATIC_ROOT already contains files collected with collectstatic
        abs_path = Path(settings.STATIC_ROOT, url.replace("/static/", "", 1))
        return abs_path.resolve(strict=True).as_uri()
    # If already absolute return as is
    if bool(urlparse(url).netloc):
        return url
    return url  # last resort


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
    Returns {"file_url": "/media/reports/<uuid>.pdf"}

    The agent must pass:
        • objective          → report objective
        • base_id            → reference player
        • candidate_ids      → complete suggested list
        • chosen_id          → recommended player
        • recommendation     → free text summary
        • pros, cons         → bullet lists
    """
    from apps.agent_service.agents.tools import player_news_tool
    from apps.dashboard.views import _context, _fetch_stats

    # 1) collect stats + charts
    ctx_dash= _context(base_id, chosen_id, candidate_ids, metrics=[])
    from pprint import pprint
    print("=" * 40, "CTX", "=" * 40)
    pprint(ctx_dash, depth=2, compact=True)
    print("=" * 80)
    # 2) player info
    players_map = {p["id"]: p for p in _fetch_stats(candidate_ids+[base_id]).values()}
    alt_players = [players_map[i] for i in candidate_ids if i != chosen_id]

    # 3) latest summarized news
    news_raw = player_news_tool.invoke(
    {
        "player_id":   chosen_id,                      
        "player_name": players_map[chosen_id]["full_name"], 
        "n": 5
    }
    )

    if isinstance(news_raw, list):                 
        news_items = news_raw                      # the tool already returns the list
    else:
        news_items = news_raw.get("items", [])     # compatibility in case it changes

    news_summary = [item["summary"] for item in news_items]

    # ---  candidates table --------------------------------
    import pandas as pd
    df_alt = pd.DataFrame(alt_players)[["id", "full_name", "club", "age"]]
    table_alt_html = (
        df_alt.rename(columns={
            "id": "ID", "full_name": "Player", "club": "Club", "age": "Age"})
        .to_html(index=False, classes="table table-sm table-striped")
    )

    # 4) build HTML
    html_str = render_to_string(
        "reports/report.html",
        {
            "objective":   objective,
            "date":        timezone.now(),        # dd/mm/yyyy hh:mm
            "candidates":  table_alt_html,
            "chosen":      players_map[chosen_id],# complete dict
            "summary":     recommendation,
            "pros":        pros,
            "cons":        cons,
            "news":        news_summary,
            "table_html":  ctx_dash["table_html"],
            "radar_base_url": _abs_uri(ctx_dash["radar_base"]),
            "radar_comp_url": _abs_uri(ctx_dash["radar_cand"]),
            "pizza_url":      _abs_uri(ctx_dash["pizza_cmp"]),
            "logo_url":       _abs_uri(static("img/app_logo_6.png")),
            "github_url": _abs_uri(static("img/github.png")),
            "linkedin_url": _abs_uri(static("img/linkedin.png")),
            "instagram_url": _abs_uri(static("img/instagram.png")),
        },
    )

    # 5) HTML → PDF
    file_id   = uuid.uuid4().hex
    rel_path  = f"reports/{file_id}.pdf"           #   reports/… inside MEDIA_ROOT
    pdf_path  = MEDIA_DIR / f"{file_id}.pdf"
    HTML(string=html_str, base_url=settings.MEDIA_ROOT).write_pdf(target=pdf_path)

    # public URL (relative) → /media/reports/…
    report_url = settings.MEDIA_URL + rel_path     # «/media/…» by default

    return {
    "text": (
        "I have generated the PDF report. "
        "Click the button to download it."
    ),
    "attachments": [
        {
            "type": "file",
            "title": "scouting_report.pdf",
            "url": report_url,   
        }
    ],
}
