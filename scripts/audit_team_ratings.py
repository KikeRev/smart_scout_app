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
    """Compute weighted aggregates per team using position-based weights.

    Returns mapping team -> {overall, att, ply, def, ctr, phy, gkp}.
    """
    from collections import defaultdict

    # Position weights per attribute
    ATT_WEIGHTS = {'FW': 0.60, 'MF': 0.30, 'DF': 0.10, 'GK': 0.0}
    DEF_WEIGHTS = {'DF': 0.50, 'MF': 0.35, 'FW': 0.10, 'GK': 0.05}
    PLY_WEIGHTS = {'FW': 0.40, 'MF': 0.40, 'DF': 0.20, 'GK': 0.0}
    CTR_WEIGHTS = {'FW': 0.40, 'MF': 0.40, 'DF': 0.20, 'GK': 0.0}
    PHY_WEIGHTS = {'FW': 0.333, 'MF': 0.333, 'DF': 0.333, 'GK': 0.0}
    GKP_WEIGHTS = {'GK': 1.0, 'DF': 0.0, 'MF': 0.0, 'FW': 0.0}
    BLEND_MINUTES = 1100.0

    team_to_players: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for (team, name, pos, minutes, ovr, att, ply, d, ctr, phy, gkp) in rows:
        team_to_players[team].append(
            {
                "position": (pos or "MF").upper(),
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

    def calculate_weighted_attribute(players: List[Dict[str, object]], attr: str, position_weights: Dict[str, float]) -> float:
        """Calculate team attribute with position-based weighting."""
        # Group players by position
        position_groups: Dict[str, List[Dict[str, object]]] = {'GK': [], 'DF': [], 'MF': [], 'FW': []}
        
        for p in players:
            pos = p.get('position', 'MF')
            if pos not in position_groups:
                pos = 'MF'  # fallback
            position_groups[pos].append(p)
        
        # Calculate minute-weighted average per position
        position_averages: Dict[str, float] = {}
        
        for pos, pos_players in position_groups.items():
            if not pos_players or position_weights.get(pos, 0) == 0:
                continue
            
            total_weighted = 0.0
            total_minutes = 0.0
            
            for player in pos_players:
                val = float(player.get(attr, 0) or 0)
                minutes = float(player.get('minutes', 0) or 0)
                
                # Apply GKP blending only for GKP attribute and GK position
                if attr == "gkp" and pos == "GK" and minutes > 0:
                    league_avg = 50.0  # simplified league average
                    w = minutes / (minutes + BLEND_MINUTES)
                    val = w * val + (1 - w) * league_avg
                
                total_weighted += val * minutes
                total_minutes += minutes
            
            if total_minutes > 0:
                position_averages[pos] = total_weighted / total_minutes
        
        # Apply position weights to get final attribute
        final_attr = 0.0
        for pos, weight in position_weights.items():
            if pos in position_averages:
                final_attr += position_averages[pos] * weight
        
        return final_attr

    out: Dict[str, Dict[str, float]] = {}
    for team, plist in team_to_players.items():
        # Calculate minute-weighted overall (simple average across all players)
        total_weighted_ovr = sum(p["ovr"] * p["minutes"] for p in plist)
        total_minutes = sum(p["minutes"] for p in plist)
        overall = total_weighted_ovr / total_minutes if total_minutes > 0 else 0.0
        
        # Calculate position-weighted attributes
        team_att = calculate_weighted_attribute(plist, "att", ATT_WEIGHTS)
        team_ply = calculate_weighted_attribute(plist, "ply", PLY_WEIGHTS)
        team_def = calculate_weighted_attribute(plist, "def", DEF_WEIGHTS)
        team_ctr = calculate_weighted_attribute(plist, "ctr", CTR_WEIGHTS)
        team_phy = calculate_weighted_attribute(plist, "phy", PHY_WEIGHTS)
        team_gkp = calculate_weighted_attribute(plist, "gkp", GKP_WEIGHTS)
        
        # Bucket counts for info
        starters = [p for p in plist if p["minutes"] >= 1300]
        subs = [p for p in plist if 300 <= p["minutes"] < 1300]
        youth = [p for p in plist if p["minutes"] < 300]
        gks = [p for p in plist if p["position"] == "GK"]
        
        out[team] = {
            "overall": round(overall, 1),
            "att": round(team_att),
            "ply": round(team_ply),
            "def": round(team_def),
            "ctr": round(team_ctr),
            "phy": round(team_phy),
            "gkp": round(team_gkp),
            "players": len(plist),
            "starters": len(starters),
            "subs": len(subs),
            "youth": len(youth),
            "gks": len(gks),
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
    print("\n=== TEAM RATINGS (Position-Weighted) ===\n")
    count = 0
    for team, vals in sorted(agg.items(), key=lambda kv: kv[0]):
        print(
            f"TEAM: {team} | SEASON: {args.season}\n"
            f"  PLAYERS: {vals['players']} (Starters: {vals['starters']}, Subs: {vals['subs']}, Youth: {vals['youth']}, GKs: {vals['gks']})\n"
            f"  OVR: {vals['overall']} | ATT: {vals['att']} | PLY: {vals['ply']} | DEF: {vals['def']} | CTR: {vals['ctr']} | PHY: {vals['phy']} | GKP: {vals['gkp']}\n"
        )
        count += 1
        if args.limit and count >= args.limit:
            break

    # Goalkeepers list (for quick inspection)
    print("\n=== GOALKEEPERS DETAIL ===\n")
    gks = list_goalkeepers(rows)
    for team, name, minutes, gkp in gks:
        print(f"  {team} | {name} | Minutes: {int(minutes)} | GKP: {gkp}")


if __name__ == "__main__":
    main()


