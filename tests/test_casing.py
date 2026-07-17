"""Tests for :func:`gando.utils.strings.converters.casing`.

Used internally by the ``start*`` scaffolding management commands to derive
file/class names in every naming convention (snake/camel/pascal/kebab) from
whatever the user typed on the command line, so incorrect conversions here
directly corrupt generated code.
"""

from gando.utils.strings.casings import CAMEL_CASE, KEBAB_CASE, PASCAL_CASE, SNAKE_CASE
from gando.utils.strings.converters import casing


def test_any_to_snake_from_pascal_input():
    assert casing('MyModelName') == 'my_model_name'


def test_any_to_snake_from_camel_input():
    assert casing('myModelName') == 'my_model_name'


def test_any_to_snake_from_kebab_input():
    assert casing('my-model-name') == 'my_model_name'


def test_any_to_camel():
    assert casing('my_model_name', to_case=CAMEL_CASE) == 'myModelName'


def test_any_to_pascal():
    assert casing('my_model_name', to_case=PASCAL_CASE) == 'MyModelName'


def test_any_to_kebab():
    assert casing('my_model_name', to_case=KEBAB_CASE) == 'my-model-name'


def test_snake_to_camel_explicit_from_case():
    assert casing('my_model_name', from_case=SNAKE_CASE, to_case=CAMEL_CASE) == 'myModelName'


def test_camel_to_snake_explicit_from_case():
    assert casing('myModelName', from_case=CAMEL_CASE, to_case=SNAKE_CASE) == 'my_model_name'


def test_pascal_to_kebab_explicit_from_case():
    assert casing('MyModelName', from_case=PASCAL_CASE, to_case=KEBAB_CASE) == 'my-model-name'


def test_kebab_to_pascal_explicit_from_case():
    assert casing('my-model-name', from_case=KEBAB_CASE, to_case=PASCAL_CASE) == 'MyModelName'


def test_leading_and_trailing_underscores_are_preserved():
    assert casing('__private_field__') == '__private_field__'


def test_leading_underscores_preserved_across_case_conversion():
    assert casing('__private_field', to_case=CAMEL_CASE) == '__privateField'


def test_empty_string_passthrough():
    assert casing('') == ''


def test_single_character_passthrough():
    assert casing('a') == 'a'
