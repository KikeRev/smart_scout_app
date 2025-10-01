"""
Unit tests for SuccessIndexCalculator v2.1
"""

import pytest
from unittest.mock import Mock, MagicMock
from apps.agent_service.success_index_calculator import SuccessIndexCalculator


class TestLeagueWeight:
    """Tests for calculate_league_weight"""
    
    def test_top5_leagues(self):
        """Top 5 European leagues should have weight 1.0"""
        assert SuccessIndexCalculator.calculate_league_weight('Premier League') == 1.0
        assert SuccessIndexCalculator.calculate_league_weight('La Liga') == 1.0
        assert SuccessIndexCalculator.calculate_league_weight('Bundesliga') == 1.0
        assert SuccessIndexCalculator.calculate_league_weight('Serie A') == 1.0
        assert SuccessIndexCalculator.calculate_league_weight('Ligue 1') == 1.0
    
    def test_tier2_leagues(self):
        """Competitive leagues should have weight 0.85"""
        assert SuccessIndexCalculator.calculate_league_weight('Eredivisie') == 0.85
        assert SuccessIndexCalculator.calculate_league_weight('Primeira Liga') == 0.85
        assert SuccessIndexCalculator.calculate_league_weight('Brasileirao') == 0.85
    
    def test_tier3_leagues(self):
        """Emerging leagues should have weight 0.70"""
        assert SuccessIndexCalculator.calculate_league_weight('Liga Hipermotion') == 0.70
        assert SuccessIndexCalculator.calculate_league_weight('Serie B') == 0.70
    
    def test_tier4_leagues(self):
        """Developing leagues should have weight 0.55"""
        assert SuccessIndexCalculator.calculate_league_weight('Danish Superliga') == 0.55
        assert SuccessIndexCalculator.calculate_league_weight('Croatian League') == 0.55
    
    def test_tier5_leagues(self):
        """Minor leagues should have weight 0.40"""
        assert SuccessIndexCalculator.calculate_league_weight('J1 League') == 0.40
        assert SuccessIndexCalculator.calculate_league_weight('Korean League 1') == 0.40
    
    def test_unknown_league(self):
        """Unrecognized leagues should have default weight 0.40"""
        assert SuccessIndexCalculator.calculate_league_weight('Unknown League') == 0.40
        assert SuccessIndexCalculator.calculate_league_weight('') == 0.40


class TestMinutesWeight:
    """Tests for calculate_minutes_weight"""
    
    def test_titular_indiscutible(self):
        """≥2000 minutes = undisputed starter (1.0)"""
        assert SuccessIndexCalculator.calculate_minutes_weight(2000) == 1.0
        assert SuccessIndexCalculator.calculate_minutes_weight(2500) == 1.0
        assert SuccessIndexCalculator.calculate_minutes_weight(3000) == 1.0
    
    def test_titular_habitual(self):
        """1500-1999 minutes = regular starter (0.9)"""
        assert SuccessIndexCalculator.calculate_minutes_weight(1500) == 0.9
        assert SuccessIndexCalculator.calculate_minutes_weight(1750) == 0.9
        assert SuccessIndexCalculator.calculate_minutes_weight(1999) == 0.9
    
    def test_rotacion(self):
        """1000-1499 minutes = rotation (0.75)"""
        assert SuccessIndexCalculator.calculate_minutes_weight(1000) == 0.75
        assert SuccessIndexCalculator.calculate_minutes_weight(1250) == 0.75
        assert SuccessIndexCalculator.calculate_minutes_weight(1499) == 0.75
    
    def test_suplente_con_minutos(self):
        """700-999 minutes = substitute with minutes (0.6)"""
        assert SuccessIndexCalculator.calculate_minutes_weight(700) == 0.6
        assert SuccessIndexCalculator.calculate_minutes_weight(850) == 0.6
        assert SuccessIndexCalculator.calculate_minutes_weight(999) == 0.6
    
    def test_suplente_ocasional(self):
        """400-699 minutes = occasional substitute (0.45)"""
        assert SuccessIndexCalculator.calculate_minutes_weight(400) == 0.45
        assert SuccessIndexCalculator.calculate_minutes_weight(550) == 0.45
        assert SuccessIndexCalculator.calculate_minutes_weight(699) == 0.45
    
    def test_minutos_limitados(self):
        """<400 minutes = very limited (0.3)"""
        assert SuccessIndexCalculator.calculate_minutes_weight(399) == 0.3
        assert SuccessIndexCalculator.calculate_minutes_weight(200) == 0.3
        assert SuccessIndexCalculator.calculate_minutes_weight(0) == 0.3


