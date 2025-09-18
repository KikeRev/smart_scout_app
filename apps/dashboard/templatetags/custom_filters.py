from django import template

register = template.Library()

@register.filter
def replace(value, arg):
    """
    Reemplaza un carácter por otro en una cadena
    Uso: {{ value|replace:"_":" " }}
    """
    if not value:
        return value
    
    old, new = arg.split(':')
    return value.replace(old, new)

@register.filter
def format_metric(value):
    """
    Formatea una métrica para mostrar en el dashboard
    """
    if not value:
        return value
    
    # Reemplazar guiones bajos por espacios y capitalizar
    formatted = value.replace('_', ' ').title()
    return formatted
