"""Tests for :mod:`gando.utils.validators` -- the per-type regex/format
validators used to build the ``PhoneNumberField``/``UsernameField``/
``PasswordField`` model fields, and available standalone via ``Validator``.

These had zero test coverage before this pass despite gating what values are
accepted into usernames/passwords/emails/dates/colors/etc. across every
consuming project -- exactly the kind of "sensitive/critical" logic the
project's hardening passes are meant to cover.
"""

import datetime

import pytest
from django.core.exceptions import ValidationError

from gando.utils.validators.base import Validator
from gando.utils.validators.boolean import validate as validate_boolean
from gando.utils.validators.color import validate as validate_color
from gando.utils.validators.date import validate as validate_date
from gando.utils.validators.datetime import validate as validate_datetime
from gando.utils.validators.email import validate as validate_email
from gando.utils.validators.float import validate as validate_float
from gando.utils.validators.integer import validate as validate_integer
from gando.utils.validators.password import validate as validate_password
from gando.utils.validators.slug import validate as validate_slug
from gando.utils.validators.time import validate as validate_time
from gando.utils.validators.url import validate as validate_url
from gando.utils.validators.username import validate as validate_username


# --------------------------------------------------------------------- #
# username
# --------------------------------------------------------------------- #

@pytest.mark.parametrize('value', ['abcd', 'a-b_c', 'a1234567890'])
def test_username_accepts_valid_values(value):
    assert validate_username(value) == value


@pytest.mark.parametrize('value', [
    'AB', 'Abc',  # starts with/contains uppercase
    '1abc',  # starts with a digit
    'ab',  # too short (< 4 chars total)
    'a' + 'b' * 32,  # too long (33 total, over the 32-char max)
    'a b',  # space not allowed
])
def test_username_rejects_invalid_values(value):
    with pytest.raises(ValidationError):
        validate_username(value)


# --------------------------------------------------------------------- #
# password
# --------------------------------------------------------------------- #

@pytest.mark.parametrize('value', ['Abcdefg1', 'Str0ngPassword'])
def test_password_accepts_valid_values(value):
    assert validate_password(value) == value


@pytest.mark.parametrize('value', [
    'short1A',  # < 8 chars
    'alllowercase1',  # no uppercase
    'ALLUPPERCASE1',  # no lowercase
    'NoDigitsHere',  # no digit
])
def test_password_rejects_invalid_values(value):
    with pytest.raises(ValidationError):
        validate_password(value)


# --------------------------------------------------------------------- #
# email
# --------------------------------------------------------------------- #

@pytest.mark.parametrize('value', ['user@example.com', 'a.b+c@sub.example.co'])
def test_email_accepts_valid_values(value):
    assert validate_email(value) == value


@pytest.mark.parametrize('value', ['not-an-email', 'user@', '@example.com', 'user example.com'])
def test_email_rejects_invalid_values(value):
    with pytest.raises(ValidationError):
        validate_email(value)


# --------------------------------------------------------------------- #
# integer / float
# --------------------------------------------------------------------- #

@pytest.mark.parametrize('value,expected', [('0', 0), ('42', 42), (7, 7)])
def test_integer_accepts_valid_values(value, expected):
    assert validate_integer(value) == expected


@pytest.mark.parametrize('value', ['-1', '01', '1.5', 'abc'])
def test_integer_rejects_invalid_values(value):
    with pytest.raises(ValidationError):
        validate_integer(value)


@pytest.mark.parametrize('value,expected', [('0', 0.0), ('3.14', 3.14), ('42', 42.0)])
def test_float_accepts_valid_values(value, expected):
    assert validate_float(value) == expected


@pytest.mark.parametrize('value', ['-1.5', '01.5', 'abc'])
def test_float_rejects_invalid_values(value):
    with pytest.raises(ValidationError):
        validate_float(value)


# --------------------------------------------------------------------- #
# boolean
# --------------------------------------------------------------------- #

@pytest.mark.parametrize('value', ['t', 'T', 'true', 'True', '1'])
def test_boolean_accepts_truthy_values(value):
    assert validate_boolean(value) is True


