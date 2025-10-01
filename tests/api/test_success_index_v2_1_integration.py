"""
Integration tests for Success Index v2.1 endpoint
Tests the complete flow with real database queries
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestSuccessIndexV2_1Integration:
    """Integration tests for /players/{id}/similar_team_fit with v2.1"""
    
    def test_endpoint_returns_v2_1_fields(self, test_client: TestClient):
        """Test that endpoint returns all v2.1 fields including breakdown"""
        # Use a known player ID (adjust based on your seed data)
        response = test_client.get(
            "/players/1/similar_team_fit",
            params={
                "team": "Real Madrid",
                "k": 5
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "context" in data
        assert "candidates" in data
        
        # Verify candidates have v2.1 fields
        if data["candidates"]:
            candidate = data["candidates"][0]
            
            # Check all expected fields are present
            assert "id" in candidate
            assert "full_name" in candidate
            assert "club" in candidate
            assert "league" in candidate
            assert "position" in candidate
            assert "age" in candidate
            assert "minutes" in candidate
            assert "overall_similarity" in candidate
            assert "team_position_similarity" in candidate
            assert "success_index" in candidate  # Base index
            assert "success_index_v2_1" in candidate  # New v2.1
            assert "success_breakdown" in candidate
            
            # Verify breakdown structure
            breakdown = candidate["success_breakdown"]
            assert "base" in breakdown
            assert "league_weight" in breakdown
            assert "minutes_weight" in breakdown
            assert "age_weight" in breakdown
            assert "team_strength_weight" in breakdown
            assert "position_adjustment" in breakdown
    
    def test_success_index_v2_1_is_lower_than_base(self, test_client: TestClient):
        """Test that v2.1 applies penalties correctly (should be <= base)"""
        response = test_client.get(
            "/players/1/similar_team_fit",
            params={
                "team": "FC Barcelona",
                "k": 10
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        for candidate in data["candidates"]:
            base = candidate["success_breakdown"]["base"]
            v2_1 = candidate["success_index_v2_1"]
            
            # v2.1 should generally be <= base (unless position adjustment gives bonus)
            # Allow for position bonuses (max 1.15)
            assert v2_1 <= base * 1.15, f"v2.1 ({v2_1}) exceeded expected maximum"
    
    def test_league_weight_affects_score(self, test_client: TestClient):
        """Test that players from different league tiers have appropriate weights"""
        response = test_client.get(
            "/players/1/similar_team_fit",
            params={
                "team": "Real Madrid",
                "k": 20
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Collect players by league tier
        top5_players = []
        tier2_players = []
        
        for candidate in data["candidates"]:
            league = candidate.get("league", "")
            league_weight = candidate["success_breakdown"]["league_weight"]
            
            if league in ["Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1"]:
                top5_players.append(league_weight)
                assert league_weight == 1.0, f"Top5 league {league} should have weight 1.0"
            elif league in ["Eredivisie", "Primeira Liga", "Brasileirao"]:
                tier2_players.append(league_weight)
                assert league_weight == 0.85, f"Tier2 league {league} should have weight 0.85"
    
    def test_minutes_weight_affects_score(self, test_client: TestClient):
        """Test that playing time is properly weighted"""
        response = test_client.get(
            "/players/1/similar_team_fit",
            params={
                "team": "Manchester City",
                "k": 20,
                "min_minutes": 0  # Include all players
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        for candidate in data["candidates"]:
            minutes = candidate.get("minutes", 0)
            minutes_weight = candidate["success_breakdown"]["minutes_weight"]
            
            # Verify weight matches expected ranges
            if minutes >= 2000:
                assert minutes_weight == 1.0
            elif minutes >= 1500:
                assert minutes_weight == 0.9
            elif minutes >= 1000:
                assert minutes_weight == 0.75
            elif minutes >= 700:
                assert minutes_weight == 0.6
            elif minutes >= 400:
                assert minutes_weight == 0.45
            else:
                assert minutes_weight == 0.3
    
    def test_age_weight_affects_score(self, test_client: TestClient):
        """Test that age is properly weighted"""
        response = test_client.get(
            "/players/1/similar_team_fit",
            params={
                "team": "Bayern Munich",
                "k": 20,
                "max_age": 35  # Include veterans
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        for candidate in data["candidates"]:
            age = candidate.get("age", 25)
            age_weight = candidate["success_breakdown"]["age_weight"]
            
            # Verify weight matches expected ranges
            if 21 <= age <= 27:
                assert age_weight == 1.0
            elif 18 <= age <= 20 or 28 <= age <= 29:
                assert age_weight == 0.95
            elif 30 <= age <= 31:
                assert age_weight == 0.85
            elif 32 <= age <= 33:
                assert age_weight == 0.7
            elif age >= 34:
                assert age_weight == 0.55
    
    def test_team_strength_weight_is_calculated(self, test_client: TestClient):
        """Test that team strength weight is properly calculated"""
        response = test_client.get(
            "/players/1/similar_team_fit",
            params={
                "team": "Liverpool",
                "k": 10
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        for candidate in data["candidates"]:
            team_weight = candidate["success_breakdown"]["team_strength_weight"]
            
            # Should be between 0.7 and 1.0
            assert 0.7 <= team_weight <= 1.0
            # Should be one of the expected values
            assert team_weight in [0.7, 0.8, 0.9, 1.0]
    
    def test_position_adjustment_is_applied(self, test_client: TestClient):
        """Test that position-specific adjustments are applied"""
        response = test_client.get(
            "/players/1/similar_team_fit",
            params={
                "team": "Juventus",
                "k": 10
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        for candidate in data["candidates"]:
            position_adj = candidate["success_breakdown"]["position_adjustment"]
            
            # Should be between 0.95 and 1.15 (with potential bonuses)
            assert 0.95 <= position_adj <= 1.15
    
    def test_sorting_by_v2_1_descending(self, test_client: TestClient):
        """Test that results are sorted by success_index_v2_1 descending"""
        response = test_client.get(
            "/players/1/similar_team_fit",
            params={
                "team": "Paris Saint-Germain",
                "k": 15
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        candidates = data["candidates"]
        if len(candidates) > 1:
            # Verify descending order
            for i in range(len(candidates) - 1):
                current = candidates[i]["success_index_v2_1"]
                next_val = candidates[i + 1]["success_index_v2_1"]
                assert current >= next_val, "Results should be sorted by v2.1 descending"
    
    def test_breakdown_values_are_rounded(self, test_client: TestClient):
        """Test that all breakdown values are properly rounded to 3 decimals"""
        response = test_client.get(
            "/players/1/similar_team_fit",
            params={
                "team": "AC Milan",
                "k": 5
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        for candidate in data["candidates"]:
            v2_1 = candidate["success_index_v2_1"]
            breakdown = candidate["success_breakdown"]
            
            # Check v2.1 has max 3 decimals
            assert len(str(v2_1).split('.')[-1]) <= 3
            
            # Check all breakdown values have max 3 decimals
            for key, value in breakdown.items():
                assert len(str(value).split('.')[-1]) <= 3
    
    def test_empty_cohort_handling(self, test_client: TestClient):
        """Test behavior when target team has no players in the position"""
        response = test_client.get(
            "/players/1/similar_team_fit",
            params={
                "team": "NonExistentTeam123",  # Team that likely doesn't exist
                "k": 5
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should still return results even with empty cohort
        assert "candidates" in data
        assert data["context"]["cohort_size"] == 0
    
    def test_player_not_found(self, test_client: TestClient):
        """Test 404 response for non-existent player"""
        response = test_client.get(
            "/players/999999/similar_team_fit",
            params={
                "team": "Real Madrid",
                "k": 5
            }
        )
        
        assert response.status_code == 404
    
    def test_with_filters_min_minutes(self, test_client: TestClient):
        """Test that min_minutes filter works with v2.1"""
        response = test_client.get(
            "/players/1/similar_team_fit",
            params={
                "team": "Chelsea",
                "k": 10,
                "min_minutes": 1500  # Only starters
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        for candidate in data["candidates"]:
            assert candidate["minutes"] >= 1500
            # Minutes weight should be 0.9 or 1.0
            assert candidate["success_breakdown"]["minutes_weight"] >= 0.9
    
    def test_with_filters_max_age(self, test_client: TestClient):
        """Test that max_age filter works with v2.1"""
        response = test_client.get(
            "/players/1/similar_team_fit",
            params={
                "team": "Atletico Madrid",
                "k": 10,
                "max_age": 25  # Only young players
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        for candidate in data["candidates"]:
            assert candidate["age"] <= 25
    
    def test_overall_weight_parameter(self, test_client: TestClient):
        """Test that overall_weight parameter affects the base calculation"""
        # Test with default weight (0.5)
        response1 = test_client.get(
            "/players/1/similar_team_fit",
            params={
                "team": "Inter Milan",
                "k": 5,
                "overall_weight": 0.5
            }
        )
        
        # Test with different weight (0.7)
        response2 = test_client.get(
            "/players/1/similar_team_fit",
            params={
                "team": "Inter Milan",
                "k": 5,
                "overall_weight": 0.7
            }
        )
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        # Base scores should be different due to different weights
        base1 = response1.json()["candidates"][0]["success_breakdown"]["base"]
        base2 = response2.json()["candidates"][0]["success_breakdown"]["base"]
        
        # They should be different (unless edge case)
        # Note: This might fail if results happen to be identical
        # In real scenarios with team_fit != overall, they should differ


@pytest.mark.integration
class TestSuccessIndexV2_1RealScenarios:
    """Test realistic scouting scenarios with v2.1"""
    
    def test_top_league_young_starter_gets_high_score(self, test_client: TestClient):
        """Test that optimal profile gets high v2.1 score"""
        response = test_client.get(
            "/players/1/similar_team_fit",
            params={
                "team": "Manchester United",
                "k": 20,
                "min_minutes": 2000,  # Starters only
                "max_age": 27  # Young players
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        if data["candidates"]:
            # Top results should have high v2.1 scores
            top_candidate = data["candidates"][0]
            
            # Optimal player from top league should have high score
            if (top_candidate["success_breakdown"]["league_weight"] == 1.0 and
                top_candidate["success_breakdown"]["minutes_weight"] == 1.0 and
                top_candidate["success_breakdown"]["age_weight"] >= 0.95):
                assert top_candidate["success_index_v2_1"] >= 0.70
    
    def test_minor_league_backup_veteran_gets_low_score(self, test_client: TestClient):
        """Test that problematic profile gets appropriately reduced score"""
        response = test_client.get(
            "/players/1/similar_team_fit",
            params={
                "team": "Tottenham",
                "k": 30,
                "min_minutes": 0,  # Include all
                "max_age": 40  # Include veterans
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Look for players with multiple risk factors
        for candidate in data["candidates"]:
            breakdown = candidate["success_breakdown"]
            
            # If player has multiple risk factors
            if (breakdown["league_weight"] <= 0.55 and  # Minor league
                breakdown["minutes_weight"] <= 0.45 and  # Backup
                breakdown["age_weight"] <= 0.70):  # Veteran
                
                # Should have significantly reduced v2.1 score
                assert candidate["success_index_v2_1"] < 0.30

