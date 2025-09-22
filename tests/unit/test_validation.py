"""
Unit tests for validation functions.
"""

import pytest
from apps.agent_service.validation import (
    validate_player_data,
    validate_similar_players_data,
    validate_news_data,
    validate_stats_data,
    sanitize_text,
    validate_parameters,
    check_data_consistency,
    validate_age_range
)


class TestPlayerDataValidation:
    """Test cases for player data validation."""
    
    def test_validate_player_data_valid(self):
        """Test validation with valid player data."""
        valid_data = {
            'id': 1,
            'full_name': 'Lionel Messi',
            'team': 'Inter Miami',
            'position': 'FW'
        }
        assert validate_player_data(valid_data) is True
    
    def test_validate_player_data_empty(self):
        """Test validation with empty data."""
        assert validate_player_data({}) is False
        assert validate_player_data(None) is False
    
    def test_validate_player_data_missing_required_fields(self):
        """Test validation with missing required fields."""
        # Missing id
        data = {
            'full_name': 'Lionel Messi',
            'team': 'Inter Miami',
            'position': 'FW'
        }
        assert validate_player_data(data) is False
        
        # Missing full_name
        data = {
            'id': 1,
            'team': 'Inter Miami',
            'position': 'FW'
        }
        assert validate_player_data(data) is False
        
        # Missing team
        data = {
            'id': 1,
            'full_name': 'Lionel Messi',
            'position': 'FW'
        }
        assert validate_player_data(data) is False
        
        # Missing position
        data = {
            'id': 1,
            'full_name': 'Lionel Messi',
            'team': 'Inter Miami'
        }
        assert validate_player_data(data) is False
    
    def test_validate_player_data_invalid_id(self):
        """Test validation with invalid ID."""
        # Negative ID
        data = {
            'id': -1,
            'full_name': 'Lionel Messi',
            'team': 'Inter Miami',
            'position': 'FW'
        }
        assert validate_player_data(data) is False
        
        # Zero ID
        data = {
            'id': 0,
            'full_name': 'Lionel Messi',
            'team': 'Inter Miami',
            'position': 'FW'
        }
        assert validate_player_data(data) is False
        
        # Non-integer ID
        data = {
            'id': 'invalid',
            'full_name': 'Lionel Messi',
            'team': 'Inter Miami',
            'position': 'FW'
        }
        assert validate_player_data(data) is False
    
    def test_validate_player_data_invalid_position(self):
        """Test validation with invalid position."""
        data = {
            'id': 1,
            'full_name': 'Lionel Messi',
            'team': 'Inter Miami',
            'position': 'INVALID'
        }
        assert validate_player_data(data) is False
    
    def test_validate_player_data_valid_positions(self):
        """Test validation with all valid positions."""
        valid_positions = ['GK', 'DF', 'MF', 'FW']
        
        for position in valid_positions:
            data = {
                'id': 1,
                'full_name': 'Test Player',
                'team': 'Test Team',
                'position': position
            }
            assert validate_player_data(data) is True


class TestSimilarPlayersDataValidation:
    """Test cases for similar players data validation."""
    
    def test_validate_similar_players_data_valid(self):
        """Test validation with valid similar players data."""
        valid_data = [
            {
                'id': 1,
                'full_name': 'Player 1',
                'team': 'Team 1',
                'position': 'FW'
            },
            {
                'id': 2,
                'full_name': 'Player 2',
                'team': 'Team 2',
                'position': 'FW'
            }
        ]
        assert validate_similar_players_data(valid_data) is True
    
    def test_validate_similar_players_data_empty(self):
        """Test validation with empty list."""
        assert validate_similar_players_data([]) is False
        assert validate_similar_players_data(None) is False
    
    def test_validate_similar_players_data_invalid_players(self):
        """Test validation with invalid player data."""
        invalid_data = [
            {
                'id': 1,
                'full_name': 'Player 1',
                'team': 'Team 1',
                'position': 'FW'
            },
            {
                'id': 2,
                'full_name': 'Player 2',
                # Missing required fields
                'position': 'FW'
            }
        ]
        assert validate_similar_players_data(invalid_data) is False


