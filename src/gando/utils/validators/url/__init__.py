from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate(value):
    validator = URLValidator()
    try:
        validator(value)
        return value
    except ValidationError:
        raise ValidationError(_(f"The string '{value}' is not a valid URL"))
