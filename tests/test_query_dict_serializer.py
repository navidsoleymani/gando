"""Regression tests for :class:`gando.models.serializers.QueryDictSerializer`.

These lock in the fixes for the three bugs documented in the README's
"Important notes, gotchas & recommended fixes" section:

* the ``__image_field_name_parser`` stale-``equal``/no-underscore bug,
* the fragile nested-dict ``__updater`` merge,
* the bare ``except`` in ``__media_url``.
"""

from gando.models.serializers import QueryDictSerializer


def test_double_underscore_nesting():
    """``a__b``/``a__c`` keys expand and merge into a single nested dict."""
    result = QueryDictSerializer()({"a__b": 1, "a__c": 2})
    assert result == {"a": {"b": 1, "c": 2}}


def test_deep_underscore_nesting():
    """Merging is deep: ``a__b__c`` and ``a__b__d`` share ``a`` and ``a.b``."""
    result = QueryDictSerializer()({"a__b__c": 1, "a__b__d": 2})
    assert result == {"a": {"b": {"c": 1, "d": 2}}}


def test_updater_multi_key_dict_is_not_lossy():
    """Deep-merge must not drop keys when the left dict has several keys.

    The old nested ``for``/``for`` ``__updater`` produced order-dependent,
    lossy output here; the new deep merge preserves every key.
    """
    result = QueryDictSerializer()(
        {"g__a": 1, "g__b": 2, "g__c": 3, "g__d": 4})
    assert result == {"g": {"a": 1, "b": 2, "c": 3, "d": 4}}


def test_image_field_prefix_grouping():
    """Image sub-fields are grouped under their prefix via a single ``_``."""
    serializer = QueryDictSerializer(image_fields_name=["avatar"])
    result = serializer({"avatar_width": 10, "avatar_height": 20})
    assert result == {"avatar": {"width": 10, "height": 20}}


def test_image_prefix_after_non_matching_prefix():
    """A later matching prefix still matches after an earlier non-match.

    This is the core "stale ``equal``" regression: with the old code, once the
    first (non-matching) prefix set ``equal = False`` it stayed ``False`` and
    the second, matching prefix was skipped.
    """
    serializer = QueryDictSerializer(image_fields_name=["banner", "avatar"])
    result = serializer({"avatar_width": 10})
    assert result == {"avatar": {"width": 10}}


def test_prefix_that_shares_leading_chars_is_not_split():
    """A field sharing leading chars with a prefix (no ``_``) is left intact.

    ``imagery`` must not be treated as image field ``image`` + ``ry``; the old
    char-by-char match raised ``IndexError`` on this shape.
    """
    serializer = QueryDictSerializer(image_fields_name=["image"])
    result = serializer({"imagery": 5})
    assert result == {"imagery": 5}


def test_src_key_is_prefixed_with_media_url():
    """A leaf key literally named ``src`` gets ``MEDIA_URL`` prepended."""
    result = QueryDictSerializer()({"src": "photo.png"})
    # tests.settings sets MEDIA_URL = "/media/"
    assert result == {"src": "/media/photo.png"}


def test_list_input_is_mapped_elementwise():
    """Lists are processed element by element."""
    result = QueryDictSerializer()([{"a__b": 1}, {"a__b": 2}])
    assert result == [{"a": {"b": 1}}, {"a": {"b": 2}}]


def test_scalar_passthrough():
    """Non dict/list values are returned unchanged."""
    assert QueryDictSerializer()("plain") == "plain"
