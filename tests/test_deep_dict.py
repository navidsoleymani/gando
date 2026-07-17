"""Tests for :func:`gando.utils.converters.deep_dict.any2dict`.

Used by ``gando.utils.parsers.images.Image.get_meta`` to turn a PIL image's
``__dict__`` (and arbitrary nested structures) into a plain, JSON-friendly
dict -- so it needs to handle nested containers, plain objects, exclusion
lists and depth limiting correctly.
"""

from gando.utils.converters.deep_dict import any2dict


class Point:
    """A plain object exposing attributes via ``__dict__``."""

    def __init__(self, x, y):
        self.x = x
        self.y = y


def test_none_passthrough():
    assert any2dict(None) is None


def test_scalars_passthrough():
    assert any2dict('a') == 'a'
    assert any2dict(1) == 1
    assert any2dict(1.5) == 1.5
    assert any2dict(True) is True


def test_nested_dict_is_recursively_converted():
    obj = {'a': {'b': Point(1, 2)}}
    result = any2dict(obj)
    assert result == {'a': {'b': {'x': 1, 'y': 2}}}


def test_list_and_tuple_and_set_are_converted_elementwise():
    assert any2dict([1, 'a']) == [1, 'a']
    assert any2dict((1, 'a')) == (1, 'a')
    assert any2dict({1, 2}) == {1, 2}


def test_plain_object_is_converted_via_dunder_dict():
    result = any2dict(Point(3, 4))
    assert result == {'x': 3, 'y': 4}


def test_object_without_dict_or_known_type_falls_back_to_str():
    # A plain ``object()`` instance has no ``__dict__`` and is none of the
    # known container/scalar types, so it degrades to its ``str()``.
    sentinel = object()
    assert any2dict(sentinel) == str(sentinel)


def test_exclude_removes_matching_keys_at_every_level():
    obj = {'keep': 1, 'secret': 2, 'nested': {'keep': 3, 'secret': 4}}
    result = any2dict(obj, exclude=['secret'])
    assert result == {'keep': 1, 'nested': {'keep': 3}}


def test_exclude_removes_matching_attrs_on_plain_objects():
    result = any2dict(Point(1, 2), exclude=['y'])
    assert result == {'x': 1}


def test_max_depth_truncates_to_string_beyond_limit():
    obj = {'a': {'b': {'c': {'d': 1}}}}
    # ``depth`` starts at 0 and is incremented *before* recursing, and the
    # cutoff check uses a strict ``>``, so with max_depth=1 two levels of
    # dict actually get expanded (depth 0 and depth 1 both pass the "depth >
    # max_depth" check) before the third level is truncated to ``str(obj)``.
    result = any2dict(obj, max_depth=1)
    assert result == {'a': {'b': str({'c': {'d': 1}})}}
