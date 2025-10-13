"""
Ratings API Router - Endpoints for FIFA-style player ratings

Provides endpoints to:
- Get individual player ratings
- Get team ratings (calculated on-the-fly)
- Get top players by rating with filters
- Get radar chart data for visualization
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from pydantic import BaseModel
import sqlalchemy as sa
from sqlalchemy import text, desc
import os

# Database connection
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://scout:scout@db:5432/scouting"
)

router = APIRouter(prefix="/api/ratings", tags=["ratings"])


# ============================================================================
# RESPONSE MODELS
# ============================================================================

class PlayerRatingResponse(BaseModel):
    """Individual player rating response"""
    player_id: int
    player_name: str
    position: str
    club: str
    league: str
    season: str
    overall_rating: int
    league_base_rating: float
    performance_rating: float
    att: int
    ply: int
    def_rating: int
    ctr: int
    phy: int
    gkp: Optional[int] = None
    minutes_played: int

    class Config:
        from_attributes = True


class RadarChartData(BaseModel):
    """Radar chart data for player visualization"""
    player_id: int
    player_name: str
    position: str
    overall_rating: int
    attributes: dict  # {ATT: 85, PLY: 90, DEF: 75, CTR: 88, PHY: 82, GKP: null}
    percentiles: dict  # Same structure, shows percentile vs league


class TopPlayerResponse(BaseModel):
    """Top player in ranking"""
    rank: int
    player_id: int
    player_name: str
    position: str
    club: str
    league: str
    nationality: str
    overall_rating: int
    att: int
    ply: int
    def_rating: int
    ctr: int
    phy: int
    gkp: Optional[int] = None


class TeamRatingResponse(BaseModel):
    """Team rating calculated on-the-fly"""
    team_name: str
    season: str
    overall_rating: float
    num_players: int
    starters: List[dict]  # Players with >= 1300 minutes
    substitutes: List[dict]  # Players with 300-1299 minutes
    youth: List[dict]  # Players with < 300 minutes
    breakdown: dict  # {starters_avg: 85.2, substitutes_avg: 78.5, youth_avg: 72.1}


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/player/{player_id}", response_model=PlayerRatingResponse)
async def get_player_rating(player_id: int, season: Optional[str] = "2024-25"):
    """
    Get FIFA-style rating for a specific player.
    
    Args:
        player_id: Player ID in database
        season: Season (default: 2024-25)
    
    Returns:
        Complete player rating with all attributes
    """
    engine = sa.create_engine(DATABASE_URL)
    
    query = text("""
        SELECT 
            pr.player_id,
            p.full_name,
            p.position,
            p.club,
            p.league,
            pr.season,
            pr.overall_rating,
            pr.league_base_rating,
            pr.performance_rating,
            pr.att,
            pr.ply,
            pr.def_rating,
            pr.ctr,
            pr.phy,
            pr.gkp,
            pr.minutes_played
        FROM player_ratings pr
        JOIN players p ON pr.player_id = p.id
        WHERE pr.player_id = :player_id
          AND pr.season = :season
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query, {"player_id": player_id, "season": season}).fetchone()
    
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Rating not found for player_id={player_id}, season={season}"
        )
    
    return PlayerRatingResponse(
        player_id=result[0],
        player_name=result[1],
        position=result[2] or "Unknown",
        club=result[3] or "Unknown",
        league=result[4] or "Unknown",
        season=result[5],
        overall_rating=result[6],
        league_base_rating=result[7],
        performance_rating=result[8],
        att=result[9],
        ply=result[10],
        def_rating=result[11],
        ctr=result[12],
        phy=result[13],
        gkp=result[14],
        minutes_played=result[15]
    )


