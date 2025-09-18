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
