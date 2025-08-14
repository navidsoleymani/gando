"""
Custom DRF API base classes with normalized response envelopes, unified exception handling,
developer/user messenger channels, monitor hooks, cookie/header staging, and request enrichment.

This module defines:
- BaseAPI: Core behavior (response shaping, exception handling, monitors, cookies, headers, helpers)
- CreateAPIView, ListAPIView, RetrieveAPIView, UpdateAPIView, DestroyAPIView: DRF views inheriting BaseAPI

Configuration expectations (from gando.config.SETTINGS):
- DEBUG: bool
- DEVELOPMENT_STATE: bool  # enables developer messages when True
- EXCEPTION_HANDLER: an object with:
    - HANDLING: bool
    - COMMUNICATION_WITH_SOFTWARE_SUPPORT: str | None (email or contact)
- MONITOR: dict[str, "pkg.mod:funcname"]  # functions called with request=...
- MONITOR_KEYS: list[str]  # allowed keys for monitor payload
- PASTE_TO_REQUEST: dict[str, "pkg.mod:funcname"]  # inject computed attributes into request

Response schema:
- Default: 1.0.0 (use header 'Response-Schema-Version: 2.0.0' to opt-in to the 2.x compact format)
"""

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
# Helpers
# --------------------------------------------------------------------------- #

def _valid_user(user_id: Union[str, int, uuid.UUID], request) -> bool:
    """
    Fast-path check: is the path/user identifier the same as the authenticated user's id?
    Avoids extra DB hits; normalizes to str before comparison.
    """
    try:
        req_uid = getattr(getattr(request, "user", None), "id", None)
        if req_uid is None:
            return False
        return str(req_uid) == str(user_id)
    except Exception:
        return False


def set_rollback() -> None:
    """
    Mark all atomic DB connections for rollback (mirrors DRF's transactional behavior).
    """
    for db in connections.all():
        if db.settings_dict.get("ATOMIC_REQUESTS") and db.in_atomic_block:
            db.set_rollback(True)


# --------------------------------------------------------------------------- #
# Base API
# --------------------------------------------------------------------------- #

