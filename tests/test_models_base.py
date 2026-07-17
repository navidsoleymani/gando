"""Tests for the request/user helpers in :mod:`gando.models.base`.

These confirm the narrowed exception handling (was a bare ``except``) still
returns safe defaults when there is no active request -- e.g. when running
outside the request/response cycle, as in these tests.
"""

from gando.models.base import current_user_agent_info, current_user_id


def test_current_user_id_returns_none_without_request():
    """No active request -> ``None`` (not an exception)."""
    assert current_user_id() is None


def test_current_user_agent_info_returns_empty_without_request():
    """No active request -> ``{}`` (not an exception)."""
    assert current_user_agent_info() == {}