@pytest.mark.parametrize('value', ['f', 'F', 'false', 'False', '0'])
def test_boolean_accepts_falsy_values(value):
    assert validate_boolean(value) is False


def test_boolean_rejects_unrecognized_value():
    with pytest.raises(ValidationError):
        validate_boolean('maybe')


# --------------------------------------------------------------------- #
# date / datetime / time
# --------------------------------------------------------------------- #

def test_date_accepts_valid_value():
    assert validate_date('2024-01-31') == datetime.date(2024, 1, 31)


@pytest.mark.parametrize('value', ['2024-13-01', '2024-01-32', '24-01-01', 'not-a-date'])
def test_date_rejects_invalid_value(value):
    with pytest.raises(ValidationError):
        validate_date(value)


def test_datetime_accepts_valid_value():
    assert validate_datetime('2024-01-31 12:30:00') == datetime.datetime(
        2024, 1, 31, 12, 30, 0)


@pytest.mark.parametrize('value', ['2024-01-31', '2024-01-31 25:00:00', 'garbage'])
def test_datetime_rejects_invalid_value(value):
    with pytest.raises(ValidationError):
        validate_datetime(value)


def test_time_accepts_valid_value():
    assert validate_time('23:59:59') == datetime.time(23, 59, 59)


@pytest.mark.parametrize('value', ['24:00:00', '12:60:00', 'noon'])
def test_time_rejects_invalid_value(value):
    with pytest.raises(ValidationError):
        validate_time(value)


# --------------------------------------------------------------------- #
# url
# --------------------------------------------------------------------- #

def test_url_accepts_value_without_scheme_by_prepending_https():
    assert validate_url('example.com') == 'https://example.com'


def test_url_accepts_value_with_scheme_unchanged():
    assert validate_url('http://example.com') == 'http://example.com'


def test_url_rejects_invalid_value():
    with pytest.raises(ValidationError):
        validate_url('not a url')


# --------------------------------------------------------------------- #
# color (regression: precedence bug in the alternation, see CHANGELOG)
# --------------------------------------------------------------------- #

@pytest.mark.parametrize('value', ['#FF0000', '#ff00ff00', 'FF0000', 'AABBCC'])
def test_color_accepts_valid_values(value):
    assert validate_color(value) == value


@pytest.mark.parametrize('value', [
    '#FF0000GARBAGE',  # trailing junk after a valid-looking prefix
    'GARBAGE#FF0000',  # leading junk before a valid-looking suffix
    '#12',  # too short
    'nothex',
])
def test_color_rejects_invalid_values(value):
    """Regression test: a prior unparenthesized ``|`` let trailing/leading
    junk around a valid-looking hex color through, because ``re.match``
    without a trailing ``$`` only anchors at the start of the string."""
    with pytest.raises(ValidationError):
        validate_color(value)


# --------------------------------------------------------------------- #
# slug
# --------------------------------------------------------------------- #

def test_slug_accepts_default_pattern():
    assert validate_slug('my-slug-123') == 'my-slug-123'


def test_slug_rejects_uppercase_by_default():
    with pytest.raises(ValidationError):
        validate_slug('My-Slug')


def test_slug_accepts_custom_pattern_and_message():
    assert validate_slug('ABC', pattern=r'^[A-Z]+$') == 'ABC'


# --------------------------------------------------------------------- #
# Validator dispatcher
# --------------------------------------------------------------------- #

@pytest.mark.parametrize('typ,value,expected', [
    ('username', 'abcd', 'abcd'),
    ('password', 'Abcdefg1', 'Abcdefg1'),
    ('email', 'user@example.com', 'user@example.com'),
    ('boolean', 'true', True),
    ('integer', '5', 5),
    ('float', '5.5', 5.5),
    ('slug', 'a-b', 'a-b'),
])
def test_validator_dispatch_routes_to_the_right_function(typ, value, expected):
    assert Validator(typ).validate(value) == expected


def test_validator_dispatch_rejects_unknown_type():
    with pytest.raises(ValidationError):
        Validator('not-a-real-type').validate('anything')
