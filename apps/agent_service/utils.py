# apps/agent_service/utils.py
import pandas as pd
import markdown                
from django.utils.safestring import mark_safe

# ── 0 · Style constants ───────────────────────────────
GREEN_TXT = 'style="color:#198754;font-weight:600"'
RED_TXT   = 'style="color:#dc3545;font-weight:600"'

GREEN_BG  = 'style="background-color:#198754;color:#fff;font-weight:700"'
RED_BG    = 'style="background-color:#dc3545;color:#fff;font-weight:700"'

# choose if you want *_TXT or *_BG:
WIN_STYLE = GREEN_BG   # winning cell
LOSE_STYLE = RED_BG    # losing cell

def stats_to_html_table(stats: dict) -> str:
    """
    Returns a clean and responsive Bootstrap <table>.
    """
    # ── 1) Filter only scalar keys ────────────────
    clean = {k: v for k, v in stats.items()
             if pd.api.types.is_scalar(v) or isinstance(v, str)}

    clean.pop("team_logo", None) # Remove 'team_logo' if it exists
    clean.pop("id", None)        # Remove 'id' if it exists
    
    # ── 2) Ordered DataFrame (alphabetical) ─────────────────
    df = (pd.DataFrame(clean, index=[0])
            .T
            .reset_index()
            .rename(columns={"index": "Statistic", 0: "Value"}))

    # ── 3) DataFrame → HTML directly ───────────────────
    html = df.to_html(
        index=False,
        border=0,
        classes="table table-sm table-striped table-bordered mb-0",
        escape=False,              # allows <img> in cells (team_logo)
        justify="left",
    )

    # ── 4) Wrap in a scrollable div ───────────────────
    html = (
        '<div class="table-responsive my-2">'
        f'{html}'
        '</div>'
    )
    return mark_safe(html)


def compare_stats_to_html_table(stats_a: dict, stats_b: dict) -> str:
    """
    Comparative table (two players) with the highest statistic highlighted.
    Rows are ordered: nationality, league, club, age and then the rest.
    """
    name_a = stats_a.get("full_name", "Player A")
    name_b = stats_b.get("full_name", "Player B")

    # ── 1 · Cleanup ───────────────────────────────────────
    drop = {"id", "team_logo", "full_name"}
    numeric_or_str = lambda v: pd.api.types.is_scalar(v) or isinstance(v, str)

    clean_a = {k: v for k, v in stats_a.items() if k not in drop and numeric_or_str(v)}
    clean_b = {k: v for k, v in stats_b.items() if k not in drop and numeric_or_str(v)}

    # ── 2 · Desired order ──────────────────────────────────
    priority = ["nationality", "league", "club", "position","age"]
    rest = sorted(set(clean_a.keys()) | set(clean_b.keys()) - set(priority))
    rest = [k for k in rest if k not in priority]  # Ensures priority comes first
    ordered_keys = priority + rest

    df = (
        pd.DataFrame({
            "Statistic": ordered_keys,
            name_a: [clean_a.get(k, "") for k in ordered_keys],
            name_b: [clean_b.get(k, "") for k in ordered_keys],
        })
    )

    # ── 3 · Highlight highest value ───────────────────────────
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
            escape=False,   # preserves our <span> with styles
          )
        + '</div>'
    )
    return mark_safe(html)