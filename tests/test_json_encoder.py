"""Tests for :class:`gando.utils.json.encoders.Encoder` and :class:`gando.
utils.json.JSON`.

Regression coverage for the fix described in ``CHANGELOG.md``: unsupported
types must raise the standard ``TypeError`` (matching stdlib ``json``
behavior), not silently serialize as ``null``.
"""

import datetime
import json as stdlib_json

import pytest

from gando.utils.json import JSON
from gando.utils.json.encoders import Encoder


def test_dumps_serializes_date_as_isoformat_string():
    result = JSON.dumps({'d': datetime.date(2024, 1, 31)})
    assert stdlib_json.loads(result) == {'d': '2024-01-31'}


def test_dumps_serializes_datetime_as_isoformat_string():
    value = datetime.datetime(2024, 1, 31, 12, 0, 0)
    result = JSON.dumps({'dt': value})
    assert stdlib_json.loads(result) == {'dt': value.isoformat()}


def test_dumps_raises_type_error_for_unsupported_type_instead_of_silently_nulling():
    """Regression: the encoder used to swallow unsupported types as ``None``
    (serialized as JSON ``null``) instead of raising, hiding real bugs."""

    class Unsupported:
        pass

    with pytest.raises(TypeError):
        JSON.dumps({'x': Unsupported()})


def test_loads_round_trips_plain_json():
    assert JSON.loads('{"a": 1, "b": [1, 2, 3]}') == {'a': 1, 'b': [1, 2, 3]}


def test_encoder_default_delegates_to_base_class_for_non_date_types():
    encoder = Encoder()
    with pytest.raises(TypeError):
        encoder.default(object())
