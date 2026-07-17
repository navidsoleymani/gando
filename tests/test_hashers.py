"""Tests for :mod:`gando.utils.hashers` -- the password hashing helpers.

Thin wrappers around Django's own hasher registry, but security-relevant
(password storage/verification) and previously untested.
"""

from gando.utils.hashers import check_hash_string, make_hash_string


def test_make_hash_string_returns_none_for_none_value():
    assert make_hash_string(None) is None


def test_make_hash_string_produces_a_verifiable_hash():
    encoded = make_hash_string('correct-horse-battery-staple')
    assert encoded != 'correct-horse-battery-staple'
    assert check_hash_string('correct-horse-battery-staple', encoded) is True


def test_check_hash_string_rejects_wrong_value():
    encoded = make_hash_string('the-real-password')
    assert check_hash_string('a-wrong-guess', encoded) is False


def test_check_hash_string_rejects_empty_value():
    encoded = make_hash_string('the-real-password')
    assert check_hash_string('', encoded) is False
    assert check_hash_string(None, encoded) is False


def test_check_hash_string_returns_false_for_unrecognized_encoded_format():
    """An encoded string that no registered hasher can identify -> False,
    not an exception (``identify_hasher`` raises ``ValueError`` internally,
    which is caught)."""
    assert check_hash_string('anything', 'not-a-real-encoded-hash') is False


def test_check_hash_string_calls_setter_when_hasher_should_be_upgraded():
    """When the encoded hash is correct but was produced with a
    non-preferred/outdated hasher, ``setter`` is invoked with the plaintext
    value so the caller can persist a freshly-hashed value."""
    from django.contrib.auth.hashers import MD5PasswordHasher

    old_encoded = MD5PasswordHasher().encode('my-password', 'somesalt')

    calls = []
    result = check_hash_string(
        'my-password', old_encoded, setter=calls.append, preferred='default')

    assert result is True
    assert calls == ['my-password']
