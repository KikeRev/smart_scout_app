import argparse
import os
from typing import Dict, List, Optional, Tuple

import sqlalchemy as sa
from sqlalchemy import text


DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://scout:scout@db:5432/scouting"
)


def fetch_player_ratings(
    *, season: str, team: Optional[str] = None, league: Optional[str] = None
) -> List[Tuple]:
    """Return rows of (team, full_name, position, minutes, ovr, att, ply, def, ctr, phy, gkp).

    Filters by team and/or league if provided.
    """
    where = ["pr.season = :season"]
    params: Dict[str, object] = {"season": season}
    if team:
        where.append("p.club = :team")
        params["team"] = team
    if league:
        where.append("p.league = :league")
        params["league"] = league
    where_sql = " AND ".join(where)

    query = text(
        f"""
        SELECT 
            p.club as team,
            p.full_name,
            p.position,
            pr.minutes_played,
            pr.overall_rating,
            pr.att, pr.ply, pr.def_rating, pr.ctr, pr.phy, pr.gkp
        FROM player_ratings pr
        JOIN players p ON pr.player_id = p.id
        WHERE {where_sql}
        ORDER BY p.club ASC, pr.minutes_played DESC
        """
    )

    engine = sa.create_engine(DATABASE_URL)
    with engine.connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return rows


def weighted_team_aggregates(rows: List[Tuple]) -> Dict[str, Dict[str, float]]:
    """Compute weighted aggregates per team using 70/25/5 weights by minutes buckets.

    Returns mapping team -> {overall, att, ply, def, ctr, phy, gkp}.
    """
    from collections import defaultdict

    team_to_players: Dict[str, List[Dict[str, float]]] = defaultdict(list)
    for (team, name, pos, minutes, ovr, att, ply, d, ctr, phy, gkp) in rows:
        team_to_players[team].append(
            {
                "minutes": float(minutes or 0),
                "ovr": float(ovr or 0),
                "att": float(att or 0),
                "ply": float(ply or 0),
                "def": float(d or 0),
                "ctr": float(ctr or 0),
                "phy": float(phy or 0),
                "gkp": float(gkp or 0),
            }
        )

    def avg(players: List[Dict[str, float]], key: str) -> float:
        return sum(p[key] for p in players) / len(players) if players else 0.0

    def minute_weighted_avg(players: List[Dict[str, float]], key: str, use_blend: bool = False) -> float:
        """Calculate minute-weighted average with optional GKP blending."""
        if not players:
            return 0.0
        
        # For GKP, use blending with 1100 minutes threshold
        if use_blend:
            BLEND_MINUTES = 1100.0
            total_weighted = 0.0
            total_minutes = 0.0
            for p in players:
                minutes = p["minutes"]
                val = p[key]
                # Apply blending: (m/(m+1100))*val + (1100/(m+1100))*league_avg
                # For simplicity, use 50 as league average (will be refined later)
                league_avg = 50.0
                w = minutes / (minutes + BLEND_MINUTES)
                blended_val = w * val + (1 - w) * league_avg
                total_weighted += blended_val * minutes
                total_minutes += minutes
            return total_weighted / total_minutes if total_minutes > 0 else 0.0
        else:
            # Standard minute-weighted average
            total_weighted = sum(p[key] * p["minutes"] for p in players)
            total_minutes = sum(p["minutes"] for p in players)
            return total_weighted / total_minutes if total_minutes > 0 else 0.0

    out: Dict[str, Dict[str, float]] = {}
    for team, plist in team_to_players.items():
        starters = [p for p in plist if p["minutes"] >= 1300]
        subs = [p for p in plist if 300 <= p["minutes"] < 1300]
        youth = [p for p in plist if p["minutes"] < 300]

        # Split GK vs non-GK lists by bucket
        starters_gk = [p for p in starters if p.get("gkp", 0) > 0]
        subs_gk = [p for p in subs if p.get("gkp", 0) > 0]
        youth_gk = [p for p in youth if p.get("gkp", 0) > 0]
        starters_nongk = [p for p in starters if p.get("gkp", 0) == 0]
        subs_nongk = [p for p in subs if p.get("gkp", 0) == 0]
        youth_nongk = [p for p in youth if p.get("gkp", 0) == 0]

        def weighted(avg_starters: float, avg_subs: float, avg_youth: float) -> float:
            return round(avg_starters * 0.70 + avg_subs * 0.25 + avg_youth * 0.05, 1)

        def wattr(attr: str) -> float:
            if attr == "gkp":
                return weighted(
                    minute_weighted_avg(starters_gk, attr, use_blend=True),
                    minute_weighted_avg(subs_gk, attr, use_blend=True),
                    minute_weighted_avg(youth_gk, attr, use_blend=True)
                )
            else:
                return weighted(
                    minute_weighted_avg(starters_nongk, attr, use_blend=False),
                    minute_weighted_avg(subs_nongk, attr, use_blend=False),
                    minute_weighted_avg(youth_nongk, attr, use_blend=False)
                )

        # overall keeps all players (including GK), same as backend endpoint
        overall = weighted(avg(starters, "ovr"), avg(subs, "ovr"), avg(youth, "ovr"))
        out[team] = {
            "overall": overall,
            "att": round(wattr("att")),
            "ply": round(wattr("ply")),
            "def": round(wattr("def")),
            "ctr": round(wattr("ctr")),
            "phy": round(wattr("phy")),
            "gkp": round(wattr("gkp")),
            "players": len(plist),
            "starters": len(starters),
            "subs": len(subs),
            "youth": len(youth),
            "gk_buckets": f"{len(starters_gk)}/{len(subs_gk)}/{len(youth_gk)}",
        }
    return out


def list_goalkeepers(rows: List[Tuple]) -> List[Tuple[str, str, float, float]]:
    """Return (team, name, minutes, gkp) for goalkeepers only."""
    gks: List[Tuple[str, str, float, float]] = []
    for (team, name, pos, minutes, ovr, att, ply, d, ctr, phy, gkp) in rows:
        if (pos or "").upper() == "GK":
            gks.append((team, name, float(minutes or 0), float(gkp or 0)))
    return gks


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit aggregated team ratings and goalkeeper ratings"
    )
    parser.add_argument("--season", default="2024-25")
    parser.add_argument("--team", default=None)
    parser.add_argument("--league", default=None)
    parser.add_argument("--limit", type=int, default=50, help="Max teams to print")
    args = parser.parse_args()

    rows = fetch_player_ratings(season=args.season, team=args.team, league=args.league)
    if not rows:
        print("No data found with current filters.")
        return

    agg = weighted_team_aggregates(rows)
    # Print header
    print("TEAM;SEASON;PLAYERS;STARTERS;SUBS;YOUTH;OVR;ATT;PLY;DEF;CTR;PHY;GKP")
    count = 0
    for team, vals in sorted(agg.items(), key=lambda kv: kv[0]):
        print(
            f"TM:{team}; SEASON:{args.season} \n"
            f"OVR:{vals['overall']}; ATT:{vals['att']}; PLY:{vals['ply']}; DEF:{vals['def']}; CTR:{vals['ctr']}; PHY:{vals['phy']}; GKP:{vals['gkp']}"
        )
        count += 1
        if args.limit and count >= args.limit:
            break

    # Goalkeepers list (for quick inspection)
    print("\n# Goalkeepers ratings (team; name; minutes; gkp)")
    gks = list_goalkeepers(rows)
    for team, name, minutes, gkp in gks:
        print(f"TEAM: {team}; NAME: {name}; MINUTES: {int(minutes)}; GKP:{gkp}")


if __name__ == "__main__":
    main()


