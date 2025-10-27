from django import template

register = template.Library()

@register.filter
def replace(value, arg):
    """
    Replaces one character with another in a string
    Usage: {{ value|replace:"_":" " }}
    """
    if not value:
        return value
    
    old, new = arg.split(':')
    return value.replace(old, new)

@register.filter
def format_metric(value):
    """
    Formats a metric for display in the dashboard
    """
    if not value:
        return value
    
    # Replace underscores with spaces and capitalize
    formatted = value.replace('_', ' ').title()
    return formatted

@register.filter(name='dict_get')
def dict_get(d, key):
    """Template helper: returns d[key]. Usage: {{ mydict|dict_get:var_key }}"""
    try:
        return d.get(key)
    except Exception:
        return None

@register.filter(name='player_id_of')
def player_id_of(player):
    """Safely returns the player id from dicts with different keys (id/player_id/pk)."""
    try:
        return player.get('id') or player.get('player_id') or player.get('pk')
    except Exception:
        return None
