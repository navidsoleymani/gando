from __future__ import annotations

import contextlib
import importlib
import math
from inspect import currentframe, getframeinfo
from typing import Any, Dict, List, Optional, Tuple, Union, Iterable
from pydantic import BaseModel
import uuid

from django.core.exceptions import PermissionDenied
from django.db import connections
from django.http import Http404

from rest_framework import exceptions, status
from rest_framework.exceptions import ErrorDetail
from rest_framework.generics import (
    GenericAPIView as DRFGAPIView,
    CreateAPIView as DRFGCreateAPIView,
    ListAPIView as DRFGListAPIView,
    RetrieveAPIView as DRFGRetrieveAPIView,
    UpdateAPIView as DRFGUpdateAPIView,
    DestroyAPIView as DRFGDestroyAPIView,
)
from rest_framework.response import Response
from rest_framework.views import APIView

from gando.config import SETTINGS
from gando.http.api_exceptions.developers import (
    DeveloperResponseAPIMessage,
    DeveloperExceptionResponseAPIMessage,
    DeveloperErrorResponseAPIMessage,
    DeveloperWarningResponseAPIMessage,
)
from gando.http.api_exceptions.endusers import (
    EnduserResponseAPIMessage,
    EnduserFailResponseAPIMessage,
    EnduserErrorResponseAPIMessage,
    EnduserWarningResponseAPIMessage,
)
from gando.http.responses.string_messages import (
    InfoStringMessage,
    ErrorStringMessage,
    WarningStringMessage,
    LogStringMessage,
    ExceptionStringMessage,
)
from gando.utils.exceptions import PassException
from gando.utils.messages import (
    DefaultResponse100FailMessage,
    DefaultResponse200SuccessMessage,
    DefaultResponse201SuccessMessage,
    DefaultResponse300FailMessage,
    DefaultResponse400FailMessage,
    DefaultResponse401FailMessage,
    DefaultResponse403FailMessage,
    DefaultResponse404FailMessage,
    DefaultResponse421FailMessage,
    DefaultResponse500FailMessage,
)
from gando.utils.http.request import request_updater

# --------------------------------------------------------------------------- #
# Module docstring
# --------------------------------------------------------------------------- #
"""
gando.http.apis.base
--------------------

Opinionated DRF base APIs and view classes with standardized response envelopes,
exception handling, developer / end-user messaging channels, monitor hooks, cookie
staging, header staging, and request enrichment.

Goals:
- Provide a single consistent API response schema across your APIs (1.0.0 by default,
  optional compact 2.0.0).
- Centralize exception mapping so both developer and enduser messages are collected
  and returned in a consistent structure.
- Allow insertion of computed attributes into the request for downstream handlers
  via `SETTINGS.PASTE_TO_REQUEST`.
- Provide monitor hooks for lightweight telemetry / context enrichment using
  `SETTINGS.MONITOR` and `SETTINGS.MONITOR_KEYS`.
- Stage cookie header modifications (set/delete) and apply them during response finalization.
- Offer small helpers for converting filenames to media URLs and for standard CRUD views.

Important configuration expected from `gando.config.SETTINGS`:
- DEBUG: bool
- DEVELOPMENT_STATE: bool
- EXCEPTION_HANDLER: object with HANDLING: bool and COMMUNICATION_WITH_SOFTWARE_SUPPORT: Optional[str]
- MONITOR: dict[str, "module.path:funcname"]
- MONITOR_KEYS: list[str]
- PASTE_TO_REQUEST: dict[str, "module.path:funcname"]

Response schema:
- Default (Header absent or not "2.0.0"): `1.0.0` verbose envelope
- If header `Response-Schema-Version: 2.0.0` is present, a compact envelope is returned.
"""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _valid_user(user_id: Union[str, int, uuid.UUID], request) -> bool:
    """
    Fast-path identity check.

    Purpose
    -------
    Do a fast comparison between `user_id` (from path kwargs) and the authenticated
    user's `request.user.id`. This avoids an extra DB lookup.

    Behavior
    --------
    - Returns True when `request.user.id` exists and string-normalized equality holds.
    - Returns False on any exception or when `request.user.id` is None.

    Args
    ----
    user_id: str|int|uuid.UUID
        The identifier extracted from the URL/path kwargs.
    request: HttpRequest
        The incoming request whose authenticated user will be compared.

    Returns
    -------
    bool
        True when the ids match, False otherwise.

    Examples
    --------
    >>> _valid_user('123', request)
    True
    """
    try:
        req_uid = getattr(getattr(request, "user", None), "id", None)
        if req_uid is None:
            return False
        return str(req_uid) == str(user_id)
    except Exception:
        # defensive: if anything unexpected happens, treat as not valid
        return False


def set_rollback() -> None:
    """
    Mark all atomic DB connections for rollback.

    This mirrors DRF transactional behavior when an exception occurs. It iterates
    through registered DB connections, and for those that have `ATOMIC_REQUESTS`
    enabled and are currently inside an atomic block, it calls `set_rollback(True)`
    so outer transaction handlers will rollback accordingly.

    Side effects
    ------------
    - Marks transaction state for rollback on affected DB connections.
    """
    for db in connections.all():
        if db.settings_dict.get("ATOMIC_REQUESTS") and db.in_atomic_block:
            db.set_rollback(True)


# --------------------------------------------------------------------------- #
# Base API
# --------------------------------------------------------------------------- #


