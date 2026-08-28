from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary using a variable key."""
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def sub(value, arg):
    """Subtract arg from value."""
    try:
        return value - arg
    except (ValueError, TypeError):
        return value


@register.filter
def mul(value, arg):
    """Multiply value by arg."""
    try:
        return value * arg
    except (ValueError, TypeError):
        return value


@register.filter
def div(value, arg):
    """Divide value by arg."""
    try:
        if arg == 0:
            return 0
        return value / arg
    except (ValueError, TypeError):
        return value