class TestAgeWeight:
    """Tests for calculate_age_weight"""
    
    def test_edad_optima(self):
        """21-27 years = optimal age (1.0)"""
        for age in range(21, 28):
            assert SuccessIndexCalculator.calculate_age_weight(age) == 1.0
    
    def test_jovenes_con_potencial(self):
        """18-20 years = young (0.95)"""
        assert SuccessIndexCalculator.calculate_age_weight(18) == 0.95
        assert SuccessIndexCalculator.calculate_age_weight(19) == 0.95
        assert SuccessIndexCalculator.calculate_age_weight(20) == 0.95
    
    def test_experiencia_consolidada(self):
        """28-29 years = experience (0.95)"""
        assert SuccessIndexCalculator.calculate_age_weight(28) == 0.95
        assert SuccessIndexCalculator.calculate_age_weight(29) == 0.95
    
    def test_veteranos_fiables(self):
        """30-31 years = veterans (0.85)"""
        assert SuccessIndexCalculator.calculate_age_weight(30) == 0.85
        assert SuccessIndexCalculator.calculate_age_weight(31) == 0.85
    
    def test_riesgo_moderado(self):
        """32-33 years = moderate risk (0.7)"""
        assert SuccessIndexCalculator.calculate_age_weight(32) == 0.7
        assert SuccessIndexCalculator.calculate_age_weight(33) == 0.7
    
    def test_alto_riesgo(self):
        """≥34 years = high risk (0.55)"""
        assert SuccessIndexCalculator.calculate_age_weight(34) == 0.55
        assert SuccessIndexCalculator.calculate_age_weight(35) == 0.55
        assert SuccessIndexCalculator.calculate_age_weight(40) == 0.55
    
    def test_muy_jovenes(self):
        """≤17 years = very young (0.75)"""
        assert SuccessIndexCalculator.calculate_age_weight(17) == 0.75
        assert SuccessIndexCalculator.calculate_age_weight(16) == 0.75


class TestTeamStrengthWeight:
    """Tests for calculate_team_strength_weight"""
    
    def test_team_top_tier(self):
        """Teams with team_score ≥80 should have weight 1.0"""
        mock_db = Mock()
        mock_result = Mock()
        mock_result.avg_goals = 1.5
        mock_result.avg_assists = 1.0
        mock_result.avg_tackles = 50.0
        mock_result.avg_interceptions = 40.0
        mock_result.avg_passes_pct = 85.0
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_result
        
        weight = SuccessIndexCalculator.calculate_team_strength_weight('Top Club', mock_db)
        assert weight == 1.0
    
    def test_team_no_data(self):
        """Teams without data should return default weight 0.8"""
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        weight = SuccessIndexCalculator.calculate_team_strength_weight('Unknown Club', mock_db)
        assert weight == 0.8
    
    def test_team_weak(self):
        """Teams with team_score <40 should have weight 0.7"""
        mock_db = Mock()
        mock_result = Mock()
        # Score = (0.01+0.01)*20 + (5+3)*0.5 + 50*0.5 = 0.4 + 4 + 25 = 29.4 < 40 ✓
        mock_result.avg_goals = 0.01
        mock_result.avg_assists = 0.01
        mock_result.avg_tackles = 5.0
        mock_result.avg_interceptions = 3.0
        mock_result.avg_passes_pct = 50.0
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_result
        
        weight = SuccessIndexCalculator.calculate_team_strength_weight('Weak Club', mock_db)
        assert weight == 0.7
    
    def test_team_exception_handling(self):
        """Errors should return neutral weight 0.8"""
        mock_db = Mock()
        mock_db.query.side_effect = Exception("Database error")
        
        weight = SuccessIndexCalculator.calculate_team_strength_weight('Error Club', mock_db)
        assert weight == 0.8


class TestPositionAdjustment:
    """Tests for calculate_position_adjustment"""
    
    def test_goalkeeper_optimal_age(self):
        """Goalkeepers 30-35 years should have bonus"""
        adj = SuccessIndexCalculator.calculate_position_adjustment(
            position='GK',
            age=32,
            minutes=2500,
            goals_per90=0,
            tackles=0,
            interceptions=0,
            passes_pct=0
        )
        assert adj > 1.0
        assert adj <= 1.15
    
    def test_forward_high_scorer(self):
        """Forwards with >0.5 goals/90 should have bonus"""
        adj = SuccessIndexCalculator.calculate_position_adjustment(
            position='FW',
            age=25,
            minutes=2000,
            goals_per90=0.6,
            tackles=0,
            interceptions=0,
            passes_pct=0
        )
        assert adj > 1.0
        assert adj <= 1.15
    
    def test_forward_moderate_scorer(self):
        """Forwards with 0.3-0.5 goals/90 should have moderate bonus"""
        adj = SuccessIndexCalculator.calculate_position_adjustment(
            position='FW',
            age=25,
            minutes=2000,
            goals_per90=0.35,
            tackles=0,
            interceptions=0,
            passes_pct=0
        )
        assert adj > 1.0
        assert adj <= 1.15
    
    def test_defender_experienced(self):
        """Defenders 27-32 years should have bonus"""
        adj = SuccessIndexCalculator.calculate_position_adjustment(
            position='DF',
            age=29,
            minutes=2000,
            goals_per90=0,
            tackles=60,
            interceptions=50,
            passes_pct=85
        )
        assert adj > 1.0
        assert adj <= 1.15
    
    def test_midfielder_versatile(self):
        """Versatile midfielders (passing + defense) should have bonus"""
        adj = SuccessIndexCalculator.calculate_position_adjustment(
            position='MF',
            age=26,
            minutes=2000,
            goals_per90=0.1,
            tackles=60,
            interceptions=30,
            passes_pct=87
        )
        assert adj > 1.0
        assert adj <= 1.15
    
    def test_adjustment_cap(self):
        """Maximum adjustment should be capped at 1.15"""
        adj = SuccessIndexCalculator.calculate_position_adjustment(
            position='GK',
            age=33,
            minutes=3000,
            goals_per90=0,
            tackles=0,
            interceptions=0,
            passes_pct=0
        )
        assert adj <= 1.15
    
    def test_unknown_position(self):
        """Unknown positions should have neutral adjustment"""
        adj = SuccessIndexCalculator.calculate_position_adjustment(
            position='UNKNOWN',
            age=25,
            minutes=2000,
            goals_per90=0,
            tackles=0,
            interceptions=0,
            passes_pct=0
        )
        assert adj == 1.0


