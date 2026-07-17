from django.core.exceptions import ValidationError

from . import (
    boolean,
    color,
    date,
    datetime,
    email,
    float,
    integer,
    password,
    slug,
    time,
    url,
    username,
)


class Validator:
    def __init__(self, typ):
        self.typ = typ

    def validate(self, value, *args, **kwargs):
        match self.typ:
            case 'boolean':
                return boolean.validate(value, *args, **kwargs)
            case 'color':
                return color.validate(value, *args, **kwargs)
            case 'date':
                return date.validate(value, *args, **kwargs)
            case 'datetime':
                return datetime.validate(value, *args, **kwargs)
            case 'email':
                return email.validate(value, *args, **kwargs)
            case 'float':
                return float.validate(value, *args, **kwargs)
            case 'integer':
                return integer.validate(value, *args, **kwargs)
            case 'password':
                return password.validate(value, *args, **kwargs)
            case 'slug':
                return slug.validate(value, *args, **kwargs)
            case 'time':
                return time.validate(value, *args, **kwargs)
            case 'url':
                return url.validate(value, *args, **kwargs)
            case 'username':
                return username.validate(value, *args, **kwargs)
            case _:
                raise ValidationError('The type is not defined correctly.')
