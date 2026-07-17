"""Tests for :func:`gando.utils.http.request.request_updater` and its
``add``/``del``/``chg`` operations on ``request.data``.

This is what backs ``GenericAPIView.adding_user_id_to_request_data`` (see
``tests/test_api_base.py``), so its edge cases -- especially the "empty but
present ``request.data``" regression -- are covered directly here too.
"""

from types import SimpleNamespace

import pytest
from rest_framework.exceptions import APIException

from gando.utils.http.request import request_updater


def _request(data):
    return SimpleNamespace(data=data)


def test_add_operation_sets_keys_on_an_empty_dict():
    """Regression: an empty (but present) ``request.data`` used to be
    treated as "no data" and silently skipped."""
    request = _request({})
    result = request_updater(request, operation='add', user=42)
    assert result.data == {'user': 42}


def test_add_operation_merges_into_a_populated_dict():
    request = _request({'title': 'hello'})
    result = request_updater(request, operation='add', user=42)
    assert result.data == {'title': 'hello', 'user': 42}


def test_add_operation_defaults_to_add_when_no_operation_given():
    request = _request({})
    result = request_updater(request, user=42)
    assert result.data == {'user': 42}


def test_add_operation_is_a_noop_when_request_has_no_data_attribute():
    request = SimpleNamespace()
    result = request_updater(request, operation='add', user=42)
    assert result is request


def test_add_operation_is_a_noop_when_data_is_none():
    request = _request(None)
    result = request_updater(request, operation='add', user=42)
    assert result.data is None


def test_del_operation_removes_an_existing_key():
    request = _request({'user': 42, 'title': 'hello'})
    result = request_updater(request, operation='del', user=None)
    assert result.data == {'title': 'hello'}


def test_del_operation_on_missing_key_raises_api_exception_409():
    request = _request({'title': 'hello'})
    with pytest.raises(APIException) as exc_info:
        request_updater(request, operation='del', missing_key=None)
    assert exc_info.value.status_code == 409


def test_chg_operation_renames_an_existing_key():
    request = _request({'old_name': 'value'})
    result = request_updater(request, operation='chg', old_name='new_name')
    assert result.data == {'new_name': 'value'}


def test_chg_operation_is_a_noop_for_a_key_not_present():
    request = _request({'other': 'value'})
    result = request_updater(request, operation='chg', missing='renamed')
    assert result.data == {'other': 'value'}
