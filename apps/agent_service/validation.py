# apps/agent_service/validation.py
"""
Validation utilities to reduce hallucinations in the scouting agent.
"""

from typing import List, Dict, Any, Optional
import re


def validate_player_data(player_data: Dict[str, Any]) -> bool:
    """
    Validates that player data is coherent and complete.
    
    Args:
        player_data: Dictionary with player data
        
    Returns:
        bool: True if data is valid, False otherwise
    """
    if not player_data:
        return False
    
    required_fields = ['id', 'full_name', 'team', 'position']
    for field in required_fields:
        if field not in player_data or not player_data[field]:
            return False
    
    # Validate that ID is a positive integer
    try:
        player_id = int(player_data['id'])
        if player_id <= 0:
            return False
    except (ValueError, TypeError):
        return False
    
    # Validate that position is valid
    valid_positions = ['GK', 'DF', 'MF', 'FW']
    if player_data['position'] not in valid_positions:
        return False
    
    return True


def validate_similar_players_data(players_list: List[Dict[str, Any]]) -> bool:
    """
    Validates that the similar players list is coherent.
    
    Args:
        players_list: List of dictionaries with player data
        
    Returns:
        bool: True if data is valid, False otherwise
    """
    if not players_list or not isinstance(players_list, list):
        return False
    
    # Check that all players have valid data
    for player in players_list:
        if not validate_player_data(player):
            return False
    
    return True


def validate_news_data(news_data: List[Dict[str, Any]]) -> bool:
    """
    Validates that news data is coherent.
    
    Args:
        news_data: List of dictionaries with news data
        
    Returns:
        bool: True if data is valid, False otherwise
    """
    if not news_data or not isinstance(news_data, list):
        return False
    
    for news_item in news_data:
        if not isinstance(news_item, dict):
            return False
        
        # Check minimum fields
        if 'title' not in news_item or 'content' not in news_item:
            return False
        
        # Check that content is not empty
        if not news_item['content'].strip():
            return False
    
    return True


def validate_stats_data(stats_data: Dict[str, Any]) -> bool:
    """
    Validates that statistical data is coherent.
    
    Args:
        stats_data: Dictionary with player statistics
        
    Returns:
        bool: True if data is valid, False otherwise
    """
    if not stats_data or not isinstance(stats_data, dict):
        return False
    
    # Check that it has at least some basic statistics
    required_stats = ['age', 'minutes_played', 'games_played']
    for stat in required_stats:
        if stat not in stats_data:
            return False
        
        # Check that it's a valid number
        try:
            value = float(stats_data[stat])
            if value < 0:
                return False
        except (ValueError, TypeError):
            return False
    
    return True


def sanitize_text(text: str) -> str:
    """
    Sanitizes text to avoid problematic characters.
    
    Args:
        text: Text to sanitize
        
    Returns:
        str: Sanitized text
    """
    if not text:
        return ""
    
    # Remove control characters
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    
    # Limit length
    if len(text) > 10000:
        text = text[:10000] + "..."
    
    return text.strip()


def validate_parameters(params: Dict[str, Any], required_params: List[str]) -> bool:
    """
    Validates that required parameters are present and valid.
    
    Args:
        params: Dictionary of parameters
        required_params: List of required parameters
        
    Returns:
        bool: True if all parameters are valid, False otherwise
    """
    for param in required_params:
        if param not in params or params[param] is None:
            return False
    
    return True


def check_data_consistency(data1: Any, data2: Any, field: str) -> bool:
    """
    Checks that two data sets are consistent in a specific field.
    
    Args:
        data1: First data set
        data2: Second data set
        field: Field to check
        
    Returns:
        bool: True if they are consistent, False otherwise
    """
    if not isinstance(data1, dict) or not isinstance(data2, dict):
        return False
    
    if field not in data1 or field not in data2:
        return False
    
    return data1[field] == data2[field]


def validate_age_range(age: int, min_age: int = 16, max_age: int = 45) -> bool:
    """
    Validates that age is in a reasonable range.
    
    Args:
        age: Age to validate
        min_age: Minimum allowed age
        max_age: Maximum allowed age
        
    Returns:
        bool: True if age is valid, False otherwise
    """
    try:
        age_int = int(age)
        return min_age <= age_int <= max_age
    except (ValueError, TypeError):
        return False


def validate_minutes_played(minutes: int) -> bool:
    """
    Validate that minutes played are reasonable.
    
    Args:
        minutes: Minutes played
        
    Returns:
        bool: True if minutes are valid, False otherwise
    """
    try:
        minutes_int = int(minutes)
        return 0 <= minutes_int <= 5000  # Maximum reasonable for a season
    except (ValueError, TypeError):
        return False
