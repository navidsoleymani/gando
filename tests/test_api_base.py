"""Tests for :mod:`gando.apis.base` -- the response envelope, exception-
message flattening, and the two security-relevant helpers every consuming
API view inherits: ``check_validate_user`` (URL-user-id vs. authenticated
-user-id) and ``adding_user_id_to_request_data`` (trusting the authenticated
user's id over anything the client puts in the request body).

None of this had any test coverage before this pass, despite being the
single most widely-used module in the library (every gando-based API view
class derives from ``BaseAPI``/``GenericAPIView``).
"""

from types import SimpleNamespace

import pytest
from django.core.exceptions import PermissionDenied
from rest_framework.exceptions import ErrorDetail

from gando.apis.base import BaseAPI, DestroyAPIView, GenericAPIView, _valid_user


def _fake_request(headers=None, query_params=None, path='/x/'):
    """Build a minimal stand-in for a DRF ``Request`` good enough for the
    handful of attributes ``BaseAPI``'s envelope-building code touches."""
    return SimpleNamespace(
        headers=headers or {},
        query_params=query_params or {},
        _request=SimpleNamespace(
            path=path, _current_scheme_host='http://testserver'),
    )


# --------------------------------------------------------------------- #
# _valid_user
# --------------------------------------------------------------------- #

def test_valid_user_matches_stringified_ids():
    request = SimpleNamespace(user=SimpleNamespace(id=42))
    assert _valid_user(42, request) is True
    assert _valid_user('42', request) is True


def test_valid_user_rejects_mismatched_ids():
    request = SimpleNamespace(user=SimpleNamespace(id=42))
    assert _valid_user(99, request) is False


def test_valid_user_false_when_no_user_id():
    request = SimpleNamespace(user=None)
    assert _valid_user(1, request) is False


def test_valid_user_false_on_unexpected_error():
    class Explode:
        @property
        def id(self):
            raise RuntimeError('boom')

    request = SimpleNamespace(user=Explode())
    assert _valid_user(1, request) is False


# --------------------------------------------------------------------- #
# response envelope (BaseAPI.response_context / validate_data)
# --------------------------------------------------------------------- #

def test_response_context_v1_wraps_dict_in_result():
    view = BaseAPI()
    view.request = _fake_request()
    payload = view.response_context({'id': 1})
    assert payload['data'] == {'result': {'id': 1}}
    assert payload['many'] is False


def test_response_context_v1_list_becomes_paginator_shape():
    view = BaseAPI()
    view.request = _fake_request()
    payload = view.response_context([1, 2, 3])
    assert payload['data'] == {
        'count': 3, 'next': None, 'previous': None, 'results': [1, 2, 3]}
    assert payload['many'] is True


def test_response_context_v1_none_defaults_to_empty_result():
    view = BaseAPI()
    view.request = _fake_request()
    payload = view.response_context(None)
    # ``_response_validator`` normalizes any *empty* dict (including the
    # ``{"result": {}}`` produced for ``data=None``) down to ``None``.
    assert payload['data'] == {'result': None}


def test_response_context_v2_uses_compact_pagination_keys():
    view = BaseAPI()
    view.request = _fake_request(headers={'Response-Schema-Version': '2.0.0'})
    payload = view.response_context([1, 2])
    assert payload['count'] == 2
    assert payload['result'] == [1, 2]


def test_success_true_for_2xx_even_with_a_stray_error_message():
    """``__success`` short-circuits to True for any 2xx status code,
    regardless of accumulated messenger content."""
    view = BaseAPI()
    view.request = _fake_request()
    view.set_status_code(201)
    view.add_error_message_to_messenger(message='should not matter', code='x')
    payload = view.response_context({'ok': True})
    assert payload['success'] is True


def test_success_false_for_4xx_with_error_in_messenger():
    view = BaseAPI()
    view.request = _fake_request()
    view.set_status_code(404)
    view.add_error_message_to_messenger(message='not found', code='not_found')
    payload = view.response_context({})
    assert payload['success'] is False
    assert payload['status_code'] == 404
    assert payload['messenger'][0] == {
        'type': 'ERROR', 'code': 'not_found', 'message': 'not found'}


def test_success_true_for_4xx_with_explicit_data_and_no_error_signal():
    """A non-2xx status with explicit (non-``None``) data and no developer
    error/exception and no FAIL/ERROR messenger entry is still success=True
    -- ``__success`` only looks at accumulated error signals, not the status
    code family, once outside the 2xx fast path."""
    view = BaseAPI()
    view.request = _fake_request()
    view.set_status_code(404)
    payload = view.response_context({'x': 1})
    assert payload['success'] is True


def test_exception_handler_messages_preserves_dict_key_when_value_is_a_list():
    """Regression: ``base_key`` used to be dropped when the value under a
    dict key was itself a list (the very common DRF validation shape
    ``{"field": ["This field is required."]}``), so the developer error
    message lost which field it was about."""
    view = BaseAPI()
    view.request = _fake_request()

    view._exception_handler_messages(
        {'field': [ErrorDetail('This field is required.', code='required')]})

    payload = view.response_context({})
    assert {'field__required': 'This field is required.'} in (
        payload['development_messages']['error'])