class BaseAPI(APIView, DRFGAPIView):
    """
    Opinionated DRF API base class that:
      - shapes responses to a consistent schema (1.0.0/2.0.0),
      - unifies exception/reporting flows for end-users and developers,
      - supports monitor hooks and staged cookies/headers,
      - offers request enrichment and security helpers (user validation, user scoping).
    """

    pagination: bool = True  # governs list envelope in 2.0.0 schema

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # Public surface
        self.exc: Optional[BaseException] = None

        # Internal state
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
        try:
            mod_name, func_name = f.rsplit(".", 1)
            mod = importlib.import_module(mod_name)
            func = getattr(mod, func_name)
            return func(request=request, *args, **kwargs)
        except PassException as exc:
            frame_info = getframeinfo(currentframe())
            self.set_log_message(
                key="pass",
                value=f"message:{exc.args[0]}, file_name: {frame_info.filename}, line_number: {frame_info.lineno}")
            return None

    def paste_to_request_func_loader_play(self, request, *args, **kwargs):
        """
        Executes PASTE_TO_REQUEST hooks and sets their results on the request object.
        """
        for key, f in SETTINGS.PASTE_TO_REQUEST.items():
            rslt = self.__paste_to_request_func_loader(f, request, *args, **kwargs)
            if rslt is not None:
                setattr(request, key, rslt)
        return request

    def initialize_request(self, request, *args, **kwargs):
        """
        DRF override: initialize and enrich the request object before dispatch.
        """
        request_ = super().initialize_request(request, *args, **kwargs)
        return self.paste_to_request_func_loader_play(request_)

    # ------------------------------ Exceptions ----------------------------- #

    def handle_exception(self, exc: BaseException) -> Response:
        """
        Capture and map known Enduser/Developer exceptions to the messenger,
        then decide between our handler (HANDLING=True) vs DRF default.
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
        DRF-compatible exception handler adapter.
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

            self._exception_handler_messages(exc.detail)
            set_rollback()
            return Response(status=exc.status_code, headers=headers)
        return None

    def _exception_handler_messages(self, msg: Any, base_key: Optional[str] = None) -> None:
        """
        Flattens DRF exception detail structures into error messages.
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
        Coerce to a support-friendly 421 envelope with helpful messages and hints.
        """
        if isinstance(exc, (exceptions.NotAuthenticated, exceptions.AuthenticationFailed)):
            auth_header = self.get_authenticate_header(self.request)
            if auth_header:
                exc.auth_header = auth_header  # type: ignore[attr-defined]
            else:
                exc.status_code = status.HTTP_403_FORBIDDEN  # type: ignore[attr-defined]

        context = self.get_exception_handler_context()
        response = self.exception_handler(exc, context) or Response()

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
        Fall back to DRF default behavior where appropriate.
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
        DRF override: standardize the outgoing payload, apply cookies/headers, support mock mode.
        """
        mock_server_status = self.request.headers.get("Mock-Server-Status") or False
        mock_server_switcher = getattr(self, "mock_server_switcher", False)
        if mock_server_switcher and mock_server_status and hasattr(self, "mock_server"):
            return super().finalize_response(request, self.mock_server(), *args, **kwargs)

        if isinstance(response, Response):
            self.helper()

            template_name = getattr(response, "template_name", None)
            headers = self.get_headers(getattr(response, "headers", None))
            exception = self.get_exception_status(getattr(response, "exception", None))
            content_type = getattr(response, "content_type", None)
            status_code = self.get_status_code(getattr(response, "status_code", None))
            data = self.response_context(getattr(response, "data", None))

            response = Response(
                data=data,
                status=status_code,
                template_name=template_name,
                headers=headers,
                exception=exception,
                content_type=content_type)

            # Apply staged cookie mutations
            for key in self.__cookies_for_delete:
                response.delete_cookie(key)
            for spec in self.__cookies_for_set:
                response.set_cookie(**spec)
        return super().finalize_response(request, response, *args, **kwargs)

    # ------------------------------ Envelope -------------------------------- #

    def _response_validator(self, input_data: Any) -> Any:
        """
        Normalizes empty lists/dicts to consistent shapes that serializers expect.
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
        Build the versioned response body.
        """
        self.response_schema_version = self.request.headers.get("Response-Schema-Version") or "1.0.0"
        if self.response_schema_version == "2.0.0":
            ret = self._response_context_v_2_0_0_response(data)
        else:
            ret = self._response_context_v_1_0_0_response(data)
        return self._response_validator(ret)

    def _response_context_v_1_0_0_response(self, data: Any = None) -> Dict[str, Any]:
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
        self.__messenger.append(
            {
                "type": type_,
                "code": self.__messenger_code_parser(code),
                "message": self.__messenger_message_parser(message)})

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
        self.__logs_message.append({key: value})

    def set_info_message(self, key: str, value: Any) -> None:
        self.__infos_message.append({key: value})

    def set_warning_message(self, key: str, value: Any) -> None:
        self.__warnings_message.append({key: value})

    def set_error_message(self, key: str, value: Any) -> None:
        self.__errors_message.append({key: value})

    def set_exception_message(self, key: str, value: Any) -> None:
        self.__exceptions_message.append({key: value})

    def set_headers(self, key: str, value: Any) -> None:
        self.__headers[key] = value

    def get_headers(self, value: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if value:
            for k, v in value.items():
                self.set_headers(k, v)
        return self.__headers

    def __messages(self) -> Dict[str, Any]:
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
        if isinstance(self.__data, list):
            return True
        if (isinstance(self.__data, dict) and
            {"count", "next", "previous", "results"}.issubset(self.__data.keys())):
            return True
        return False

    def __many_v_2_0_0_response(self) -> bool:
        if isinstance(self.__data, list):
            return True
        if (isinstance(self.__data, dict) and
            {"count", "next", "previous", "result"}.issubset(self.__data.keys())):
            return True
        return False

    def __fail_message_messenger(self) -> bool:
        return any(msg.get("type") in {"FAIL", "ERROR"} for msg in self.__messenger)

    def __warning_message_messenger(self) -> bool:
        return any(msg.get("type") == "WARNING" for msg in self.__messenger)

    def __success(self) -> bool:
        if 200 <= self.get_status_code() < 300:
            return True
        return (
            len(self.__errors_message) == 0
            and len(self.__exceptions_message) == 0
            and not self.__exception_status
            and not self.__fail_message_messenger()
        )

    def __has_warning(self) -> bool:
        return bool(self.__warnings_message) and self.__warning_message_messenger()

    def set_status_code(self, value: int) -> None:
        self.__status_code = value

    def get_status_code(self, value: Optional[int] = None) -> int:
        if value and 100 <= value < 600 and value != 200:
            self.set_status_code(value)
        return self.__status_code or 200

    def set_content_type(self, value: str) -> None:
        self.__content_type = value

    def get_content_type(self, value: Optional[str] = None) -> Optional[str]:
        if value:
            self.set_content_type(value)
        return self.__content_type

    def set_exception_status(self, value: bool) -> None:
        self.__exception_status = value

    def get_exception_status(self, value: Optional[bool] = None) -> bool:
        if value is not None:
            self.set_exception_status(value)
        return self.__exception_status

    # ------------------------------ Monitor --------------------------------- #

    def set_monitor(self, key: str, value: Any) -> None:
        if key in self.__allowed_monitor_keys:
            self.__monitor[key] = value

    def __monitor_func_loader(self, f: str, *args, **kwargs) -> Any:
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
        monitor_out: Dict[str, Any] = dict(monitor or {})
        for key, f in SETTINGS.MONITOR.items():
            monitor_out[key] = self.__monitor_func_loader(f, *args, **kwargs)
        return monitor_out

    @property
    def __allowed_monitor_keys(self) -> Iterable[str]:
        return SETTINGS.MONITOR_KEYS

    # ------------------------------ Data validators ------------------------- #

    def validate_data(self) -> Dict[str, Any]:
        """
        Schema 1.0.0 “data” block normalization.
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
        Schema 2.0.0 normalization.
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
        return f"{self.get_host()}{self.request._request.path}"

    def __get_pagination_url(self, *, page_size: int, page_number: int, count: int) -> Tuple[
        Optional[str], Optional[str]]:
        """
        Builds next/previous links given (page_size, page_number, count).
        Uses math.ceil for a robust last-page calculation.
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
        return bool(str(SETTINGS.DEBUG).lower()[0] == 't')

    @property
    def __development_state(self) -> bool:
        return bool(str(SETTINGS.DEVELOPMENT_STATE).lower()[0] == 't')

    def __development_messages_display(self) -> bool:
        if self.__development_state:
            return self.request.headers.get("Development-Messages-Display", "True") == "True"
        return False

    def __exception_status_display(self) -> bool:
        if self.__development_state:
            return self.request.headers.get("Exception-Status-Display", "True") == "True"
        return False

    # ------------------------------ Response helpers ------------------------ #

    def response(self, output_data: Any = None) -> Response:
        """
        Shortcut for returning a Response that will be normalized in finalize_response.
        """
        return Response(output_data, status=self.get_status_code(), headers=self.get_headers())

    def get_host(self) -> str:
        with contextlib.suppress(Exception):
            return self.request._request._current_scheme_host
        return None

    def append_host_to_url(self, value: str) -> str:
        return f"{self.get_host()}{value}"

    @staticmethod
    def get_media_url() -> str:
        from django.conf import settings

        return settings.MEDIA_URL

    def convert_filename_to_url(self, file_name: Optional[str]) -> Optional[str]:
        return None if file_name is None else f"{self.get_media_url()}{file_name}"

    def convert_filename_to_url_localhost(self, file_name: Optional[str]) -> Optional[str]:
        return None if file_name is None else f"{self.get_host()}{self.get_media_url()}{file_name}"

    def helper(self) -> None:
        """
        Hook for subclasses to set additional headers/messages/etc before finalize_response builds the payload.
        """
        pass

    # ------------------------------ Default messages ------------------------ #

    def __default_message(self) -> str:
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
        status_code = self.get_status_code()
        message = None
        with contextlib.suppress(Exception):
            message = self.exc.detail if self.exc else None  # type: ignore[attr-defined]

        code = None
        with contextlib.suppress(Exception):
            code = self.exc.get_codes() if self.exc else None  # type: ignore[attr-defined]

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
        Recursively scan the data to extract dynamic Info/Error/Warning/Log/Exception string messages.
        Returns the same structure with those dynamic message objects stripped (converted to None or removed).
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
        # plain string
        return value

    # ------------------------------ Cookies --------------------------------- #

    class Cookie(BaseModel):
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
        return self.request.COOKIES.get(key)

    def cookie_setter(self, key: str, **kwargs) -> None:
        self.__cookies_for_set.append(self.Cookie(key=key, **kwargs).model_dump())

    def cookie_deleter(self, key: str) -> None:
        self.__cookies_for_delete.append(key)

    # ------------------------------ Query params ---------------------------- #

    @property
    def get_query_params_fields(self) -> Optional[List[str]]:
        """
        Parse `?fields=a,b,c` query param into a list. Returns None if not provided.
        """
        fields = self.request.query_params.get("fields")
        return None if fields is None else fields.split(",")

    # ------------------------------ Security helpers ------------------------ #

    def get_check_validate_user(self) -> bool:
        return getattr(self, "check_validate_user", False)

    def get_user_lookup_field(self) -> str:
        return getattr(self, "user_lookup_field", "id")

    def _checking_validate_user(self, request, *args, **kwargs) -> None:
        """
        If enabled, make sure the URL kwarg for the user equals the authenticated user id.
        """
        if self.get_check_validate_user():
            lookup_field = self.get_user_lookup_field()
            if not _valid_user(user_id=kwargs.get(lookup_field), request=request):
                raise PermissionDenied

    def get_user_field_name(self) -> str:
        return getattr(self, "user_field_name", "user")

    def get_add_user_id_to_request_data(self) -> bool:
        return getattr(self, "add_user_id_to_request_data", True)

    def adding_user_id_to_request_data(self) -> None:
        """
        Mutate request.data to include the authenticated user id under the configured field.
        """
        user_id = getattr(getattr(self.request, "user", None), "id", None)
        if not self.get_add_user_id_to_request_data():
            return
        params = {self.get_user_field_name(): user_id}
        self.request = request_updater(self.request, **params)

    def dispatch(self, request, *args, **kwargs):
        """
        Apply security check and user-id injection for write methods, then dispatch.
        """
        self._checking_validate_user(request, *args, **kwargs)
        method = request.method.lower()
        if method in ("post", "put", "patch"):
            self.adding_user_id_to_request_data()
        return super().dispatch(request, *args, **kwargs)

    def get_for_user(self) -> bool:
        return getattr(self, "for_user", False)

    def get_user_field_name_id(self) -> str:
        base = self.get_user_field_name()
        return base if base.endswith("_id") else f"{base}_id"

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.get_for_user():
            return queryset.filter(**{self.get_user_field_name_id(): getattr(self.request.user, "id", None)})
        return queryset


# --------------------------------------------------------------------------- #
# Concrete Views
# --------------------------------------------------------------------------- #

class CreateAPIView(BaseAPI, DRFGCreateAPIView):
    """Create-only endpoint with BaseAPI facilities."""
    pass


class ListAPIView(BaseAPI, DRFGListAPIView):
    """List-only endpoint with BaseAPI facilities."""
    pass


class RetrieveAPIView(BaseAPI, DRFGRetrieveAPIView):
    """Retrieve-only endpoint with BaseAPI facilities."""
    pass


class UpdateAPIView(BaseAPI, DRFGUpdateAPIView):
    """Update-only endpoint with BaseAPI facilities."""
    pass


class DestroyAPIView(BaseAPI, DRFGDestroyAPIView):
    """
    Destroy endpoint with optional soft-delete behavior.
    To enable soft delete, set either view attr `soft_delete=True` or pass kwarg `soft_delete=True`.
    """

    def get_soft_delete(self, soft_delete: Optional[bool] = None, **kwargs) -> bool:
        if soft_delete is None:
            return getattr(self, "soft_delete", False)
        return bool(soft_delete)

    def destroy(self, request, *args, **kwargs) -> Response:
        instance = self.get_object()
        self.perform_destroy(instance=instance, soft_delete=self.get_soft_delete(**kwargs))
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance, soft_delete: bool = False) -> None:
        if instance is None:
            return
        if soft_delete:
            # Convention: mark as unavailable. Adjust attribute to match your model.
            if hasattr(instance, "available"):
                instance.available = 0
            instance.save()
        else:
            instance.delete()