class BaseAPI(APIView):
    """
    Opinionated base class for DRF views.

    Features
    --------
    - Normalized response envelopes (1.0.0 verbose, opt-in 2.0.0 compact).
    - Centralized exception handling that maps library exceptions to enduser and
      developer messages.
    - Monitor hooks invoked from `SETTINGS.MONITOR`.
    - Request enrichment by running functions declared in `SETTINGS.PASTE_TO_REQUEST`.
    - Developer message streams (info, warnings, logs, exceptions) visible when
      `SETTINGS.DEVELOPMENT_STATE` is True and requester toggles header flags.
    - Cookie staging API (`cookie_setter` / `cookie_deleter`) — applied in finalize_response.
    - Helpers for media URL conversion and filename -> URL helpers.
    - Security helpers:
        * check_validate_user (validate path user == auth user)
        * adding_user_id_to_request_data (mutates request.data to include `user` or configured field)
        * for_user queryset filtering helper

    How to use
    ----------
    Inherit from BaseAPI in your DRF view classes. Implement `helper()` to set
    any response headers/messages before finalization.

    Example
    -------
    class MyView(BaseAPI, RetrieveAPIView):
        def helper(self):
            self.set_info_message('trace_id', 'abc123')
            self.set_headers('X-Server', 'v1')

    Notes
    -----
    - This class intentionally mixes APIView + GenericAPIView to keep compatibility
      with DRF mixins and generic view behavior.
    - Do not override finalize_response unless you fully replicate staging cookie/header behavior.
    """

    pagination: bool = True  # governs list envelope in 2.0.0 schema

    def __init__(self, **kwargs: Any) -> None:
        """
        Construct internal containers used during request handling.

        The constructor initializes:
        - public `.exc` for the last exception encountered.
        - private lists/dicts that aggregate messages, headers, cookies, monitor data, etc.

        These containers are intentionally private (double underscore) to avoid
        accidental external mutation.
        """
        super().__init__(**kwargs)
        # Public surface
        self.exc: Optional[BaseException] = None

        # Internal state containers (message streams, monitor, headers, cookies)
        self.__messenger: List[Dict[str, Any]] = []
        self.__data: Any = None

        self.__logs_message: List[Dict[str, Any]] = []
        self.__infos_message: List[Dict[str, Any]] = []
        self.__warnings_message: List[Dict[str, Any]] = []
        self.__errors_message: List[Dict[str, Any]] = []
        self.__exceptions_message: List[Dict[str, Any]] = []

        self.__monitor: Dict[str, Any] = {}

        self.__status_code: Optional[int] = None
        self.__headers: Dict[str, Any] = {}
        self.__cookies_for_set: List[Dict[str, Any]] = []
        self.__cookies_for_delete: List[str] = []

        self.__content_type: Optional[str] = None
        self.__exception_status: bool = False

    # ------------------------------ Request hooks --------------------------- #

    def __paste_to_request_func_loader(self, f: str, request, *args, **kwargs) -> Any:
        """
        Dynamically import and run a function declared in SETTINGS.PASTE_TO_REQUEST.

        Args
        ----
        f: str
            A string in the form 'pkg.module:function_name'.
        request: HttpRequest
            The request object to pass to the callable.
        *args, **kwargs:
            Additional args forwarded to the callable.

        Returns
        -------
        Any
            Whatever the configured function returns. If it raises PassException,
            a log message is added and None is returned (meaning "skip").

        Safety
        ------
        - Exceptions other than PassException will propagate out to the caller.
        """
        try:
            mod_name, func_name = f.rsplit(".", 1)
            mod = importlib.import_module(mod_name)
            func = getattr(mod, func_name)
            return func(request=request, *args, **kwargs)
        except PassException as exc:
            # Add a developer log when a hook explicitly signals a pass.
            frame_info = getframeinfo(currentframe())
            self.set_log_message(
                key="pass",
                value=f"message:{exc.args[0]}, file_name: {frame_info.filename}, line_number: {frame_info.lineno}")
            return None

    def paste_to_request_func_loader_play(self, request, *args, **kwargs):
        """
        Execute all configured PASTE_TO_REQUEST hooks and attach results to `request`.

        For each key, function string in `SETTINGS.PASTE_TO_REQUEST`, the function is executed;
        if a non-None result is returned, it will be set on the request as an attribute under `key`.

        Returns
        -------
        request
            The mutated request with additional attributes set by the hooks.

        Usage
        -----
        - Designed to be called during `initialize_request` so downstream logic can rely
          on pre-computed attributes (for example: `request.current_workspace`).
        """
        for key, f in SETTINGS.PASTE_TO_REQUEST.items():
            rslt = self.__paste_to_request_func_loader(f, request, *args, **kwargs)
            if rslt is not None:
                setattr(request, key, rslt)
        return request

    def initialize_request(self, request, *args, **kwargs):
        """
        DRF override: initialize and enrich the request before dispatch.

        Implementation detail
        ---------------------
        Calls the super implementation to get a DRF Request object and then applies
        `paste_to_request_func_loader_play` so configured attributes are available
        in `self.request` and in view logic.
        """
        request_ = super().initialize_request(request, *args, **kwargs)
        return self.paste_to_request_func_loader_play(request_)

    # ------------------------------ Exceptions ----------------------------- #

    def handle_exception(self, exc: BaseException) -> Response:
        """
        Central exception entrypoint for the view.

        This method:
        - Captures the exception in `.exc`.
        - If the exception is one of the custom Developer/Enduser message types,
          maps them into the appropriate internal message streams (info/error/warning).
        - Delegates to either `_handle_exception_gando_handling_true` or
          `_handle_exception_gando_handling_false` depending on
          `SETTINGS.EXCEPTION_HANDLER.HANDLING`.

        Notes
        -----
        - Developer messages (DeveloperResponseAPIMessage family) set internal
          developer streams and may set `.set_status_code`.
        - Enduser messages (EnduserResponseAPIMessage family) become messenger
          entries visible to endusers.

        Returns
        -------
        rest_framework.response.Response
            A DRF Response object. The response content body will be shaped later
            in `finalize_response`.
        """
        self.exc = exc

        # Developer-side messages
        if isinstance(exc, DeveloperResponseAPIMessage):
            if isinstance(exc, DeveloperErrorResponseAPIMessage):
                self.set_status_code(exc.status_code)
                self.set_error_message(key=exc.code, value=exc.message)
            elif isinstance(exc, DeveloperExceptionResponseAPIMessage):
                self.set_status_code(exc.status_code)
                self.set_exception_message(key=exc.code, value=exc.message)
            elif isinstance(exc, DeveloperWarningResponseAPIMessage):
                self.set_status_code(exc.status_code)
                self.set_warning_message(key=exc.code, value=exc.message)

        # Enduser-side messages
        if isinstance(exc, EnduserResponseAPIMessage):
            if isinstance(exc, EnduserErrorResponseAPIMessage):
                self.set_status_code(exc.status_code)
                self.add_error_message_to_messenger(code=exc.code, message=exc.message)
            elif isinstance(exc, EnduserFailResponseAPIMessage):
                self.set_status_code(exc.status_code)
                self.add_fail_message_to_messenger(code=exc.code, message=exc.message)
            elif isinstance(exc, EnduserWarningResponseAPIMessage):
                self.set_status_code(exc.status_code)
                self.add_warning_message_to_messenger(code=exc.code, message=exc.message)

        if SETTINGS.EXCEPTION_HANDLER.HANDLING:
            return self._handle_exception_gando_handling_true(exc)
        return self._handle_exception_gando_handling_false(exc)

    def exception_handler(self, exc: Exception, context: Dict[str, Any]) -> Optional[Response]:
        """
        Adapter to DRF standard exception detail shapes.

        Behavior
        --------
        - Converts `Http404` -> `exceptions.NotFound`
        - Converts Django `PermissionDenied` -> `exceptions.PermissionDenied`
        - When exc is an `exceptions.APIException`, it extracts authentication-related headers
          (`WWW-Authenticate`) and `Retry-After` where appropriate and flattens
          exception.details into internal error messages, then returns an empty
          Response with the correct status and headers.
        - Otherwise returns None (DRF fallback).

        Args
        ----
        exc: Exception
        context: dict
            DRF-provided context (view, request, etc).

        Returns
        -------
        Optional[Response]
        """
        if isinstance(exc, Http404):
            exc = exceptions.NotFound(*(exc.args))
        elif isinstance(exc, PermissionDenied):
            exc = exceptions.PermissionDenied(*(exc.args))

        if isinstance(exc, exceptions.APIException):
            headers: Dict[str, str] = {}
            if getattr(exc, "auth_header", None):
                headers["WWW-Authenticate"] = exc.auth_header
            if getattr(exc, "wait", None):
                headers["Retry-After"] = f"{int(exc.wait)}"

            # flatten DRF exception detail into internal error messages
            self._exception_handler_messages(exc.detail)
            set_rollback()
            return Response(status=exc.status_code, headers=headers)
        return None

    def _exception_handler_messages(self, msg: Any, base_key: Optional[str] = None) -> None:
        """
        Flattens nested DRF exception `detail` structures into error messages.

        DRF exceptions often carry nested dict/list structures; this utility walks those
        recursively and converts them into string messages stored by `set_error_message`.

        Args
        ----
        msg: Any
            The `detail` payload from a DRF `APIException`.
        base_key: Optional[str]
            The parent key used to build hierarchical keys for nested structures.
        """
        if isinstance(msg, list):
            for e in msg:
                self._exception_handler_messages(e)
        elif isinstance(msg, dict):
            for k, v in msg.items():
                self._exception_handler_messages(v, base_key=k)
        else:
            key = msg.code if hasattr(msg, "code") else "e"
            key = f"{base_key}__{key}" if base_key else key
            self.set_error_message(key=key, value=str(msg))

    def _handle_exception_gando_handling_true(self, exc: BaseException) -> Response:
        """
        When `SETTINGS.EXCEPTION_HANDLER.HANDLING` is True.

        Behavior
        --------
        - Attempt to map authentication errors to authentication headers where possible.
        - Run DRF's exception handler adapter; then build a helpful 421-style payload
          with supporting developer messages and a pointer to software support if configured.
        - Marks response.exception = True so that downstream finalize_response knows it's exceptional.

        Returns
        -------
        Response
        """
        if isinstance(exc, (exceptions.NotAuthenticated, exceptions.AuthenticationFailed)):
            auth_header = self.get_authenticate_header(self.request)
            if auth_header:
                exc.auth_header = auth_header  # type: ignore[attr-defined]
            else:
                exc.status_code = status.HTTP_403_FORBIDDEN  # type: ignore[attr-defined]

        context = self.get_exception_handler_context()
        response = self.exception_handler(exc, context) or Response()

        # Add a generic unexpected error entry visible to both developers (if allowed) and support
        self.set_exception_message(key="unexpectedError", value=exc.args)
        self.set_error_message(
            key="unexpectedError",
            value=(
                "An unexpected error has occurred based on your request type.\n"
                "Please do not repeat this request without changing your request.\n"
                "Be sure to read the documents on how to use this service correctly.\n"
                "In any case, discuss the issue with software support.\n"))
        self.set_warning_message(
            key="unexpectedError",
            value="Please discuss this matter with software support.")
        if SETTINGS.EXCEPTION_HANDLER.COMMUNICATION_WITH_SOFTWARE_SUPPORT:
            self.set_info_message(
                key="unexpectedError",
                value=(
                    "Please share this problem with our technical experts at the Email address "
                    f"'{SETTINGS.EXCEPTION_HANDLER.COMMUNICATION_WITH_SOFTWARE_SUPPORT}'."))
        self.set_status_code(421)
        response.exception = True
        return response

    def _handle_exception_gando_handling_false(self, exc: BaseException) -> Response:
        """
        When `SETTINGS.EXCEPTION_HANDLER.HANDLING` is False.

        Behavior
        --------
        - Try to convert authentication errors to auth headers as needed.
        - Fall back to DRF's default behavior by invoking the DRF exception handler.
        - If the handler returns None, re-raise (so DRF will process it).
        - Mark the response as exceptional and return it.
        """
        if isinstance(exc, (exceptions.NotAuthenticated, exceptions.AuthenticationFailed)):
            auth_header = self.get_authenticate_header(self.request)
            if auth_header:
                exc.auth_header = auth_header  # type: ignore[attr-defined]
            else:
                exc.status_code = status.HTTP_403_FORBIDDEN  # type: ignore[attr-defined]

        context = self.get_exception_handler_context()
        response = self.exception_handler(exc, context)
        if response is None:
            self.raise_uncaught_exception(exc)
        response.exception = True  # type: ignore[assignment]
        return response  # type: ignore[return-value]

    # ------------------------------ Finalization ---------------------------- #

    def finalize_response(self, request, response: Response, *args, **kwargs) -> Response:
        """
        DRF override that standardizes the final outgoing Response payload.

        Responsibilities
        ----------------
        - If mock-server behavior is enabled on the view and the request contains the header
          "Mock-Server-Status", short-circuit returning the mock payload.
        - If `response` is a DRF Response instance:
            * Calls `helper()` so subclasses can inject headers/messages.
            * Reads status/template/content_type/headers/exception and data from the incoming `response`.
            * Builds a new `Response` with normalized `data` using `response_context`.
            * Applies staged cookie set/delete operations.
        - Calls the parent `finalize_response` to allow DRF to apply any remaining behaviour.

        Important notes
        ---------------
        - Cookie mutations are not applied directly on the `Response` object until this
          finalization step. Use `cookie_setter` / `cookie_deleter` during view processing.
        """
        mock_server_status = self.request.headers.get("Mock-Server-Status") or False
        mock_server_switcher = getattr(self, "mock_server_switcher", False)
        if mock_server_switcher and mock_server_status and hasattr(self, "mock_server"):
            # If view is configured to use a mock server, call it and bypass normal finalization.
            return super().finalize_response(request, self.mock_server(), *args, **kwargs)

        if isinstance(response, Response):
            # Allow subclasses to set headers/messages before finalizing
            self.helper()

            template_name = getattr(response, "template_name", None)
            headers = self.get_headers(getattr(response, "headers", None))
            exception = self.get_exception_status(getattr(response, "exception", None))
            content_type = getattr(response, "content_type", None)
            status_code = self.get_status_code(getattr(response, "status_code", None))
            data = self.response_context(getattr(response, "data", None))

            # Build a new standardized Response (will be further handled by parent)
            response = Response(
                data=data,
                status=status_code,
                template_name=template_name,
                headers=headers,
                exception=exception,
                content_type=content_type)

            # Apply staged cookie mutations collected during view processing.
            for key in self.__cookies_for_delete:
                response.delete_cookie(key)
            for spec in self.__cookies_for_set:
                # spec is a dict emitted by Cookie.model_dump()
                response.set_cookie(**spec)
        return super().finalize_response(request, response, *args, **kwargs)

    # ------------------------------ Envelope -------------------------------- #

    def _response_validator(self, input_data: Any) -> Any:
        """
        Normalize empty collections to shapes serializers expect.

        For lists, recursively validate elements. For dicts, if empty return None
        (so JSON serializers that expect nullable dicts behave consistently).

        Args
        ----
        input_data: Any
            The payload to validate after envelope construction.

        Returns
        -------
        Any
            The normalized payload.
        """
        if isinstance(input_data, list):
            return [self._response_validator(i) for i in input_data] if input_data else []
        if isinstance(input_data, dict):
            if not input_data:
                return None
            return {k: self._response_validator(v) for k, v in input_data.items()}
        return input_data

    def response_context(self, data: Any = None) -> Dict[str, Any]:
        """
        Build the versioned response body according to requested schema version.

        The request header `Response-Schema-Version` controls whether the
        compact 2.0.0 schema is used. Default is the verbose 1.0.0 schema.

        Args
        ----
        data: Any
            The raw data to include in the envelope (usually result of view logic).

        Returns
        -------
        dict
            A fully built envelope (still subject to `_response_validator`).
        """
        self.response_schema_version = self.request.headers.get("Response-Schema-Version") or "1.0.0"
        if self.response_schema_version == "2.0.0":
            ret = self._response_context_v_2_0_0_response(data)
        else:
            ret = self._response_context_v_1_0_0_response(data)
        return self._response_validator(ret)

    def _response_context_v_1_0_0_response(self, data: Any = None) -> Dict[str, Any]:
        """
        Construct the verbose (1.0.0) response envelope.

        Envelope fields include:
        - success, status_code, has_warning, monitor, messenger, many, data
        - optional: development_messages, exception_status

        Args
        ----
        data: Any

        Returns
        -------
        dict
        """
        self.__data = self.__set_messages_from_data(data)

        status_code = self.get_status_code()
        data_block = self.validate_data()
        many = self.__many()
        monitor = self.__monitor

        has_warning = self.__has_warning()
        exception_status = self.get_exception_status()
        messages = self.__messages()
        success = self.__success()
        headers = self.get_headers()

        payload: Dict[str, Any] = {
            "success": success,
            "status_code": status_code,
            "has_warning": has_warning,
            "monitor": self.monitor_play(monitor),
            "messenger": self.__messenger,
            "many": many,
            "data": data_block}
        if self.__development_messages_display():
            payload["development_messages"] = messages
        if self.__exception_status_display():
            payload["exception_status"] = exception_status
        return payload

    def _response_context_v_2_0_0_response(self, data: Any = None) -> Dict[str, Any]:
        """
        Construct the compact (2.0.0) response envelope.

        Intended to be smaller and easier to parse by machines while still
        carrying messenger, success, and pagination metadata.

        Args
        ----
        data: Any

        Returns
        -------
        dict
        """
        self.__data = self.__set_messages_from_data(data)

        status_code = self.get_status_code()
        many = self.__many_v_2_0_0_response()
        monitor = self.__monitor
        exception_status = self.get_exception_status()
        messages = self.__messages()
        success = self.__success()
        headers = self.get_headers()

        payload: Dict[str, Any] = {
            "success": success,
            "status_code": status_code,
            "messenger": self.__messenger}
        payload.update(self.validate_data_v_2_0_0_response())

        if self.__development_messages_display():
            payload["development_messages"] = messages
        if self.__exception_status_display():
            payload["exception_status"] = exception_status
        return payload

    # ------------------------------ Messenger -------------------------------- #

    @staticmethod
    def __messenger_code_parser(x: Any) -> Union[int, str]:
        """
        Normalize message code into int or str.

        The input `x` might be:
        - an int
        - a string
        - an object holding `.code`
        - a dict with key "code"

        This helper attempts several access patterns and falls back to "-1".
        """
        if isinstance(x, (int, str)):
            return x
        with contextlib.suppress(Exception):
            return x.code
        with contextlib.suppress(Exception):
            return x.get("code")
        with contextlib.suppress(Exception):
            return "-1"
        return "-1"

    @staticmethod
    def __messenger_message_parser(x: Any) -> str:
        """
        Extract a readable message string from various possible message shaped inputs.

        Accepts:
        - plain string
        - objects with .detail, .details, .messages, .message
        - dict shapes with 'detail', 'details', 'messages', 'message'

        Returns a fallback 'Unknown problem. Please report to support.' if nothing meaningful found.
        """
        if isinstance(x, str):
            return x
        with contextlib.suppress(Exception):
            return x.detail
        with contextlib.suppress(Exception):
            return x.details[0]
        with contextlib.suppress(Exception):
            return x.details
        with contextlib.suppress(Exception):
            return x.messages[0]
        with contextlib.suppress(Exception):
            return x.messages
        with contextlib.suppress(Exception):
            return x.message
        with contextlib.suppress(Exception):
            return x.get("detail")
        with contextlib.suppress(Exception):
            return x.get("details")[0]
        with contextlib.suppress(Exception):
            return x.get("details")
        with contextlib.suppress(Exception):
            return x.get("messages")[0]
        with contextlib.suppress(Exception):
            return x.get("messages")
        with contextlib.suppress(Exception):
            return x.get("message")
        return "Unknown problem. Please report to support."

    def __add_to_messenger(self, *, message: Any, code: Any, type_: str) -> None:
        """
        Internal helper to append an entry to the `messenger` list.

        Each messenger entry is normalized to:
        {
            "type": type_,
            "code": <int|string>,
            "message": <string>
        }
        """
        self.__messenger.append(
            {
                "type": type_,
                "code": self.__messenger_code_parser(code),
                "message": self.__messenger_message_parser(message)})

    # convenience wrappers for common messenger types (fail/error/warning/success)
    def add_fail_message_to_messenger(self, *, message: Any, code: Any) -> None:
        self.__add_to_messenger(message=message, code=code, type_="FAIL")

    def add_error_message_to_messenger(self, *, message: Any, code: Any) -> None:
        self.__add_to_messenger(message=message, code=code, type_="ERROR")

    def add_warning_message_to_messenger(self, *, message: Any, code: Any) -> None:
        self.__add_to_messenger(message=message, code=code, type_="WARNING")

    def add_success_message_to_messenger(self, *, message: Any, code: Any) -> None:
        self.__add_to_messenger(message=message, code=code, type_="SUCCESS")

    # Developer streams (visible only in development mode if enabled)
    def set_log_message(self, key: str, value: Any) -> None:
        """Append a developer log (only visible in development messages)."""
        self.__logs_message.append({key: value})

    def set_info_message(self, key: str, value: Any) -> None:
        """Append developer informational message."""
        self.__infos_message.append({key: value})

    def set_warning_message(self, key: str, value: Any) -> None:
        """Append developer warning message."""
        self.__warnings_message.append({key: value})

    def set_error_message(self, key: str, value: Any) -> None:
        """Append developer error message."""
        self.__errors_message.append({key: value})

    def set_exception_message(self, key: str, value: Any) -> None:
        """Append developer exception message."""
        self.__exceptions_message.append({key: value})

    def set_headers(self, key: str, value: Any) -> None:
        """
        Stage a header to be included in the final response.

        Multiple calls with different keys will accumulate.
        """
        self.__headers[key] = value

    def get_headers(self, value: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Fetch currently staged headers. If `value` is provided, it is merged into staged headers.

        Returns
        -------
        dict
            The headers to apply on the response.
        """
        if value:
            for k, v in value.items():
                self.set_headers(k, v)
        return self.__headers

    def __messages(self) -> Dict[str, Any]:
        """
        Aggregate developer message streams into a single dict.

        When debug status is True, include 'log' and 'exception' channels as well.
        """
        tmp: Dict[str, Any] = {
            "info": self.__infos_message,
            "warning": self.__warnings_message,
            "error": self.__errors_message}
        if self.__debug_status:
            tmp["log"] = self.__logs_message
            tmp["exception"] = self.__exceptions_message
        return tmp

    # ------------------------------ Data shaping ---------------------------- #

    def __many(self) -> bool:
        """
        Heuristic: is the payload `many` (a list or a DRF paginator dict)?

        Returns True when:
        - `self.__data` is a list, or
        - it is a dict in the DRF paginator shape containing keys
          {'count', 'next', 'previous', 'results'}.
        """
        if isinstance(self.__data, list):
            return True
        if (isinstance(self.__data, dict) and
            {"count", "next", "previous", "results"}.issubset(self.__data.keys())):
            return True
        return False

    def __many_v_2_0_0_response(self) -> bool:
        """
        Same as __many but uses the v2.0.0 compact paginator key set.
        """
        if isinstance(self.__data, list):
            return True
        if (isinstance(self.__data, dict) and
            {"count", "next", "previous", "result"}.issubset(self.__data.keys())):
            return True
        return False

    def __fail_message_messenger(self) -> bool:
        """Return True when any messenger entry is FAIL or ERROR."""
        return any(msg.get("type") in {"FAIL", "ERROR"} for msg in self.__messenger)

    def __warning_message_messenger(self) -> bool:
        """Return True when any messenger entry is WARNING."""
        return any(msg.get("type") == "WARNING" for msg in self.__messenger)

    def __success(self) -> bool:
        """
        Determine overall success flag for response envelope.

        Logic:
        - True for 2xx HTTP codes.
        - Else True when there are no developer errors/exceptions, exception_status is False,
          and messenger does not contain FAIL/ERROR.
        """
        if 200 <= self.get_status_code() < 300:
            return True
        return (
            len(self.__errors_message) == 0
            and len(self.__exceptions_message) == 0
            and not self.__exception_status
            and not self.__fail_message_messenger()
        )

    def __has_warning(self) -> bool:
        """Return True when there are developer warnings and messenger warnings."""
        return bool(self.__warnings_message) and self.__warning_message_messenger()

    def set_status_code(self, value: int) -> None:
        """Stage a response status code for the view. Value must be 100 <= value < 600."""
        self.__status_code = value

    def get_status_code(self, value: Optional[int] = None) -> int:
        """
        Get currently staged status code.

        If `value` is provided and in the valid HTTP range (and not 200) it will be applied.
        Otherwise returns staged status or defaults to 200.
        """
        if value and 100 <= value < 600 and value != 200:
            self.set_status_code(value)
        return self.__status_code or 200

    def set_content_type(self, value: str) -> None:
        """Stage the content type for the response."""
        self.__content_type = value

    def get_content_type(self, value: Optional[str] = None) -> Optional[str]:
        """Get or set staged content type."""
        if value:
            self.set_content_type(value)
        return self.__content_type

    def set_exception_status(self, value: bool) -> None:
        """Stage an exception flag to be returned in the response body (if enabled)."""
        self.__exception_status = value

    def get_exception_status(self, value: Optional[bool] = None) -> bool:
        """Get or set the staged exception status flag."""
        if value is not None:
            self.set_exception_status(value)
        return self.__exception_status

    # ------------------------------ Monitor --------------------------------- #

    def set_monitor(self, key: str, value: Any) -> None:
        """
        Add a key/value pair to the local monitor data.

        Only keys present in `SETTINGS.MONITOR_KEYS` are allowed and will be used
        by `monitor_play` when merging with configured MONITOR hooks.
        """
        if key in self.__allowed_monitor_keys:
            self.__monitor[key] = value

    def __monitor_func_loader(self, f: str, *args, **kwargs) -> Any:
        """
        Dynamically import and call a monitor function from `SETTINGS.MONITOR`.

        The callable will be passed `request=self.request` plus any provided args/kwargs.
        If the callable raises PassException, it is logged and None is returned.
        """
        try:
            mod_name, func_name = f.rsplit(".", 1)
            mod = importlib.import_module(mod_name)
            func = getattr(mod, func_name)
            return func(request=self.request, *args, **kwargs)
        except PassException as exc:
            frame_info = getframeinfo(currentframe())
            self.set_log_message(
                key="pass",
                value=f"message:{exc.args[0]}, file_name: {frame_info.filename}, line_number: {frame_info.lineno}")
            return None

    def monitor_play(self, monitor: Optional[Dict[str, Any]] = None, *args, **kwargs) -> Dict[str, Any]:
        """
        Execute and merge global monitor hooks declared in SETTINGS.MONITOR.

        Returns a dict containing:
        - entries prepopulated from `monitor` param (if any)
        - entries computed by calling each function declared in SETTINGS.MONITOR

        Example
        -------
        SETTINGS.MONITOR = {
            "latency_ms": "myapp.metrics:get_latency_ms",
            "user_agent": "myapp.metrics:get_user_agent"
        }

        The returned dict will have keys 'latency_ms' and 'user_agent'.
        """
        monitor_out: Dict[str, Any] = dict(monitor or {})
        for key, f in SETTINGS.MONITOR.items():
            monitor_out[key] = self.__monitor_func_loader(f, *args, **kwargs)
        return monitor_out

    @property
    def __allowed_monitor_keys(self) -> Iterable[str]:
        """Expose the configured monitor keys (iterable)."""
        return SETTINGS.MONITOR_KEYS

    # ------------------------------ Data validators ------------------------- #

    def validate_data(self) -> Dict[str, Any]:
        """
        Normalize data into the 1.0.0 schema data block.

        Behavior
        --------
        - None -> adds a default messenger and returns {'result': {}}
        - str -> possibly treat as a dynamic message (special message classes) and return {'result': {'string': s}}
        - list -> returns a classic DRF paginator block with count/next/previous/results
        - dict -> wrapped with {'result': dict}
        - other -> returns {'result': {}}

        Returns
        -------
        dict
        """
        data = self.__data

        if data is None:
            self.__set_default_message()
            return {"result": {}}

        if isinstance(data, str):
            s = self.__set_dynamic_message(data)
            return {"result": {"string": s} if s else {}}

        if isinstance(data, list):
            return {
                "count": len(data),
                "next": None,
                "previous": None,
                "results": data}

        if isinstance(data, dict):
            return {"result": data}

        return {"result": {}}

    def validate_data_v_2_0_0_response(self) -> Dict[str, Any]:
        """
        Normalize data into the 2.0.0 compact schema.

        Behavior matches `validate_data` but uses compact keys:
        - list + pagination True -> count/next/previous/result
        - input paginator transformation: accepts DRF paginator shape or custom compact shape
        """
        data = self.__data

        if data is None:
            self.__set_default_message()
            return {"result": {}}

        if isinstance(data, str):
            s = self.__set_dynamic_message(data)
            return {"result": {"string": s} if s else {}}

        if isinstance(data, list):
            if self.pagination:
                return {"count": len(data), "next": None, "previous": None, "result": data}
            return {"result": data}

        if isinstance(data, dict):
            # Transform DRF paginator format
            if {"count", "next", "previous", "results"}.issubset(data.keys()):
                if self.pagination:
                    return {
                        "count": data.get("count"),
                        "next": data.get("next"),
                        "previous": data.get("previous"),
                        "result": data.get("results")}
                return {"result": data.get("results")}
            # Our compact paginator format
            if {"count", "page_size", "page_number", "result"}.issubset(data.keys()):
                n, p = self.__get_pagination_url(
                    page_size=int(data.get("page_size") or 0),
                    page_number=int(data.get("page_number") or 1),
                    count=int(data.get("count") or 0))
                if self.pagination:
                    return {"count": data.get("count"), "next": n, "previous": p, "result": data.get("result")}
                return {"result": data.get("result")}

            return {"result": data}

        return {"result": {}}

    @property
    def get_request_path(self) -> str:
        """Return the fully qualified path used to build pagination links."""
        return f"{self.get_host()}{self.request._request.path}"

    def __get_pagination_url(self, *, page_size: int, page_number: int, count: int) -> Tuple[
        Optional[str], Optional[str]]:
        """
        Build next/previous pagination URLs using page_size, page_number, and total count.

        Uses `math.ceil` to compute last page robustly.

        Returns
        -------
        (next_url, previous_url) or (None, None) when not applicable.

        Notes
        -----
        - If page_size <= 0 returns (None, None).
        - next and previous contain query param `page=<n>`.
        """
        if page_size <= 0:
            return None, None

        last_page = max(1, math.ceil(count / page_size)) if count > 0 else 1
        next_page_number = page_number + 1 if page_number < last_page else None
        prev_page_number = page_number - 1 if page_number > 1 else None

        next_page = f"{self.get_request_path}?page={next_page_number}" if next_page_number else None
        previous_page = f"{self.get_request_path}?page={prev_page_number}" if prev_page_number else None
        return next_page, previous_page

    # ------------------------------ Environment ----------------------------- #

    @property
    def __debug_status(self) -> bool:
        """True when SETTINGS.DEBUG is truthy (fast string-based check)."""
        return bool(str(SETTINGS.DEBUG).lower()[0] == 't')

    @property
    def __development_state(self) -> bool:
        """True when SETTINGS.DEVELOPMENT_STATE is truthy."""
        return bool(str(SETTINGS.DEVELOPMENT_STATE).lower()[0] == 't')

    def __development_messages_display(self) -> bool:
        """
        Toggle whether to include `development_messages` in responses.

        Controlled by:
        - global SETTINGS.DEVELOPMENT_STATE
        - request header `Development-Messages-Display` (defaults to "True")
        """
        if self.__development_state:
            return self.request.headers.get("Development-Messages-Display", "True") == "True"
        return False

    def __exception_status_display(self) -> bool:
        """
        Toggle whether to include `exception_status` in responses.

        Controlled by:
        - global SETTINGS.DEVELOPMENT_STATE
        - request header `Exception-Status-Display` (defaults to "True")
        """
        if self.__development_state:
            return self.request.headers.get("Exception-Status-Display", "True") == "True"
        return False

    # ------------------------------ Response helpers ------------------------ #

    def response(self, output_data: Any = None) -> Response:
        """
        Convenience: return a DRF `Response` that will be normalized during finalize_response.

        Usage
        -----
        Instead of `return Response(...)` in your views, use `return self.response(payload)`
        so that the final payload shape is controlled by BaseAPI.
        """
        return Response(output_data, status=self.get_status_code(), headers=self.get_headers())

    def get_host(self) -> str:
        """
        Obtain the request host (scheme + host) from the underlying WSGI request.

        Returns None when not available.
        """
        with contextlib.suppress(Exception):
            return self.request._request._current_scheme_host
        return None

    def append_host_to_url(self, value: str) -> str:
        """Shortcut to prepend host to a partial URL path."""
        return f"{self.get_host()}{value}"

    @staticmethod
    def get_media_url() -> str:
        """
        Return Django's MEDIA_URL setting.

        Useful for building absolute media URLs from stored file names.
        """
        from django.conf import settings

        return settings.MEDIA_URL

    def convert_filename_to_url(self, file_name: Optional[str]) -> Optional[str]:
        """Convert a stored filename into a relative media URL (MEDIA_URL + filename)."""
        return None if file_name is None else f"{self.get_media_url()}{file_name}"

    def convert_filename_to_url_localhost(self, file_name: Optional[str]) -> Optional[str]:
        """Convert a filename into a fully qualified URL using the request host + MEDIA_URL."""
        return None if file_name is None else f"{self.get_host()}{self.get_media_url()}{file_name}"

    def helper(self) -> None:
        """
        Hook for subclasses to set additional headers/messages/etc before finalize_response builds the payload.

        Intended usage:
        - set headers with `set_headers`
        - set developer messages with `set_info_message` / `set_error_message` etc
        - stage cookies using `cookie_setter`

        This method is intentionally a no-op here; override in child classes.
        """
        pass

    # ------------------------------ Default messages ------------------------ #

    def __default_message(self) -> str:
        """
        Return a human readable default message based on the staged status code.

        This method is used when a view returns no explicit message and we want to
        supply a reasonable default to be included in the development messages.
        """
        status_code = self.get_status_code()

        if 100 <= status_code < 200:
            return "please wait..."

        if 200 <= status_code < 300:
            return ("The desired object was created correctly."
                    if status_code == 201
                    else "Your request has been successfully registered.")

        if 300 <= status_code < 400:
            return "The requirements for your request are not available."

        if 400 <= status_code < 500:
            if status_code == 400:
                return "Bad Request..."
            if status_code == 401:
                return "Your authentication information is not available."
            if status_code == 403:
                return "You do not have access to this section."
            if status_code == 404:
                return "There is no information about your request."
            if status_code == 421:
                return (
                    "An unexpected error has occurred based on your request type.\n"
                    "Please do not repeat this request without changing your request.\n"
                    "Be sure to read the documents on how to use this service correctly.\n"
                    "In any case, discuss the issue with software support.\n")
            return "There was an error in how to send the request."

        if status_code >= 500:
            return "The server is unable to respond to your request."

        return "Undefined."

    def __default_messenger_message_adder(self) -> None:
        """
        Add a default messenger entry based on staged status code and current exception context.

        - If self.exc exists, try to derive a message/code from its attributes.
        - Uses the DefaultResponse* message models as fallbacks for each status band.
        """
        status_code = self.get_status_code()
        message = None
        with contextlib.suppress(Exception):
            message = self.exc.detail if self.exc else None  # type: ignore[attr-defined]

        self.__auto_default_messenger_message_adder(status_code, message)

    def __auto_default_messenger_message_adder(self, status_code, message, prefix_code=''):
        if isinstance(message, list):
            for m in message:
                self.__default_messenger_message_adder_detector(status_code, m, f'{prefix_code}{m.code}')
        elif isinstance(message, dict):
            for k, v in message.items():
                self.__auto_default_messenger_message_adder(status_code, v, f'{k}__')
        else:
            self.__default_messenger_message_adder_detector(status_code, message, f'{prefix_code}{message.code}')

    def __default_messenger_message_adder_detector(self, status_code, message, code):
        if 100 <= status_code < 200:
            self.__add_to_messenger(
                message=message or DefaultResponse100FailMessage.message,
                code=code or DefaultResponse100FailMessage.code,
                type_=DefaultResponse100FailMessage.type)
        elif 200 <= status_code < 300:
            if status_code == 201:
                self.__add_to_messenger(
                    message=message or DefaultResponse201SuccessMessage.message,
                    code=code or DefaultResponse201SuccessMessage.code,
                    type_=DefaultResponse201SuccessMessage.type)
            else:
                self.__add_to_messenger(
                    message=message or DefaultResponse200SuccessMessage.message,
                    code=code or DefaultResponse200SuccessMessage.code,
                    type_=DefaultResponse200SuccessMessage.type)
        elif 300 <= status_code < 400:
            self.__add_to_messenger(
                message=message or DefaultResponse300FailMessage.message,
                code=code or DefaultResponse300FailMessage.code,
                type_=DefaultResponse300FailMessage.type)
        elif 400 <= status_code < 500:
            mapping = {
                400: DefaultResponse400FailMessage,
                401: DefaultResponse401FailMessage,
                403: DefaultResponse403FailMessage,
                404: DefaultResponse404FailMessage,
                421: DefaultResponse421FailMessage}
            model = mapping.get(status_code, DefaultResponse400FailMessage)
            self.__add_to_messenger(
                message=message or model.message,
                code=code or model.code,
                type_=model.type)
        elif status_code >= 500:
            self.__add_to_messenger(
                message=message or DefaultResponse500FailMessage.message,
                code=code or DefaultResponse500FailMessage.code,
                type_=DefaultResponse500FailMessage.type)

    def __set_default_message(self) -> None:
        """
        Populate messenger and developer message streams with suitable defaults
        when no explicit data was provided by the view.
        """
        self.__default_messenger_message_adder()
        status_code = self.get_status_code()
        if 100 <= status_code < 200:
            self.set_warning_message("status_code_1xx", self.__default_message())
        elif 200 <= status_code < 300:
            self.set_info_message("status_code_2xx", self.__default_message())
        elif 300 <= status_code < 400:
            self.set_error_message("status_code_3xx", self.__default_message())
        elif 400 <= status_code < 500:
            self.set_error_message("status_code_4xx", self.__default_message())
        elif status_code >= 500:
            self.set_error_message("status_code_5xx", self.__default_message())
        else:
            self.set_error_message("status_code_xxx", self.__default_message())

    def __set_messages_from_data(self, data: Any) -> Any:
        """
        Recursively scan `data` and extract special dynamic messages.

        Special message objects are:
        - InfoStringMessage -> developer info
        - ErrorStringMessage / ErrorDetail -> developer error
        - WarningStringMessage -> developer warning
        - LogStringMessage -> developer log
        - ExceptionStringMessage -> developer exception

        The function strips these special objects out of the returned data structure
        (replacing them with None or removing them), and appends the corresponding developer
        stream entries to the internal containers.

        Returns
        -------
        Any
            The cleaned data structure with message objects removed.
        """
        if isinstance(data, str):
            return self.__set_dynamic_message(data)

        if isinstance(data, list):
            return [self.__set_messages_from_data(i) for i in data]

        if isinstance(data, dict):
            out: Dict[str, Any] = {}
            for k, v in data.items():
                out[k] = self.__set_messages_from_data(v)
            return out

        return data

    def __set_dynamic_message(self, value: Any) -> Optional[str]:
        """
        Detect if `value` is a special message instance and store it on the appropriate developer stream.

        Returns
        -------
        Optional[str]
            If `value` was a plain string, return it. If it was a special message,
            store it in developer stream and return None (so the message isn't duplicated
            in the result body).
        """
        if isinstance(value, InfoStringMessage):
            self.set_info_message(key=value.code, value=value)
            return None
        if isinstance(value, (ErrorStringMessage, ErrorDetail)):
            self.set_error_message(key=value.code, value=value)  # type: ignore[attr-defined]
            return None
        if isinstance(value, WarningStringMessage):
            self.set_warning_message(key=value.code, value=value)
            return None
        if isinstance(value, LogStringMessage):
            self.set_log_message(key=value.code, value=value)
            return None
        if isinstance(value, ExceptionStringMessage):
            self.set_exception_message(key=value.code, value=value)
            return None
        # plain string -> return for normal inclusion in data block
        return value

    # ------------------------------ Cookies --------------------------------- #

    class Cookie(BaseModel):
        """
        Pydantic model representing cookie set arguments.

        This model is used to validate and normalize cookie kwargs used by `cookie_setter`.
        - model_dump() is used to convert to a plain dict before set_cookie is called.
        """
        key: str
        value: Any = ""
        max_age: Optional[int] = None
        expires: Any = None
        path: str = "/"
        domain: Optional[str] = None
        secure: bool = False
        httponly: bool = False
        samesite: Optional[str] = None

    def cookie_getter(self, key: str) -> Optional[str]:
        """Return a cookie from the incoming request by key."""
        return self.request.COOKIES.get(key)

    def cookie_setter(self, key: str, **kwargs) -> None:
        """
        Stage a cookie to be set on the outgoing response.

        The kwargs follow Django's `set_cookie` API (max_age, expires, path, domain, secure, httponly, samesite).

        Example
        -------
        self.cookie_setter('sessionid', value='abc', httponly=True, secure=True)
        """
        self.__cookies_for_set.append(self.Cookie(key=key, **kwargs).model_dump())

    def cookie_deleter(self, key: str) -> None:
        """Stage a cookie for deletion on the outgoing response."""
        self.__cookies_for_delete.append(key)

    # ------------------------------ Query params ---------------------------- #

    @property
    def get_query_params_fields(self) -> Optional[List[str]]:
        """
        Parse `?fields=a,b,c` into a list of fields for serializers or projection.

        Returns None when the `fields` query param is not present.
        """
        fields = self.request.query_params.get("fields")
        return None if fields is None else fields.split(",")


class GenericAPIView(DRFGAPIView, BaseAPI):
    # ------------------------------ Security helpers ------------------------ #

    def get_check_validate_user(self) -> bool:
        """Return the boolean view attribute `check_validate_user` (defaults False)."""
        return getattr(self, "check_validate_user", False)

    def get_user_lookup_field(self) -> str:
        """Return the name of the URL kwarg used for user lookup (defaults to 'id')."""
        return getattr(self, "user_lookup_field", "id")

    def _checking_validate_user(self, request, *args, **kwargs) -> None:
        """
        If the view sets `check_validate_user=True`, ensure that the URL kwarg value
        equals the authenticated user's id. Raises PermissionDenied when mismatch occurs.

        This is a fast-path check that avoids DB hits by simply comparing stringified ids.
        """
        if self.get_check_validate_user():
            lookup_field = self.get_user_lookup_field()
            if not _valid_user(user_id=kwargs.get(lookup_field), request=request):
                raise PermissionDenied

    def get_user_field_name(self) -> str:
        """Return the field name used when injecting the user id into request.data (default 'user')."""
        return getattr(self, "user_field_name", "user")

    def get_add_user_id_to_request_data(self) -> bool:
        """Return whether request.data should be mutated to include the user id (defaults True)."""
        return getattr(self, "add_user_id_to_request_data", True)

    def adding_user_id_to_request_data(self) -> None:
        """
        Mutate request.data to include the authenticated user's id under the configured field.

        Uses `gando.utils.http.request.request_updater` to produce a new request object with updated `data`.
        """
        user_id = getattr(getattr(self.request, "user", None), "id", None)
        if not self.get_add_user_id_to_request_data():
            return
        params = {self.get_user_field_name(): user_id}
        self.request = request_updater(self.request, **params)

    def dispatch(self, request, *args, **kwargs):
        """
        `.dispatch()` is pretty much the same as Django's regular dispatch,
        but with extra hooks for startup, finalize, and exception handling.
        """
        self.args = args
        self.kwargs = kwargs
        request = self.initialize_request(request, *args, **kwargs)
        self.request = request
        self.headers = self.default_response_headers  # deprecate?

        try:
            self.initial(request, *args, **kwargs)

            method = request.method.lower()
            # Get the appropriate handler method
            if method in self.http_method_names:
                handler = getattr(
                    self, request.method.lower(),
                    self.http_method_not_allowed)
            else:
                handler = self.http_method_not_allowed

            self._checking_validate_user(request, *args, **kwargs)
            if method in ("post", "put", "patch"):
                self.adding_user_id_to_request_data()

            response = handler(request, *args, **kwargs)

        except Exception as exc:
            response = self.handle_exception(exc)

        self.response = self.finalize_response(request, response, *args, **kwargs)
        return self.response

    def get_for_user(self) -> bool:
        """Return whether this view should filter queryset for the authenticated user (defaults False)."""
        return getattr(self, "for_user", False)

    def get_user_field_name_id(self) -> str:
        """
        Return the name of the foreign key used in querysets, e.g. 'user_id'.
        If `user_field_name` already ends with '_id' return it unchanged.
        """
        base = self.get_user_field_name()
        return base if base.endswith("_id") else f"{base}_id"

    def get_queryset(self):
        """
        Override `get_queryset` to optionally filter by authenticated user when `for_user` is True.

        Expected behavior:
        - Calls super().get_queryset() to obtain the base queryset.
        - If get_for_user() True, filters `queryset.filter(<user_field> = request.user.id)`.
        """
        queryset = super().get_queryset()
        if self.get_for_user():
            return queryset.filter(**{self.get_user_field_name_id(): getattr(self.request.user, "id", None)})
        return queryset


# --------------------------------------------------------------------------- #
# Concrete Views
# --------------------------------------------------------------------------- #


class CreateAPIView(GenericAPIView, DRFGCreateAPIView):
    """Create-only endpoint with BaseAPI facilities."""
    pass


class ListAPIView(GenericAPIView, DRFGListAPIView):
    """List-only endpoint with BaseAPI facilities."""
    pass


class RetrieveAPIView(GenericAPIView, DRFGRetrieveAPIView):
    """Retrieve-only endpoint with BaseAPI facilities."""
    pass


class UpdateAPIView(GenericAPIView, DRFGUpdateAPIView):
    """Update-only endpoint with BaseAPI facilities."""
    pass


class DestroyAPIView(GenericAPIView, DRFGDestroyAPIView):
    """
    Destroy endpoint with optional soft-delete behavior.

    By default perform hard delete. To enable soft-delete behavior:
    - set view attribute `soft_delete = True`, or
    - pass `soft_delete=True` to `destroy()` as kwarg.

    Soft delete convention:
    - If the instance has an `available` field, it will be set to 0 and the instance saved.
      Adjust this convention to your model (e.g. `is_active=False`) as needed.
    """

    def get_soft_delete(self, soft_delete: Optional[bool] = None, **kwargs) -> bool:
        """
        Resolve whether a deletion should be soft.

        Priority:
        - explicit kwarg value
        - view attribute `self.soft_delete`
        - default False
        """
        if soft_delete is None:
            return getattr(self, "soft_delete", False)
        return bool(soft_delete)

    def destroy(self, request, *args, **kwargs) -> Response:
        """
        Standard DRF destroy override.

        Steps:
        - Retrieve the instance with `self.get_object()`
        - Call `perform_destroy` with resolved `soft_delete`
        - Return HTTP 204 NO CONTENT on success
        """
        instance = self.get_object()
        self.perform_destroy(instance=instance, soft_delete=self.get_soft_delete(**kwargs))
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance, soft_delete: bool = False) -> None:
        """
        Execute deletion behavior.

        - If `instance` is None, do nothing.
        - If `soft_delete` True and instance has attribute `available`, set it to 0 and save.
        - Otherwise, call instance.delete() to hard-delete.

        Note: adapt the `available` field convention to your app's soft-delete design.
        """
        if instance is None:
            return
        if soft_delete:
            # Convention: mark as unavailable. Adjust attribute to match your model.
            if hasattr(instance, "available"):
                instance.available = 0
            instance.save()
        else:
            instance.delete()
