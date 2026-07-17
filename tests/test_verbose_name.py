"""Tests for :func:`gando.models.fields.base.verbose_name`.

Used internally by ``ImageField.contribute_to_class`` to build the
``verbose_name`` of every generated sub-field (``<name>_category``,
``<name>_src``, etc.) from the parent field's own name, so it runs once per
sub-field for every ``ImageField`` on every model.
"""

from gando.models.fields.base import verbose_name


def test_single_word():
    assert verbose_name('avatar') == 'Avatar'


def test_snake_case_two_words():
    assert verbose_name('device_type') == 'Device Type'


def test_snake_case_three_words():
    assert verbose_name('user_profile_picture') == 'User Profile Picture'


def test_trailing_underscore_does_not_raise():
    """Regression: a trailing underscore (a common Python convention to
    avoid shadowing a builtin, e.g. ``type_``) used to raise ``IndexError``
    because the old char-by-char walk indexed one past the string end."""
    assert verbose_name('type_') == 'Type'


def test_leading_underscore_does_not_raise():
    assert verbose_name('_private') == 'Private'


def test_double_underscore_does_not_raise():
    assert verbose_name('a__b') == 'A B'


def test_empty_string_returns_unchanged():
    """Regression: an empty field name used to raise ``IndexError`` on
    ``value[0]``; it now returns the (empty) input unchanged."""
    assert verbose_name('') == ''


def test_all_underscores_returns_unchanged():
    assert verbose_name('___') == '___'