# --------------------------------------------------------------------- #
# GenericAPIView: check_validate_user / for_user / adding_user_id
# --------------------------------------------------------------------- #

def test_checking_validate_user_passes_when_ids_match():
    view = GenericAPIView()
    view.check_validate_user = True
    request = SimpleNamespace(user=SimpleNamespace(id=7))
    view._checking_validate_user(request, id=7)  # no exception


def test_checking_validate_user_raises_permission_denied_on_mismatch():
    view = GenericAPIView()
    view.check_validate_user = True
    request = SimpleNamespace(user=SimpleNamespace(id=7))
    with pytest.raises(PermissionDenied):
        view._checking_validate_user(request, id=999)


def test_checking_validate_user_is_a_noop_when_disabled():
    view = GenericAPIView()  # check_validate_user defaults to False
    request = SimpleNamespace(user=SimpleNamespace(id=7))
    view._checking_validate_user(request, id=999)  # no exception


def test_checking_validate_user_respects_custom_lookup_field():
    view = GenericAPIView()
    view.check_validate_user = True
    view.user_lookup_field = 'owner_id'
    request = SimpleNamespace(user=SimpleNamespace(id=7))
    view._checking_validate_user(request, owner_id=7)  # no exception
    with pytest.raises(PermissionDenied):
        view._checking_validate_user(request, owner_id=8)


def test_adding_user_id_to_request_data_injects_authenticated_user_id():
    """Regression: this used to silently no-op whenever ``request.data``
    started out as an empty dict (a falsy-but-present value), which is
    exactly the common "empty body, let the server fill in `user`" case."""
    view = GenericAPIView()
    view.request = SimpleNamespace(data={}, user=SimpleNamespace(id=42))

    view.adding_user_id_to_request_data()

    assert view.request.data == {'user': 42}


def test_adding_user_id_to_request_data_uses_custom_field_name():
    view = GenericAPIView()
    view.user_field_name = 'owner'
    view.request = SimpleNamespace(data={}, user=SimpleNamespace(id=42))

    view.adding_user_id_to_request_data()

    assert view.request.data == {'owner': 42}


def test_adding_user_id_to_request_data_disabled_via_flag():
    view = GenericAPIView()
    view.add_user_id_to_request_data = False
    view.request = SimpleNamespace(data={}, user=SimpleNamespace(id=42))

    view.adding_user_id_to_request_data()

    assert view.request.data == {}


def test_get_user_field_name_id_appends_suffix_once():
    view = GenericAPIView()
    assert view.get_user_field_name_id() == 'user_id'
    view.user_field_name = 'owner_id'
    assert view.get_user_field_name_id() == 'owner_id'


class _FakeQuerySet:
    """Records ``.filter(**kwargs)`` calls instead of hitting a real DB."""

    def __init__(self):
        self.filter_calls = []

    def filter(self, **kwargs):
        self.filter_calls.append(kwargs)
        return self


def test_get_queryset_filters_by_user_when_for_user_enabled():
    view = GenericAPIView()
    view.for_user = True
    fake_qs = _FakeQuerySet()
    view.queryset = fake_qs
    view.request = SimpleNamespace(user=SimpleNamespace(id=42))

    view.get_queryset()

    assert fake_qs.filter_calls == [{'user_id': 42}]


def test_get_queryset_does_not_filter_when_for_user_disabled():
    view = GenericAPIView()  # for_user defaults to False
    fake_qs = _FakeQuerySet()
    view.queryset = fake_qs
    view.request = SimpleNamespace(user=SimpleNamespace(id=42))

    view.get_queryset()

    assert fake_qs.filter_calls == []


# --------------------------------------------------------------------- #
# DestroyAPIView: soft vs. hard delete
# --------------------------------------------------------------------- #

class _FakeInstance:
    def __init__(self, available=1):
        self.available = available
        self.saved = False
        self.deleted = False

    def save(self):
        self.saved = True

    def delete(self):
        self.deleted = True


def test_perform_destroy_hard_deletes_by_default():
    view = DestroyAPIView()
    instance = _FakeInstance()
    view.perform_destroy(instance)
    assert instance.deleted is True
    assert instance.saved is False
    assert instance.available == 1


def test_perform_destroy_soft_deletes_when_requested():
    view = DestroyAPIView()
    instance = _FakeInstance()
    view.perform_destroy(instance, soft_delete=True)
    assert instance.deleted is False
    assert instance.saved is True
    assert instance.available == 0


def test_perform_destroy_none_instance_is_a_noop():
    view = DestroyAPIView()
    view.perform_destroy(None)  # no exception


def test_get_soft_delete_prefers_explicit_kwarg_over_view_attribute():
    view = DestroyAPIView()
    view.soft_delete = False
    assert view.get_soft_delete(soft_delete=True) is True
    assert view.get_soft_delete(soft_delete=False) is False


def test_get_soft_delete_falls_back_to_view_attribute():
    view = DestroyAPIView()
    view.soft_delete = True
    assert view.get_soft_delete() is True
