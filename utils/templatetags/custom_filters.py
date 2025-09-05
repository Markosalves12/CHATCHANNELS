from django import template
import os

register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def basename(value):
    """Retorna o nome base do caminho do arquivo."""
    return os.path.basename(value)