class TestNewsDataValidation:
    """Test cases for news data validation."""
    
    def test_validate_news_data_valid(self):
        """Test validation with valid news data."""
        valid_data = {
            'title': 'Test News Title',
            'content': 'Test news content',
            'url': 'https://example.com/news',
            'published_date': '2024-01-15T10:30:00Z',
            'source': 'Test Source'
        }
        assert validate_news_data(valid_data) is True
    
    def test_validate_news_data_empty(self):
        """Test validation with empty data."""
        assert validate_news_data({}) is False
        assert validate_news_data(None) is False
    
    def test_validate_news_data_missing_required_fields(self):
        """Test validation with missing required fields."""
        # Missing title
        data = {
            'content': 'Test content',
            'url': 'https://example.com/news',
            'published_date': '2024-01-15T10:30:00Z',
            'source': 'Test Source'
        }
        assert validate_news_data(data) is False
        
        # Missing content
        data = {
            'title': 'Test Title',
            'url': 'https://example.com/news',
            'published_date': '2024-01-15T10:30:00Z',
            'source': 'Test Source'
        }
        assert validate_news_data(data) is False


class TestStatsDataValidation:
    """Test cases for stats data validation."""
    
    def test_validate_stats_data_valid(self):
        """Test validation with valid stats data."""
        valid_data = {
            'goals': 25,
            'assists': 15,
            'minutes': 2500,
            'goals_per90': 0.9,
            'assists_per90': 0.54
        }
        assert validate_stats_data(valid_data) is True
    
    def test_validate_stats_data_empty(self):
        """Test validation with empty data."""
        assert validate_stats_data({}) is False
        assert validate_stats_data(None) is False
    
    def test_validate_stats_data_negative_values(self):
        """Test validation with negative values."""
        data = {
            'goals': -5,
            'assists': 15,
            'minutes': 2500
        }
        assert validate_stats_data(data) is False


class TestTextSanitization:
    """Test cases for text sanitization."""
    
    def test_sanitize_text_normal(self):
        """Test sanitization of normal text."""
        text = "This is normal text"
        result = sanitize_text(text)
        assert result == "This is normal text"
    
    def test_sanitize_text_html(self):
        """Test sanitization of HTML content."""
        text = "<script>alert('xss')</script>Hello World"
        result = sanitize_text(text)
        assert "<script>" not in result
        assert "Hello World" in result
    
    def test_sanitize_text_special_chars(self):
        """Test sanitization of special characters."""
        text = "Text with &amp; &lt; &gt; entities"
        result = sanitize_text(text)
        assert "&amp;" not in result
        assert "&lt;" not in result
        assert "&gt;" not in result
    
    def test_sanitize_text_empty(self):
        """Test sanitization of empty text."""
        assert sanitize_text("") == ""
        assert sanitize_text(None) == ""


class TestParameterValidation:
    """Test cases for parameter validation."""
    
    def test_validate_parameters_valid(self):
        """Test validation with valid parameters."""
        params = {
            'player_id': 1,
            'k': 5,
            'position': 'FW'
        }
        required = ['player_id', 'k']
        assert validate_parameters(params, required) is True
    
    def test_validate_parameters_missing_required(self):
        """Test validation with missing required parameters."""
        params = {
            'player_id': 1,
            'position': 'FW'
        }
        required = ['player_id', 'k']
        assert validate_parameters(params, required) is False
    
    def test_validate_parameters_empty(self):
        """Test validation with empty parameters."""
        assert validate_parameters({}, ['player_id']) is False
        assert validate_parameters(None, ['player_id']) is False


class TestDataConsistency:
    """Test cases for data consistency checks."""
    
    def test_check_data_consistency_valid(self):
        """Test consistency check with valid data."""
        data = {
            'goals': 25,
            'minutes': 2500,
            'goals_per90': 0.9
        }
        assert check_data_consistency(data) is True
    
    def test_check_data_consistency_inconsistent(self):
        """Test consistency check with inconsistent data."""
        data = {
            'goals': 25,
            'minutes': 2500,
            'goals_per90': 2.0  # This should be 0.9 (25/2500*90)
        }
        assert check_data_consistency(data) is False


class TestAgeRangeValidation:
    """Test cases for age range validation."""
    
    def test_validate_age_range_valid(self):
        """Test validation with valid age range."""
        assert validate_age_range(20, 30) is True
        assert validate_age_range(18, 35) is True
        assert validate_age_range(25, 25) is True
    
    def test_validate_age_range_invalid(self):
        """Test validation with invalid age range."""
        assert validate_age_range(30, 20) is False  # min > max
        assert validate_age_range(-5, 30) is False  # negative min
        assert validate_age_range(20, 50) is False  # too wide range
        assert validate_age_range(10, 20) is False  # too young
    
    def test_validate_age_range_edge_cases(self):
        """Test validation with edge cases."""
        assert validate_age_range(16, 40) is True  # minimum valid range
        assert validate_age_range(17, 40) is False  # too young
        assert validate_age_range(16, 41) is False  # too wide
