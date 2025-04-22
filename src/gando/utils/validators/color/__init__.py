import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate(value):
    """
    Validate HEX color format (e.g., #RRGGBB).
    """
    pattern = r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{8})$'
    if not re.match(pattern, value):
        raise ValidationError(
            _(f"{value} is not a valid color. Please enter a valid color code(#RRGGBB).")
        )
    return value