@router.get("/player/{player_id}/radar", response_model=RadarChartData)
async def get_player_radar(player_id: int, season: Optional[str] = "2024-25"):
    """
    Get radar chart data for a player.
    
    Returns both absolute attribute values and percentiles for visualization.
    """
    engine = sa.create_engine(DATABASE_URL)
    
    # Get player rating
    query = text("""
        SELECT 
            pr.player_id,
            p.full_name,
            p.position,
            p.league,
            pr.overall_rating,
            pr.att,
            pr.ply,
            pr.def_rating,
            pr.ctr,
            pr.phy,
            pr.gkp
        FROM player_ratings pr
        JOIN players p ON pr.player_id = p.id
        WHERE pr.player_id = :player_id
          AND pr.season = :season
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query, {"player_id": player_id, "season": season}).fetchone()
    
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Rating not found for player_id={player_id}"
        )
    
    player_id, name, position, league, ovr, att, ply, def_r, ctr, phy, gkp = result
    
    # Get league averages for percentile calculation
    league_query = text("""
        SELECT 
            AVG(pr.att) as avg_att,
            AVG(pr.ply) as avg_ply,
            AVG(pr.def_rating) as avg_def,
            AVG(pr.ctr) as avg_ctr,
            AVG(pr.phy) as avg_phy,
            AVG(pr.gkp) as avg_gkp
        FROM player_ratings pr
        JOIN players p ON pr.player_id = p.id
        WHERE p.league = :league
          AND pr.season = :season
    """)
    
    with engine.connect() as conn:
        league_avg = conn.execute(league_query, {"league": league, "season": season}).fetchone()
    
    # Calculate simple percentiles (could be improved with actual percentile ranking)
    attributes = {
        "ATT": att,
        "PLY": ply,
        "DEF": def_r,
        "CTR": ctr,
        "PHY": phy,
    }
    
    if position == "GK" and gkp:
        attributes["GKP"] = gkp
    
    # Simple percentile approximation (value / max_possible * 100)
    percentiles = {
        key: min(100, (value / 100.0) * 100)
        for key, value in attributes.items()
    }
    
    return RadarChartData(
        player_id=player_id,
        player_name=name,
        position=position or "Unknown",
        overall_rating=ovr,
        attributes=attributes,
        percentiles=percentiles
    )


@router.get("/top", response_model=List[TopPlayerResponse])
async def get_top_players(
    limit: int = Query(50, ge=1, le=100, description="Number of players to return"),
    league: Optional[str] = Query(None, description="Filter by league"),
    nationality: Optional[str] = Query(None, description="Filter by nationality"),
    position: Optional[str] = Query(None, description="Filter by position (GK, DF, MF, FW)"),
    season: Optional[str] = Query("2024-25", description="Season"),
    min_minutes: Optional[int] = Query(500, description="Minimum minutes played")
):
    """
    Get top N players by overall rating with optional filters.
    
    Filters:
    - league: Filter by specific league (e.g., "Premier League", "La Liga")
    - nationality: Filter by nationality (e.g., "England", "Brazil")
    - position: Filter by position (GK, DF, MF, FW)
    - min_minutes: Minimum minutes played (default: 500)
    
    Returns ranked list of players with their ratings.
    """
    engine = sa.create_engine(DATABASE_URL)
    
    # Build dynamic query
    where_clauses = ["pr.season = :season", "pr.minutes_played >= :min_minutes"]
    params = {"season": season, "min_minutes": min_minutes, "limit": limit}
    
    if league:
        where_clauses.append("p.league = :league")
        params["league"] = league
    
    if nationality:
        where_clauses.append("p.nationality = :nationality")
        params["nationality"] = nationality
    
    if position:
        where_clauses.append("p.position = :position")
        params["position"] = position
    
    where_sql = " AND ".join(where_clauses)
    
    query = text(f"""
        SELECT 
            pr.player_id,
            p.full_name,
            p.position,
            p.club,
            p.league,
            p.nationality,
            pr.overall_rating,
            pr.att,
            pr.ply,
            pr.def_rating,
            pr.ctr,
            pr.phy,
            pr.gkp
        FROM player_ratings pr
        JOIN players p ON pr.player_id = p.id
        WHERE {where_sql}
        ORDER BY pr.overall_rating DESC, p.full_name ASC
        LIMIT :limit
    """)
    
    with engine.connect() as conn:
        results = conn.execute(query, params).fetchall()
    
    if not results:
        return []
    
    return [
        TopPlayerResponse(
            rank=idx + 1,
            player_id=row[0],
            player_name=row[1],
            position=row[2] or "Unknown",
            club=row[3] or "Unknown",
            league=row[4] or "Unknown",
            nationality=row[5] or "Unknown",
            overall_rating=row[6],
            att=row[7],
            ply=row[8],
            def_rating=row[9],
            ctr=row[10],
            phy=row[11],
            gkp=row[12]
        )
        for idx, row in enumerate(results)
    ]


@router.get("/team/{team_name}", response_model=TeamRatingResponse)
async def get_team_rating(
    team_name: str,
    season: Optional[str] = Query("2024-25", description="Season")
):
    """
    Get team rating calculated on-the-fly from player ratings.
    
    Team rating is a weighted average:
    - Starters (>=1300 min): 70% weight
    - Substitutes (300-1299 min): 25% weight
    - Youth (<300 min): 5% weight
    
    Args:
        team_name: Team/club name (e.g., "Liverpool", "Real Madrid")
        season: Season (default: 2024-25)
    
    Returns:
        Team rating with player breakdown by category
    """
    engine = sa.create_engine(DATABASE_URL)
    
    query = text("""
        SELECT 
            p.full_name,
            p.position,
            pr.overall_rating,
            pr.minutes_played,
            pr.att,
            pr.ply,
            pr.def_rating,
            pr.ctr,
            pr.phy
        FROM player_ratings pr
        JOIN players p ON pr.player_id = p.id
        WHERE p.club = :team_name
          AND pr.season = :season
        ORDER BY pr.minutes_played DESC
    """)
    
    with engine.connect() as conn:
        results = conn.execute(query, {"team_name": team_name, "season": season}).fetchall()
    
    if not results:
        raise HTTPException(
            status_code=404,
            detail=f"No players found for team '{team_name}' in season {season}"
        )
    
    # Classify players by minutes
    starters = []
    substitutes = []
    youth = []
    
    for row in results:
        player_data = {
            "name": row[0],
            "position": row[1] or "Unknown",
            "rating": row[2],
            "minutes": row[3],
            "att": row[4],
            "ply": row[5],
            "def": row[6],
            "ctr": row[7],
            "phy": row[8]
        }
        
        if row[3] >= 1300:
            starters.append(player_data)
        elif row[3] >= 300:
            substitutes.append(player_data)
        else:
            youth.append(player_data)
    
    # Calculate weighted team rating
    starters_avg = sum(p["rating"] for p in starters) / len(starters) if starters else 0
    substitutes_avg = sum(p["rating"] for p in substitutes) / len(substitutes) if substitutes else 0
    youth_avg = sum(p["rating"] for p in youth) / len(youth) if youth else 0
    
    # Weighted average: 70% starters, 25% substitutes, 5% youth
    team_rating = (
        starters_avg * 0.70 +
        substitutes_avg * 0.25 +
        youth_avg * 0.05
    )
    
    return TeamRatingResponse(
        team_name=team_name,
        season=season,
        overall_rating=round(team_rating, 1),
        num_players=len(results),
        starters=starters,
        substitutes=substitutes,
        youth=youth,
        breakdown={
            "starters_avg": round(starters_avg, 1),
            "starters_count": len(starters),
            "substitutes_avg": round(substitutes_avg, 1),
            "substitutes_count": len(substitutes),
            "youth_avg": round(youth_avg, 1),
            "youth_count": len(youth)
        }
    )


@router.get("/leagues", response_model=List[str])
async def get_available_leagues(season: Optional[str] = "2024-25"):
    """
    Get list of available leagues for filtering.
    """
    engine = sa.create_engine(DATABASE_URL)
    
    query = text("""
        SELECT DISTINCT p.league
        FROM players p
        JOIN player_ratings pr ON p.id = pr.player_id
        WHERE pr.season = :season
          AND p.league IS NOT NULL
        ORDER BY p.league
    """)
    
    with engine.connect() as conn:
        results = conn.execute(query, {"season": season}).fetchall()
    
    return [row[0] for row in results]


@router.get("/nationalities", response_model=List[str])
async def get_available_nationalities(season: Optional[str] = "2024-25"):
    """
    Get list of available nationalities for filtering.
    """
    engine = sa.create_engine(DATABASE_URL)
    
    query = text("""
        SELECT DISTINCT p.nationality
        FROM players p
        JOIN player_ratings pr ON p.id = pr.player_id
        WHERE pr.season = :season
          AND p.nationality IS NOT NULL
        ORDER BY p.nationality
    """)
    
    with engine.connect() as conn:
        results = conn.execute(query, {"season": season}).fetchall()
    
    return [row[0] for row in results]