class TestCompleteCalculation:
    """Tests for calculate_success_index_v2_1 (integration)"""
    
    def test_complete_calculation_structure(self):
        """Result should have correct structure"""
        mock_db = Mock()
        mock_result = Mock()
        mock_result.avg_goals = 1.0
        mock_result.avg_assists = 0.8
        mock_result.avg_tackles = 40.0
        mock_result.avg_interceptions = 30.0
        mock_result.avg_passes_pct = 80.0
        mock_db.query.return_value.filter.return_value.first.return_value = mock_result
        
        player_data = {
            'league': 'Premier League',
            'minutes': 2500,
            'age': 25,
            'club': 'Test Club',
            'position': 'MF',
            'goals_per90': 0.3,
            'tackles': 60,
            'interceptions': 40,
            'passes_pct': 85
        }
        
        result = SuccessIndexCalculator.calculate_success_index_v2_1(
            success_index_base=0.85,
            player_data=player_data,
            db=mock_db
        )
        
        assert 'success_index_v2_1' in result
        assert 'breakdown' in result
        assert 'base' in result['breakdown']
        assert 'league_weight' in result['breakdown']
        assert 'minutes_weight' in result['breakdown']
        assert 'age_weight' in result['breakdown']
        assert 'team_strength_weight' in result['breakdown']
        assert 'position_adjustment' in result['breakdown']
    
    def test_optimal_player_high_score(self):
        """Optimal player should have high score"""
        mock_db = Mock()
        mock_result = Mock()
        mock_result.avg_goals = 1.5
        mock_result.avg_assists = 1.0
        mock_result.avg_tackles = 50.0
        mock_result.avg_interceptions = 40.0
        mock_result.avg_passes_pct = 85.0
        mock_db.query.return_value.filter.return_value.first.return_value = mock_result
        
        player_data = {
            'league': 'Premier League',
            'minutes': 2500,
            'age': 25,
            'club': 'Top Club',
            'position': 'MF',
            'goals_per90': 0.3,
            'tackles': 60,
            'interceptions': 40,
            'passes_pct': 85
        }
        
        result = SuccessIndexCalculator.calculate_success_index_v2_1(
            success_index_base=0.90,
            player_data=player_data,
            db=mock_db
        )
        
        # Optimal player should have score close to base
        assert result['success_index_v2_1'] >= 0.75
    
    def test_problematic_player_low_score(self):
        """Problematic player should have low score"""
        mock_db = Mock()
        mock_result = Mock()
        mock_result.avg_goals = 0.3
        mock_result.avg_assists = 0.2
        mock_result.avg_tackles = 20.0
        mock_result.avg_interceptions = 15.0
        mock_result.avg_passes_pct = 70.0
        mock_db.query.return_value.filter.return_value.first.return_value = mock_result
        
        player_data = {
            'league': 'J1 League',  # Tier 5
            'minutes': 300,  # Very few minutes
            'age': 34,  # Veteran
            'club': 'Weak Club',
            'position': 'FW',
            'goals_per90': 0.1,  # Low performance
            'tackles': 10,
            'interceptions': 5,
            'passes_pct': 65
        }
        
        result = SuccessIndexCalculator.calculate_success_index_v2_1(
            success_index_base=0.70,
            player_data=player_data,
            db=mock_db
        )
        
        # Problematic player should have very reduced score
        assert result['success_index_v2_1'] < 0.20
    
    def test_values_are_rounded(self):
        """Values should be rounded to 3 decimals"""
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        player_data = {
            'league': 'La Liga',
            'minutes': 1750,
            'age': 26,
            'club': 'Test Club',
            'position': 'DF'
        }
        
        result = SuccessIndexCalculator.calculate_success_index_v2_1(
            success_index_base=0.876543,
            player_data=player_data,
            db=mock_db
        )
        
        # Verify all values have maximum 3 decimals
        assert len(str(result['success_index_v2_1']).split('.')[-1]) <= 3
        for key, value in result['breakdown'].items():
            assert len(str(value).split('.')[-1]) <= 3

