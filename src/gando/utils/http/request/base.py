"""Helpers to mutate an (otherwise-immutable) DRF ``request.data`` in place.

Used by :meth:`gando.apis.base.GenericAPIView.adding_user_id_to_request_data`
to inject the authenticated user's id into ``request.data`` on every
``POST``/``PUT``/``PATCH`` -- a security-relevant helper (it is what lets a
view trust ``request.data['user']`` as the *authenticated* user rather than
whatever the client claims).
"""

from rest_framework.exceptions import APIException


def _has_request_data(request) -> bool:
    """Return whether ``request`` carries a (possibly empty) ``.data`` mapping.

    Only presence/``None``-ness is checked -- **not** truthiness. A previous
    version used ``hasattr(request, 'data') and request.data``, which treats
    an empty dict (``{}``, the common case for a client-supplied body that
    the server is expected to fill in entirely, e.g. an empty "like this
    post" request relying on the server to inject ``user``) as "no data",
    silently skipping the add/remove/change operation exactly when it was
    needed most.
    """
    return hasattr(request, 'data') and request.data is not None


def _request_mutable(req):
    if hasattr(req.data, '_mutable'):
        req.data._mutable = True
    return req


def _request_immutable(req):
    if hasattr(req.data, '_mutable'):
        req.data._mutable = False
    return req


def _request_adder(request, **kwargs):
    try:
        if not _has_request_data(request):
            return request

        request = _request_mutable(request)
        for k, v in kwargs.items():
            request.data[k] = v
        request = _request_immutable(request)

    except Exception as exc:
        rais = APIException(
            "You are not submitting your request correctly.", )
        rais.status_code = 409
        raise rais

    return request


def _request_remover(request, **kwargs):
    try:
        if not _has_request_data(request):
            return request

        request = _request_mutable(request)
        for k, _ in kwargs.items():
            del request.data[k]
        request = _request_immutable(request)

    except Exception as exc:
        rais = APIException(
            "You are not submitting your request correctly.", )
        rais.status_code = 409
        raise rais

    return request


def _request_changer(request, **kwargs):
    try:
        if not _has_request_data(request):
            return request

        request = _request_mutable(request)
        for key, new_key in kwargs.items():
            if key in request.data:
                request.data[new_key] = request.data[key]
                del request.data[key]
        request = _request_immutable(request)

    except Exception as exc:
        rais = APIException(
            "You are not submitting your request correctly.", )
        rais.status_code = 409
        raise rais

    return request


def request_updater(request, operation='add', **kwargs):
    """

    :param request:
    :param operation: add or del or chg
    :param kwargs:
    :return:
    """

    if operation == 'add':
        request = _request_adder(request, **kwargs)
    elif operation == 'del':
        request = _request_remover(request, **kwargs)
    elif operation == 'chg':
        request = _request_changer(request, **kwargs)
    return request
