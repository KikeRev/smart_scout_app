"""
Success Index Calculator v2.1

This module calculates an enhanced success index for transfer recommendations,
considering multiple factors: league, minutes played, age, team performance,
and position-specific adjustments.

Formula:
    success_index_v2_1 = success_index_base × league_weight × minutes_weight 
                        × age_weight × team_strength_weight × position_adjustment
"""

from typing import Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func


class SuccessIndexCalculator:
    """Success index calculator for transfer recommendations"""
    
    # ─────────────────────────────────────────────────────────────────────
    # LEAGUE TIER WEIGHTS
    # ─────────────────────────────────────────────────────────────────────
    LEAGUE_WEIGHTS = {
        # Tier 1 - Top 5 European Leagues (weight: 1.0)
        'Premier League': 1.0,
        'La Liga': 1.0,
        'Bundesliga': 1.0,
        'Serie A': 1.0,
        'Ligue 1': 1.0,
        
        # Tier 2 - Competitive 1st Division Leagues (weight: 0.85)
        'Eredivisie': 0.85,
        'Primeira Liga': 0.85,
        'Belgian Pro League': 0.85,
        'Brasileirao': 0.85,
        'Liga Argentina': 0.85,
        'Liga MX': 0.85,
        
        # Tier 3 - Emerging and 2nd Tier European Leagues (weight: 0.70)
        'Premier Championship England': 0.70,
        'Liga Hipermotion': 0.70,
        'Serie B': 0.70,
        'Brasileirao B': 0.70,
        'Turkiye Super Lig': 0.70,
        'Swiss Super League': 0.70,
        'Saudi Pro League': 0.70,
        
        # Tier 4 - Developing Leagues (weight: 0.55)
        'Danish Superliga': 0.55,
        'Croatian League': 0.55,
        'Czech First League': 0.55,
        'Eliteserien': 0.55,
        'Bulgarian First League': 0.55,
        'Roumanian League I': 0.55,
        
        # Tier 5 - Minor Leagues (weight: 0.40)
        'Major League Soccer Eastern Conf': 0.40,
        'Major League Soccer Western Conf': 0.40,
        'J1 League': 0.40,
        'Korean League 1': 0.40,
        'Chinese Super League': 0.40,
        'Veikkausliiga': 0.40,
    }
    
    @staticmethod
    def calculate_league_weight(league: str) -> float:
        """
        Calculates weight based on league quality.
        
        Args:
            league: League name
            
        Returns:
            float: Weight between 0.40 (minor leagues) and 1.0 (top 5)
        """
        return SuccessIndexCalculator.LEAGUE_WEIGHTS.get(league, 0.40)
    
    @staticmethod
    def calculate_minutes_weight(minutes: int) -> float:
        """
        Calculates weight based on minutes played in the season.
        
        A full season is ~3000-3400 minutes (38 matches × 90 min).
        Minutes indicate: coach's confidence, physical consistency,
        tactical adaptation, and sustained performance.
        
        Args:
            minutes: Minutes played in the season
            
        Returns:
            float: Weight between 0.30 (very few minutes) and 1.0 (starter)
        """
        if minutes >= 2000:
            return 1.00  # Undisputed starter (22+ full matches)
        elif minutes >= 1500:
            return 0.90  # Regular starter (17-22 matches)
        elif minutes >= 1000:
            return 0.75  # Important rotation (11-16 matches)
        elif minutes >= 700:
            return 0.60  # Substitute with minutes (8-11 matches)
        elif minutes >= 400:
            return 0.45  # Occasional substitute (5-8 matches)
        else:
            return 0.30  # Very limited minutes (< 5 matches)
    
    @staticmethod
    def calculate_age_weight(age: int) -> float:
        """
        Calculates weight based on player's age.
        
        Considers: resale value, medium/long-term projection,
        injury risk, and adaptation capacity.
        
        Args:
            age: Player's age
            
        Returns:
            float: Weight between 0.55 (veterans) and 1.0 (optimal age)
        """
        if 21 <= age <= 27:
            return 1.00  # Optimal age (peak + potential)
        elif 18 <= age <= 20:
            return 0.95  # Young with potential (adaptation risk)
        elif 28 <= age <= 29:
            return 0.95  # Consolidated experience
        elif 30 <= age <= 31:
            return 0.85  # Reliable veterans (less improvement margin)
        elif 32 <= age <= 33:
            return 0.70  # Moderate physical risk (2-3 useful years)
        elif age >= 34:
            return 0.55  # High physical risk (short term)
        elif age <= 17:
            return 0.75  # Very young (high uncertainty)
        else:
            return 0.80  # Catch-all
    
    @staticmethod
    def calculate_team_strength_weight(
        club: str, 
        db: Session
    ) -> float:
        """
        Calculates weight based on team performance.
        
        Considers aggregated metrics from all team players
        to estimate competitive level:
        - Offensive: goals and assists per 90 minutes
        - Defensive: tackles and interceptions
        - Control: pass completion percentage
        
        Args:
            club: Club name
            db: Database session
            
        Returns:
            float: Weight between 0.70 (weak teams) and 1.0 (top teams)
        """
        # Import here to avoid circular dependencies
        from apps.ingestion.seed_and_ingest import Player
        
        try:
            # Query to obtain team metrics
            # Only players with significant minutes (>500 min)
            team_stats = db.query(
                func.avg(Player.goals_per90).label('avg_goals'),
                func.avg(Player.assists_per90).label('avg_assists'),
                func.avg(Player.tackles).label('avg_tackles'),
                func.avg(Player.interceptions).label('avg_interceptions'),
                func.avg(Player.passes_pct).label('avg_passes_pct')
            ).filter(
                Player.club == club,
                Player.minutes >= 500
            ).first()
            
            if not team_stats or team_stats.avg_goals is None:
                return 0.80  # Default for teams without sufficient data
            
            # Calculate team strength score components
            offensive = (team_stats.avg_goals or 0) + (team_stats.avg_assists or 0)
            defensive = ((team_stats.avg_tackles or 0) + (team_stats.avg_interceptions or 0))
            control = (team_stats.avg_passes_pct or 0)
            
            # Weighted formula for team score
            # Offensive has more weight (×20), defensive and control normalized
            team_score = (offensive * 20) + (defensive * 0.5) + (control * 0.5)
            
            # Convert score to categorized weight
            if team_score >= 80:
                return 1.00  # Top tier (elite teams)
            elif team_score >= 60:
                return 0.90  # Strong (competitive teams)
            elif team_score >= 40:
                return 0.80  # Medium (mid-table teams)
            else:
                return 0.70  # Weak (struggling teams)
                
        except Exception as e:
            # In case of error, return neutral weight
            print(f"Error calculating team strength for {club}: {e}")
            return 0.80
    
    @staticmethod
    def calculate_position_adjustment(
        position: str,
        age: int,
        minutes: int,
        goals_per90: Optional[float] = 0,
        tackles: Optional[int] = 0,
        interceptions: Optional[int] = 0,
        passes_pct: Optional[float] = 0
    ) -> float:
        """
        Applies position-specific adjustments.
        
        Different positions have different performance curves and
        valued characteristics:
        - GK: Higher age tolerance, importance of continuity
        - FW: Bonus for scoring performance, need rhythm
        - DF: Experience valued, later peak
        - MF: Balance, bonus for versatility
        
        Args:
            position: Player's position
            age: Player's age
            minutes: Minutes played
            goals_per90: Goals per 90 minutes
            tackles: Tackles per season
            interceptions: Interceptions per season
            passes_pct: Pass completion percentage
            
        Returns:
            float: Adjustment between 0.95 and 1.15 (maximum cap)
        """
        adjustment = 1.0
        
        # ─────────────────────────────────────────────────────────────────
        # GOALKEEPERS (GK)
        # ─────────────────────────────────────────────────────────────────
        if position == 'GK':
            # Goalkeepers have later performance peak (28-35 years)
            if 30 <= age <= 35:
                adjustment *= 1.10  # Reduce age penalty
            
            # Continuity is crucial for goalkeepers
            if minutes >= 2000:
                adjustment *= 1.05  # Bonus for being starter
        
        # ─────────────────────────────────────────────────────────────────
        # FORWARDS (FW, FWMF)
        # ─────────────────────────────────────────────────────────────────
        elif position in ['FW', 'FWMF']:
            # Bonus for high scoring performance
            if goals_per90 and goals_per90 >= 0.50:
                adjustment *= 1.10  # Elite scorer (0.5+ goals/90)
            elif goals_per90 and goals_per90 >= 0.30:
                adjustment *= 1.05  # Good scorer (0.3+ goals/90)
            
            # Forwards need rhythm and continuity
            if minutes >= 1500:
                adjustment *= 1.03
        
        # ─────────────────────────────────────────────────────────────────
        # DEFENDERS (DF, DFMF)
        # ─────────────────────────────────────────────────────────────────
        elif position in ['DF', 'DFMF']:
            # Defenders have later peak, value experience
            if 27 <= age <= 32:
                adjustment *= 1.08  # Optimal age for defenders
            
            # Bonus for good defensive numbers
            if tackles and interceptions and (tackles + interceptions) >= 100:
                adjustment *= 1.05  # Active defender
        
        # ─────────────────────────────────────────────────────────────────
        # MIDFIELDERS (MF, MFFW, MFDF)
        # ─────────────────────────────────────────────────────────────────
        elif position in ['MF', 'MFFW', 'MFDF']:
            # Bonus for versatility (good passing + defensive work)
            if passes_pct and tackles and passes_pct >= 85 and tackles >= 50:
                adjustment *= 1.05  # Complete midfielder
        
        # Maximum cap of 1.15 to avoid excessive adjustments
        return min(adjustment, 1.15)
    
    @classmethod
    def calculate_success_index_v2_1(
        cls,
        success_index_base: float,
        player_data: Dict,
        db: Session
    ) -> Dict:
        """
        Calculates complete success index v2.1 with all factors.
        
        Args:
            success_index_base: Base index (combination of overall + team_fit)
            player_data: Dictionary with player data:
                - league: str
                - minutes: int
                - age: int
                - club: str
                - position: str
                - goals_per90: float (optional)
                - tackles: int (optional)
                - interceptions: int (optional)
                - passes_pct: float (optional)
            db: Database session
            
        Returns:
            Dict with:
                - success_index_v2_1: float (final index)
                - breakdown: Dict with breakdown of each weight
        """
        # Calculate each weight component
        league_w = cls.calculate_league_weight(player_data.get('league', ''))
        minutes_w = cls.calculate_minutes_weight(player_data.get('minutes', 0))
        age_w = cls.calculate_age_weight(player_data.get('age', 25))
        team_w = cls.calculate_team_strength_weight(
            player_data.get('club', ''), 
            db
        )
        position_adj = cls.calculate_position_adjustment(
            player_data.get('position', ''),
            player_data.get('age', 25),
            player_data.get('minutes', 0),
            player_data.get('goals_per90', 0),
            player_data.get('tackles', 0),
            player_data.get('interceptions', 0),
            player_data.get('passes_pct', 0)
        )
        
        # Calculate final index
        success_index_v2_1 = (
            success_index_base 
            * league_w 
            * minutes_w 
            * age_w 
            * team_w 
            * position_adj
        )
        
        return {
            'success_index_v2_1': round(success_index_v2_1, 3),
            'breakdown': {
                'base': round(success_index_base, 3),
                'league_weight': round(league_w, 3),
                'minutes_weight': round(minutes_w, 3),
                'age_weight': round(age_w, 3),
                'team_strength_weight': round(team_w, 3),
                'position_adjustment': round(position_adj, 3)
            }
        }

