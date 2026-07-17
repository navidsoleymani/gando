"""A ``json.JSONEncoder`` subclass that additionally serializes dates/datetimes."""

from json import JSONEncoder
import datetime


class Encoder(JSONEncoder):
    """Encode ``date``/``datetime`` as ISO-8601 strings; delegate everything else.

    ``JSONEncoder.default`` is only invoked for objects the base encoder does
    not already know how to serialize, and its return value is used *as the
    serialized substitute* for that object -- it is not a "can I handle
    this?" predicate. The previous implementation returned ``None`` (the
    implicit return of a function with no ``else`` branch) for every
    non-date/datetime type, which silently serialized any unsupported object
    (a ``Decimal``, a ``set``, a model instance, ...) as JSON ``null``
    instead of raising the standard
    ``TypeError: Object of type X is not JSON serializable``. That hid real
    bugs in callers (data quietly turning into ``null`` instead of erroring
    loudly). This now delegates to ``super().default(obj)`` for anything
    that isn't a date/datetime, restoring the standard ``JSONEncoder``
    contract.
    """

    def default(self, obj):
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        return super().default(obj)
