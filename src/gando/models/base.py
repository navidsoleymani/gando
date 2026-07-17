"""Helpers for reading the current request/user from thread-local state.

These read the request stashed by
:class:`gando.middlewares.global_state.CurrentRequestMiddleware`, so they only
return meaningful values while a request is being processed (e.g. inside model
``save``/``delete`` paths triggered from a view). Outside a request — for
example in a management command, a shell, or a background task — they return
safe defaults.
"""

from django.core.exceptions import ObjectDoesNotExist

from gando.middlewares.global_state import CurrentRequestMiddleware


def global_request():
    """Return the current request from thread-local storage (or ``None``)."""
    return CurrentRequestMiddleware.get_request()


def current_user_id():
    """Return the current authenticated user's id, or ``None``.

    ``None`` is returned when there is no active request, the request has no
    resolvable user, or the user is anonymous. Only the expected lookup errors
    are caught (a previous bare ``except`` also swallowed unrelated failures).
    """
    try:
        return global_request().user.id
    except (AttributeError, ObjectDoesNotExist):
        return None


def current_user_agent_info():
    """Return the current request's user-agent info dict, or ``{}``.

    ``{}`` is returned when there is no active request or no ``uad`` (user
    agent device) info is attached to it. Only the expected lookup errors are
    caught (a previous bare ``except`` also swallowed unrelated failures).
    """
    try:
        return global_request().uad.to_dict()
    except (AttributeError, ObjectDoesNotExist):
        return {}
