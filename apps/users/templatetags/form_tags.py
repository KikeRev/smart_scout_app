from django import template

register = template.Library()

@register.filter
def add_class(field, css):
    """
    Uso: {{ field|add_class:"form-control" }}
    Añade/combina clases al widget de un campo de formulario.
    """
    existing = field.field.widget.attrs.get("class", "")
    combined = f"{existing} {css}".strip()
    return field.as_widget(attrs={"class": combined})
