from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate(value):
    _value = value
    if '://' not in value:
        _value = 'https://' + value
    validator = URLValidator()
    try:
        validator(_value)
        return _value
    except ValidationError:
        raise ValidationError(_(f"The string '{value}' is not a valid URL"))
