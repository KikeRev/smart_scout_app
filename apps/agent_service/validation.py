# apps/agent_service/validation.py
"""
Utilidades de validación para reducir alucinaciones en el agente de scouting.
"""

from typing import List, Dict, Any, Optional
import re


def validate_player_data(player_data: Dict[str, Any]) -> bool:
    """
    Valida que los datos de un jugador sean coherentes y completos.
    
    Args:
        player_data: Diccionario con datos del jugador
        
    Returns:
        bool: True si los datos son válidos, False en caso contrario
    """
    if not player_data:
        return False
    
    required_fields = ['id', 'full_name', 'team', 'position']
    for field in required_fields:
        if field not in player_data or not player_data[field]:
            return False
    
    # Validar que el ID sea un entero positivo
    try:
        player_id = int(player_data['id'])
        if player_id <= 0:
            return False
    except (ValueError, TypeError):
        return False
    
    # Validar que la posición sea válida
    valid_positions = ['GK', 'DF', 'MF', 'FW']
    if player_data['position'] not in valid_positions:
        return False
    
    return True


def validate_similar_players_data(players_list: List[Dict[str, Any]]) -> bool:
    """
    Valida que la lista de jugadores similares sea coherente.
    
    Args:
        players_list: Lista de diccionarios con datos de jugadores
        
    Returns:
        bool: True si los datos son válidos, False en caso contrario
    """
    if not players_list or not isinstance(players_list, list):
        return False
    
    # Verificar que todos los jugadores tengan datos válidos
    for player in players_list:
        if not validate_player_data(player):
            return False
    
    return True


def validate_news_data(news_data: List[Dict[str, Any]]) -> bool:
    """
    Valida que los datos de noticias sean coherentes.
    
    Args:
        news_data: Lista de diccionarios con datos de noticias
        
    Returns:
        bool: True si los datos son válidos, False en caso contrario
    """
    if not news_data or not isinstance(news_data, list):
        return False
    
    for news_item in news_data:
        if not isinstance(news_item, dict):
            return False
        
        # Verificar campos mínimos
        if 'title' not in news_item or 'content' not in news_item:
            return False
        
        # Verificar que el contenido no esté vacío
        if not news_item['content'].strip():
            return False
    
    return True


def validate_stats_data(stats_data: Dict[str, Any]) -> bool:
    """
    Valida que los datos estadísticos sean coherentes.
    
    Args:
        stats_data: Diccionario con estadísticas del jugador
        
    Returns:
        bool: True si los datos son válidos, False en caso contrario
    """
    if not stats_data or not isinstance(stats_data, dict):
        return False
    
    # Verificar que tenga al menos algunas estadísticas básicas
    required_stats = ['age', 'minutes_played', 'games_played']
    for stat in required_stats:
        if stat not in stats_data:
            return False
        
        # Verificar que sea un número válido
        try:
            value = float(stats_data[stat])
            if value < 0:
                return False
        except (ValueError, TypeError):
            return False
    
    return True


def sanitize_text(text: str) -> str:
    """
    Sanitiza texto para evitar caracteres problemáticos.
    
    Args:
        text: Texto a sanitizar
        
    Returns:
        str: Texto sanitizado
    """
    if not text:
        return ""
    
    # Eliminar caracteres de control
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    
    # Limitar longitud
    if len(text) > 10000:
        text = text[:10000] + "..."
    
    return text.strip()


def validate_parameters(params: Dict[str, Any], required_params: List[str]) -> bool:
    """
    Valida que los parámetros requeridos estén presentes y sean válidos.
    
    Args:
        params: Diccionario de parámetros
        required_params: Lista de parámetros requeridos
        
    Returns:
        bool: True si todos los parámetros son válidos, False en caso contrario
    """
    for param in required_params:
        if param not in params or params[param] is None:
            return False
    
    return True


def check_data_consistency(data1: Any, data2: Any, field: str) -> bool:
    """
    Verifica que dos conjuntos de datos sean consistentes en un campo específico.
    
    Args:
        data1: Primer conjunto de datos
        data2: Segundo conjunto de datos
        field: Campo a verificar
        
    Returns:
        bool: True si son consistentes, False en caso contrario
    """
    if not isinstance(data1, dict) or not isinstance(data2, dict):
        return False
    
    if field not in data1 or field not in data2:
        return False
    
    return data1[field] == data2[field]


def validate_age_range(age: int, min_age: int = 16, max_age: int = 45) -> bool:
    """
    Valida que la edad esté en un rango razonable.
    
    Args:
        age: Edad a validar
        min_age: Edad mínima permitida
        max_age: Edad máxima permitida
        
    Returns:
        bool: True si la edad es válida, False en caso contrario
    """
    try:
        age_int = int(age)
        return min_age <= age_int <= max_age
    except (ValueError, TypeError):
        return False


def validate_minutes_played(minutes: int) -> bool:
    """
    Valida que los minutos jugados sean razonables.
    
    Args:
        minutes: Minutos jugados
        
    Returns:
        bool: True si los minutos son válidos, False en caso contrario
    """
    try:
        minutes_int = int(minutes)
        return 0 <= minutes_int <= 5000  # Máximo razonable para una temporada
    except (ValueError, TypeError):
        return False
