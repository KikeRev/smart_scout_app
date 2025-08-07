import os, requests
from typing import List, Dict
from langchain.tools import tool

DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "http://localhost:8000")  # contenedor web

@tool(
    args_schema=None,
    return_direct=True,
    description=(
        "Genera un dashboard interactivo con radar, pizza y tabla comparativa. "
        "Requiere base_player_id (int) y candidate_ids (lista de int). "
        "Devuelve HTML listo para ser mostrado."
    ),
)
def dashboard_inline(base_player_id: int, candidate_ids: list[int]) -> dict:
    """
    Lanza la llamada HTMX y devuelve la URL incluida en HX-Redirect.
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
