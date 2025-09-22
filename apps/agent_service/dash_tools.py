import os, requests

DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "http://localhost:8000")  # web container

def dashboard_inline(base_player_id: int, candidate_ids: list[int]) -> dict:
    """
    Makes HTMX call and returns the URL included in HX-Redirect.
    """
    r = requests.post(
        "http://localhost:8000/dashboard/inline/",
        json={                       
            "base_id": base_player_id,
            "candidate_ids": candidate_ids,
        },
        timeout=15,
    )
    r.raise_for_status()
    return {"url": r.headers["HX-Redirect"]}
