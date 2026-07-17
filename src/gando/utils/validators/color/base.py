import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate(value, *args, **kwargs):
    """
    Validate HEX color format (``#RRGGBB``/``#RRGGBBAA``, ``#`` optional).

    Notes
    -----
    The pattern is fully anchored and wraps the ``#``-optional/hex-length
    alternation in a single group: ``^#?(...)$``. A previous version wrote
    the equivalent of ``^(#(...))|(...)$`` -- because ``|`` has the lowest
    precedence in a regex, that actually meant "starts with ``#`` + 6/8 hex
    chars (anything may follow)" **or** "ends with 6/8 hex chars (anything
    may precede)", so strings like ``"#FF0000<script>"`` or
    ``"javascript:#FF0000"`` were incorrectly accepted by :func:`re.match`
    (which only anchors at the start, not the end, when the pattern itself
    has no trailing ``$`` on the matching branch).
    """
    pattern = r'^#?([A-Fa-f0-9]{6}|[A-Fa-f0-9]{8})$'
    if not re.match(pattern, value):
        raise ValidationError(
            _(f"{value} is not a valid color. Please enter a valid color code(#RRGGBB).")
        )
    return value
