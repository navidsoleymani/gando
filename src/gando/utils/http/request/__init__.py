from rest_framework.exceptions import APIException


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
        if not (hasattr(request, 'data') and request.data):
            return request

        request = _request_mutable(request)
        for k, v in kwargs.items():
            request.data[k] = v
        request = _request_immutable(request)

    except Exception as exc:
        rais = APIException("You are not submitting your request correctly.", )
        rais.status_code = 409
        raise rais

    return request


def _request_remover(request, **kwargs):
    try:
        if not (hasattr(request, 'data') and request.data):
            return request

        request = _request_mutable(request)
        for k, _ in kwargs.items():
            del request.data[k]
        request = _request_immutable(request)

    except Exception as exc:
        rais = APIException("You are not submitting your request correctly.", )
        rais.status_code = 409
        raise rais

    return request


def _request_changer(request, **kwargs):
    try:
        if not (hasattr(request, 'data') and request.data):
            return request

        request = _request_mutable(request)
        for key, new_key in kwargs.items():
            if key in request.data:
                request.data[new_key] = request.data[key]
                del request.data[key]
        request = _request_immutable(request)

    except Exception as exc:
        rais = APIException("You are not submitting your request correctly.", )
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
