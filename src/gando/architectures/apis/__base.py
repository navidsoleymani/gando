import contextlib
import importlib
from inspect import currentframe, getframeinfo
from typing import Any

from django.core.exceptions import PermissionDenied
from django.db import connections
from django.http import Http404
from pydantic import BaseModel
from rest_framework import exceptions
from rest_framework import status
from rest_framework.exceptions import ErrorDetail
from rest_framework.generics import (
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


def _valid_user(user_id, request):
    from django.contrib.auth import get_user_model

    try:
        obj = get_user_model().objects.get(id=request.user.id)
        obj_id = obj.id if isinstance(obj.id, int) else str(obj.id)
        if obj_id == user_id:
            return True
        return False
    except Exception as exc:
        return False


def set_rollback():
    for db in connections.all():
        if db.settings_dict['ATOMIC_REQUESTS'] and db.in_atomic_block:
            db.set_rollback(True)


class BaseAPI(APIView):
    pagination = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.__messenger = []

        self.__data = None

        self.__logs_message = []
        self.__infos_message = []
        self.__warnings_message = []
        self.__errors_message = []
        self.__exceptions_message = []

        self.__monitor: dict = dict()

        self.__status_code: int | None = None

        self.__headers: dict = dict()
        self.__cookies_for_set: list = list()
        self.__cookies_for_delete: list = list()

        self.__content_type: str | None = None
        self.__exception_status: bool = False
        self.exc = None

    def __paste_to_request_func_loader(self, f, request, *args, **kwargs):
        try:
            mod_name, func_name = f.rsplit('.', 1)
            mod = importlib.import_module(mod_name)
            func = getattr(mod, func_name)

            return func(request=request, *args, **kwargs)
        except PassException as exc:
            frame_info = getframeinfo(currentframe())
            self.set_log_message(
                key='pass',
                value=f"message:{exc.args[0]}, "
                      f"file_name: {frame_info.filename}, "
                      f"line_number: {frame_info.lineno}")
            return None

    def paste_to_request_func_loader_play(self, request, *args, **kwargs):
        for key, f in SETTINGS.PASTE_TO_REQUEST.items():
            rslt = self.__paste_to_request_func_loader(f, request, *args, **kwargs)
            if rslt:
                setattr(request, key, rslt)

        return request

    def initialize_request(self, request, *args, **kwargs):

        request_ = super().initialize_request(request, *args, **kwargs)
        rslt = self.paste_to_request_func_loader_play(request_)
        ret = rslt
        return ret

    def handle_exception(self, exc):
        self.exc = exc
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

    def exception_handler(self, exc, context):
        """
        Returns the response that should be used for any given exception.

        By default, we handle the REST framework `APIException`, and also
        Django's built-in `Http404` and `PermissionDenied` exceptions.

        Any unhandled exceptions may return `None`, which will cause a 500 error
        to be raised.
        """
        if isinstance(exc, Http404):
            exc = exceptions.NotFound(*(exc.args))
        elif isinstance(exc, PermissionDenied):
            exc = exceptions.PermissionDenied(*(exc.args))

        if isinstance(exc, exceptions.APIException):
            headers = {}
            if getattr(exc, 'auth_header', None):
                headers['WWW-Authenticate'] = exc.auth_header
            if getattr(exc, 'wait', None):
                headers['Retry-After'] = '%d' % exc.wait

            self._exception_handler_messages(exc.detail)

            set_rollback()
            return Response(status=exc.status_code, headers=headers)

        return None

    def _exception_handler_messages(self, msg, base_key=None):
        if isinstance(msg, list):
            for e in msg:
                self._exception_handler_messages(e)
        elif isinstance(msg, dict):
            for k, v in msg.items():
                self._exception_handler_messages(v, base_key=k)
        else:
            key = msg.code if hasattr(msg, 'code') else 'e'
            key = base_key + '__' + key if base_key else key
            self.set_error_message(key=key, value=str(msg))

    def _handle_exception_gando_handling_true(self, exc):
        """
        Handle any exception that occurs, by returning an appropriate response,
        or re-raising the error.
        """
        if isinstance(exc, (exceptions.NotAuthenticated,
                            exceptions.AuthenticationFailed)):
            auth_header = self.get_authenticate_header(self.request)

            if auth_header:
                exc.auth_header = auth_header
            else:
                exc.status_code = status.HTTP_403_FORBIDDEN

        context = self.get_exception_handler_context()
        response = self.exception_handler(exc, context)

        if response is None:
            response = Response()

        self.set_exception_message(
            key='unexpectedError',
            value=exc.args
        )
        self.set_error_message(
            key='unexpectedError',
            value=(
                "An unexpected error has occurred based on your request type.\n"
                "Please do not repeat this request without changing your request.\n"
                "Be sure to read the documents on how to use this service correctly.\n"
                "In any case, discuss the issue with software support.\n"
            )
        )
        self.set_warning_message(
            key='unexpectedError',
            value='Please discuss this matter with software support.',
        )
        if SETTINGS.EXCEPTION_HANDLER.COMMUNICATION_WITH_SOFTWARE_SUPPORT:
            self.set_info_message(
                key='unexpectedError',
                value=(
                    f"Please share this problem with our technical experts"
                    f" at the Email address "
                    f"'{SETTINGS.EXCEPTION_HANDLER.COMMUNICATION_WITH_SOFTWARE_SUPPORT}'."
                ),
            )
        self.set_status_code(421)
        response.exception = True
        return response

    def _handle_exception_gando_handling_false(self, exc):
        """
        Handle any exception that occurs, by returning an appropriate response,
        or re-raising the error.
        """
        if isinstance(exc, (exceptions.NotAuthenticated,
                            exceptions.AuthenticationFailed)):
            # WWW-Authenticate header for 401 responses, else coerce to 403
            auth_header = self.get_authenticate_header(self.request)

            if auth_header:
                exc.auth_header = auth_header
            else:
                exc.status_code = status.HTTP_403_FORBIDDEN

        context = self.get_exception_handler_context()
        response = self.exception_handler(exc, context)

        if response is None:
            self.raise_uncaught_exception(exc)

        response.exception = True
        return response

    def finalize_response(self, request, response, *args, **kwargs):
        mock_server_status = self.request.headers.get('Mock-Server-Status') or False
        mock_server_switcher = self.mock_server_switcher if hasattr(self, 'mock_server_switcher') else False
        if mock_server_switcher and mock_server_status and hasattr(self, 'mock_server'):
            return super().finalize_response(request, self.mock_server(), *args, **kwargs)

        if isinstance(response, Response):
            self.helper()

            tmp = response.template_name if hasattr(response, 'template_name') else None
            template_name = tmp

            tmp = response.headers if hasattr(response, 'headers') else None
            headers = self.get_headers(tmp)

            tmp = response.exception if hasattr(response, 'exception') else None
            exception = self.get_exception_status(tmp)

            tmp = response.content_type if hasattr(response, 'content_type') else None
            content_type = tmp

            tmp = response.status_code if hasattr(response, 'status_code') else None
            status_code = self.get_status_code(tmp)

            tmp = response.data if hasattr(response, 'data') else None
            data = self.response_context(tmp)

            response = Response(
                data=data,
                status=status_code,
                template_name=template_name,
                headers=headers,
                exception=exception,
                content_type=content_type,
            )

            if self.__cookies_for_delete:
                for i in self.__cookies_for_delete:
                    response.delete_cookie(i)

            if self.__cookies_for_set:
                for i in self.__cookies_for_set:
                    response.set_cookie(**i)

        return super().finalize_response(request, response, *args, **kwargs)

    def _response_validator(self, input_data):
        if isinstance(input_data, list):
            if not len(input_data):
                return []
            return [self._response_validator(i) for i in input_data]
        if isinstance(input_data, dict):
            if not len(input_data.keys()):
                return None
            ret = {}
            for k, v in input_data.items():
                ret[k] = self._response_validator(v)
            return ret
        return input_data

    def response_context(self, data=None):
        ret = None

        self.response_schema_version = self.request.headers.get('Response-Schema-Version') or '1.0.0'
        if self.response_schema_version == '2.0.0':
            ret = self._response_context_v_2_0_0_response(data)
        else:
            ret = self._response_context_v_1_0_0_response(data)
        return self._response_validator(ret)

    def _response_context_v_1_0_0_response(self, data=None):
        self.__data = self.__set_messages_from_data(data)

        status_code = self.get_status_code()
        content_type = self.get_content_type()
        data = self.validate_data()
        many = self.__many()

        monitor = self.__monitor

        has_warning = self.__has_warning()
        exception_status = self.get_exception_status()

        messages = self.__messages()

        success = self.__success()

        headers = self.get_headers()

        tmp = {
            'success': success,

            'status_code': status_code,

            'has_warning': has_warning,

            'monitor': self.monitor_play(monitor),

            'messenger': self.__messenger,

            'many': many,
            'data': data,
        }
        if self.__development_messages_display():
            tmp['development_messages'] = messages

        if self.__exception_status_display():
            tmp['exception_status'] = exception_status

        ret = tmp
        return ret

    def _response_context_v_2_0_0_response(self, data=None):
        self.__data = self.__set_messages_from_data(data)

        status_code = self.get_status_code()
        content_type = self.get_content_type()
        data = self.validate_data_v_2_0_0_response()
        many = self.__many_v_2_0_0_response()

        monitor = self.__monitor

        has_warning = self.__has_warning()
        exception_status = self.get_exception_status()

        messages = self.__messages()

        success = self.__success()

        headers = self.get_headers()

        tmp = {
            'success': success,
            'status_code': status_code,
            'messenger': self.__messenger,
        }
        tmp.update(data)

        if self.__development_messages_display():
            tmp['development_messages'] = messages

        if self.__exception_status_display():
            tmp['exception_status'] = exception_status

        ret = tmp
        return ret

    def __messenger_code_parser(self, x):
        if isinstance(x, int) or isinstance(x, str):
            return x

        with contextlib.suppress(Exception):
            return x.code

        with contextlib.suppress(Exception):
            return x.get('code')

        with contextlib.suppress(Exception):
            return '-1'

    def __messenger_message_parser(self, x):
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
            return x.get('detail')

        with contextlib.suppress(Exception):
            return x.get('details')[0]

        with contextlib.suppress(Exception):
            return x.get('details')

        with contextlib.suppress(Exception):
            return x.get('messages')[0]

        with contextlib.suppress(Exception):
            return x.get('messages')

        with contextlib.suppress(Exception):
            return x.get('message')

        with contextlib.suppress(Exception):
            return 'Unknown problem. Please report to support.'

    def __add_to_messenger(self, message, code, type_):
        self.__messenger.append(
            {
                'type': type_,
                'code': self.__messenger_code_parser(code),
                'message': self.__messenger_message_parser(message),
            }
        )

    def add_fail_message_to_messenger(self, message, code):
        self.__add_to_messenger(
            message=message,
            code=code,
            type_='FAIL',
        )

    def add_error_message_to_messenger(self, message, code):
        self.__add_to_messenger(
            message=message,
            code=code,
            type_='ERROR',
        )

    def add_warning_message_to_messenger(self, message, code):
        self.__add_to_messenger(
            message=message,
            code=code,
            type_='WARNING',
        )

    def add_success_message_to_messenger(self, message, code):
        self.__add_to_messenger(
            message=message,
            code=code,
            type_='SUCCESS',
        )

    def set_log_message(self, key, value):
        log = {key: value}
        self.__logs_message.append(log)

    def set_info_message(self, key, value):
        info = {key: value}
        self.__infos_message.append(info)

    def set_warning_message(self, key, value):
        warning = {key: value}
        self.__warnings_message.append(warning)

    def set_error_message(self, key, value):
        error = {key: value}
        self.__errors_message.append(error)

    def set_exception_message(self, key, value):
        exception = {key: value}
        self.__exceptions_message.append(exception)

    def set_headers(self, key, value):
        self.__headers[key] = value

    def get_headers(self, value: dict = None):
        if value:
            for k, v in value.items():
                self.set_headers(k, v)
        return self.__headers

    def __messages(self, ) -> dict:
        tmp = {
            'info': self.__infos_message,
            'warning': self.__warnings_message,
            'error': self.__errors_message,

        }
        if self.__debug_status:
            tmp['log'] = self.__logs_message
            tmp['exception'] = self.__exceptions_message

        ret = tmp
        return ret

    def __many(self):
        if isinstance(self.__data, list):
            return True
        if (
                isinstance(self.__data, dict) and
                'count' in self.__data and
                'next' in self.__data and
                'previous' in self.__data and
                'results' in self.__data
        ):
            return True
        return False

    def __many_v_2_0_0_response(self):
        if isinstance(self.__data, list):
            return True
        if (
                isinstance(self.__data, dict) and
                'count' in self.__data and
                'next' in self.__data and
                'previous' in self.__data and
                'result' in self.__data
        ):
            return True
        return False

    def __fail_message_messenger(self):
        for msg in self.__messenger:
            if msg.get('type', '') == 'FAIL' or msg.get('type', '') == 'ERROR':
                return True
        return False

    def __warning_message_messenger(self):
        for msg in self.__messenger:
            if msg.get('type', '') == 'WARNING':
                return True
        return False

    def __success(self):
        if 200 <= self.get_status_code() < 300:
            return True
        if (
                len(self.__errors_message) == 0 and
                len(self.__exceptions_message) == 0 and
                not self.__exception_status and
                not self.__fail_message_messenger()
        ):
            return True
        return False

    def __has_warning(self):
        if len(self.__warnings_message) != 0 and self.__warning_message_messenger():
            return True
        return False

    def set_status_code(self, value: int):
        self.__status_code = value

    def get_status_code(self, value: int = None):
        if value and 100 <= value < 600 and value != 200:
            self.set_status_code(value)

        return self.__status_code or 200

    def set_content_type(self, value: str):
        self.__content_type = value

    def get_content_type(self, value: str = None):
        if value:
            self.set_content_type(value)

        return self.__content_type

    def set_exception_status(self, value: bool):
        self.__exception_status = value

    def get_exception_status(self, value: bool = None):
        if value is not None:
            self.set_exception_status(value)

        return self.__exception_status

    def set_monitor(self, key, value):
        if key in self.__allowed_monitor_keys:
            self.__monitor[key] = value

    def __monitor_func_loader(self, f, *args, **kwargs):
        try:
            mod_name, func_name = f.rsplit('.', 1)
            mod = importlib.import_module(mod_name)
            func = getattr(mod, func_name)

            return func(request=self.request, *args, **kwargs)
        except PassException as exc:
            frame_info = getframeinfo(currentframe())
            self.set_log_message(
                key='pass',
                value=f"message:{exc.args[0]}, "
                      f"file_name: {frame_info.filename}, "
                      f"line_number: {frame_info.lineno}")
            return None

    def monitor_play(self, monitor=None, *args, **kwargs):
        monitor = monitor or {}
        for key, f in SETTINGS.MONITOR.items():
            monitor[key] = self.__monitor_func_loader(f, *args, **kwargs)

        return monitor

    @property
    def __allowed_monitor_keys(self):
        return SETTINGS.MONITOR_KEYS

    def validate_data(self):
        data = self.__data

        if data is None:
            self.__set_default_message()
            tmp = {'result': {}}

        elif isinstance(data, str) or issubclass(type(data), str):
            data = self.__set_dynamic_message(data)
            tmp = {'result': {'string': data} if data else {}}

        elif isinstance(data, list):
            tmp = {
                'count': len(data),
                'next': None,
                'previous': None,
                'results': data,
            }

        elif isinstance(data, dict):
            tmp = {'result': data}

        else:
            tmp = {'result': {}}

        ret = tmp
        return ret

    def validate_data_v_2_0_0_response(self):
        data = self.__data

        if data is None:
            self.__set_default_message()
            tmp = {'result': {}}

        elif isinstance(data, str) or issubclass(type(data), str):
            data = self.__set_dynamic_message(data)
            tmp = {'result': {'string': data} if data else {}}

        elif isinstance(data, list):
            if self.pagination:
                tmp = {
                    'count': len(data),
                    'next': None,
                    'previous': None,
                    'result': data,
                }
            else:
                tmp = {
                    'result': data,
                }

        elif isinstance(data, dict):
            if (
                    'count' in data and
                    'next' in data and
                    'previous' in data and
                    'results' in data
            ):
                if self.pagination:
                    tmp = {
                        'count': data.get('count'),
                        'next': data.get('next'),
                        'previous': data.get('previous'),
                        'result': data.get('results'),
                    }
                else:
                    tmp = {
                        'result': data.get('results'),
                    }
            elif (
                    'count' in data and
                    'page_size' in data and
                    'page_number' in data and
                    'result' in data
            ):
                n, p = self.__get_pagination_url(
                    page_size=data.get('page_size'),
                    page_number=data.get('page_number'),
                    count=data.get('count'))

                if self.pagination:

                    tmp = {
                        'count': data.get('count'),
                        'next': n,
                        'previous': p,
                        'result': data.get('result'),
                    }
                else:
                    tmp = {
                        'result': data.get('result'),
                    }
            else:
                tmp = {'result': data}

        else:
            tmp = {'result': {}}

        ret = tmp
        return ret

    @property
    def get_request_path(self):
        return f'{self.get_host()}{self.request._request.path}'

    def __get_pagination_url(self, page_size, page_number, count):
        first_page = int(bool(count))
        cps = count / page_size
        rcps = round(count / page_size)
        last_page = cps if rcps == cps else rcps + 1

        next_page_number = None if page_number >= last_page else page_number + 1
        previous_page_number = None if page_number <= first_page and first_page else page_number - 1

        next_page = f'{self.get_request_path}?page={next_page_number}' if next_page_number else None
        previous_page = f'{self.get_request_path}?page={previous_page_number}' if previous_page_number else None

        return next_page, previous_page

    @property
    def __debug_status(self):
        return SETTINGS.DEBUG

    @property
    def __development_state(self):
        return SETTINGS.DEVELOPMENT_STATE

    def __development_messages_display(self):
        if self.__development_state:
            ret = self.request.headers.get('Development-Messages-Display', 'True') == 'True'
        else:
            ret = False
        return ret

    def __exception_status_display(self):
        if self.__development_state:
            ret = self.request.headers.get('Exception-Status-Display', 'True') == 'True'
        else:
            ret = False
        return ret

    def response(self, output_data=None):
        data = output_data
        rsp = Response(
            data,
            status=self.get_status_code(),
            headers=self.get_headers(),
        )

        return rsp

    def get_host(self):
        return self.request._request._current_scheme_host

    def append_host_to_url(self, value):
        ret = f'{self.get_host()}{value}'
        return ret

    @staticmethod
    def get_media_url():
        from django.conf import settings

        ret = settings.MEDIA_URL
        return ret

    def convert_filename_to_url(self, file_name):
        if file_name is None:
            return None
        ret = f'{self.get_media_url()}{file_name}'
        return ret

    def convert_filename_to_url_localhost(self, file_name):
        if file_name is None:
            return None
        ret = f'{self.get_host()}{self.get_media_url()}{file_name}'
        return ret

    def helper(self):
        pass

    def __default_message(self):
        status_code = self.get_status_code()

        if 100 <= status_code < 200:
            msg = 'please wait...'

        elif 200 <= status_code < 300:
            if status_code == 201:
                msg = 'The desired object was created correctly.'
            else:
                msg = 'Your request has been successfully registered.'

        elif 300 <= status_code < 400:
            msg = 'The requirements for your request are not available.'

        elif 400 <= status_code < 500:
            if status_code == 400:
                msg = 'Bad Request...'

            elif status_code == 401:
                msg = 'Your authentication information is not available.'

            elif status_code == 403:
                msg = 'You do not have access to this section.'

            elif status_code == 404:
                msg = 'There is no information about your request.'

            elif status_code == 421:
                msg = (
                    "An unexpected error has occurred based on your request type.\n"
                    "Please do not repeat this request without changing your request.\n"
                    "Be sure to read the documents on how to use this service correctly.\n"
                    "In any case, discuss the issue with software support.\n"
                )

            else:
                msg = 'There was an error in how to send the request.'

        elif 500 <= status_code:
            msg = 'The server is unable to respond to your request.'

        else:
            msg = 'Undefined.'

        return msg

    def __default_messenger_message_adder(self):
        status_code = self.get_status_code()
        try:
            message = self.exc.detail if self.exc else None
        except:
            message = None
        try:
            code = self.exc.get_codes() if self.exc else None
        except:
            code = None
        if 100 <= status_code < 200:
            self.__add_to_messenger(
                message=message or DefaultResponse100FailMessage.message,
                code=code or DefaultResponse100FailMessage.code,
                type_=DefaultResponse100FailMessage.type,
            )

        elif 200 <= status_code < 300:
            if status_code == 201:
                self.__add_to_messenger(
                    message=message or DefaultResponse201SuccessMessage.message,
                    code=code or DefaultResponse201SuccessMessage.code,
                    type_=DefaultResponse201SuccessMessage.type,
                )
            else:
                self.__add_to_messenger(
                    message=message or DefaultResponse200SuccessMessage.message,
                    code=code or DefaultResponse200SuccessMessage.code,
                    type_=DefaultResponse200SuccessMessage.type,
                )

        elif 300 <= status_code < 400:
            self.__add_to_messenger(
                message=message or DefaultResponse300FailMessage.message,
                code=code or DefaultResponse300FailMessage.code,
                type_=DefaultResponse300FailMessage.type,
            )

        elif 400 <= status_code < 500:
            if status_code == 400:
                self.__add_to_messenger(
                    message=message or DefaultResponse400FailMessage.message,
                    code=code or DefaultResponse400FailMessage.code,
                    type_=DefaultResponse400FailMessage.type,
                )

            elif status_code == 401:
                self.__add_to_messenger(
                    message=message or DefaultResponse401FailMessage.message,
                    code=code or DefaultResponse401FailMessage.code,
                    type_=DefaultResponse401FailMessage.type,
                )

            elif status_code == 403:
                self.__add_to_messenger(
                    message=message or DefaultResponse403FailMessage.message,
                    code=code or DefaultResponse403FailMessage.code,
                    type_=DefaultResponse403FailMessage.type,
                )

            elif status_code == 404:
                self.__add_to_messenger(
                    message=message or DefaultResponse404FailMessage.message,
                    code=code or DefaultResponse404FailMessage.code,
                    type_=DefaultResponse404FailMessage.type,
                )

            elif status_code == 421:
                self.__add_to_messenger(
                    message=message or DefaultResponse421FailMessage.message,
                    code=code or DefaultResponse421FailMessage.code,
                    type_=DefaultResponse421FailMessage.type,
                )

            else:
                self.__add_to_messenger(
                    message=message or DefaultResponse400FailMessage.message,
                    code=code or DefaultResponse400FailMessage.code,
                    type_=DefaultResponse400FailMessage.type,
                )

        elif 500 <= status_code:
            self.__add_to_messenger(
                message=message or DefaultResponse500FailMessage.message,
                code=code or DefaultResponse500FailMessage.code,
                type_=DefaultResponse500FailMessage.type,
            )

        else:
            pass

    def __set_default_message(self):
        self.__default_messenger_message_adder()

        status_code = self.get_status_code()

        if 100 <= status_code < 200:
            self.set_warning_message('status_code_1xx', self.__default_message())

        elif 200 <= status_code < 300:
            self.set_info_message('status_code_2xx', self.__default_message())

        elif 300 <= status_code < 400:
            self.set_error_message('status_code_3xx', self.__default_message())

        elif 400 <= status_code < 500:
            self.set_error_message('status_code_4xx', self.__default_message())

        elif 500 <= status_code:
            self.set_error_message('status_code_5xx', self.__default_message())

        else:
            self.set_error_message('status_code_xxx', self.__default_message())

    def __set_messages_from_data(self, data):
        if isinstance(data, str) or issubclass(type(data), str):
            return self.__set_dynamic_message(data)

        if isinstance(data, list):
            tmp = []
            for i in data:
                rslt = self.__set_messages_from_data(i)
                # if rslt:
                tmp.append(rslt)

            ret = tmp
            return ret

        if isinstance(data, dict):
            tmp = {}
            for k, v in data.items():
                rslt = self.__set_messages_from_data(v)
                # if rslt is not None:
                tmp[k] = v

            ret = tmp
            return ret

        return data

    def __set_dynamic_message(self, value):
        if isinstance(value, InfoStringMessage):
            self.set_info_message(key=value.code, value=value)
            return None
        if isinstance(value, ErrorStringMessage) or isinstance(value, ErrorDetail):
            self.set_error_message(key=value.code, value=value)
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

        return value

    class Cookie(BaseModel):
        key: str
        value: Any = ""
        max_age: Any = None
        expires: Any = None
        path: Any = "/"
        domain: Any = None
        secure: Any = False
        httponly: Any = False
        samesite: Any = None

    def cookie_getter(self, key: str):
        ret = self.request.COOKIES.get(key)
        return ret

    def cookie_setter(self, key: str, **kwargs):
        ret = self.__cookies_for_set.append(self.Cookie(key=key, **kwargs).model_dump())
        return ret

    def cookie_deleter(self, key: str):
        ret = self.__cookies_for_delete.append(key)
        return ret

    @property
    def get_query_params_fields(self):
        fields = self.request.query_params.get('fields')
        fields = fields if fields is None else fields.split(',')
        return fields


class CreateAPIView(BaseAPI, DRFGCreateAPIView):
    def create(self, request, *args, **kwargs):
        if hasattr(self, 'check_validate_user') and self.check_validate_user:
            user_lookup_field = 'id'
            if hasattr(self, 'user_lookup_field'):
                user_lookup_field = self.user_lookup_field
            if not _valid_user(request=request, user_id=kwargs.get(user_lookup_field)):
                return Response(status=403)

        data = request.data.copy()
        user_field_name = 'user'
        if hasattr(self, 'user_field_name'):
            user_field_name = self.user_field_name
        data[user_field_name] = request.user.id

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class ListAPIView(BaseAPI, DRFGListAPIView):
    def get_queryset(self):
        qs = super().get_queryset()
        if hasattr(self, 'for_user') and self.for_user:
            qs = qs.filter(user_id=self.request.user.id)
        return qs

    def get(self, request, *args, **kwargs):
        if hasattr(self, 'check_validate_user') and self.check_validate_user:
            user_lookup_field = 'id'
            if hasattr(self, 'user_lookup_field'):
                user_lookup_field = self.user_lookup_field
            if not _valid_user(request=request, user_id=kwargs.get(user_lookup_field)):
                return Response(status=403)
        return super().get(request, *args, **kwargs)


class RetrieveAPIView(BaseAPI, DRFGRetrieveAPIView):
    def get_queryset(self):
        qs = super().get_queryset()
        if hasattr(self, 'for_user') and self.for_user:
            qs = qs.filter(user_id=self.request.user.id)
        return qs

    def get(self, request, *args, **kwargs):
        if hasattr(self, 'check_validate_user') and self.check_validate_user:
            user_lookup_field = 'id'
            if hasattr(self, 'user_lookup_field'):
                user_lookup_field = self.user_lookup_field
            if not _valid_user(request=request, user_id=kwargs.get(user_lookup_field)):
                return Response(status=403)
        return super().get(request, *args, **kwargs)


class UpdateAPIView(BaseAPI, DRFGUpdateAPIView):
    def get_queryset(self):
        qs = super().get_queryset()
        if hasattr(self, 'for_user') and self.for_user:
            qs = qs.filter(user_id=self.request.user.id)
        return qs

    def update(self, request, *args, **kwargs):
        if hasattr(self, 'check_validate_user') and self.check_validate_user:
            user_lookup_field = 'id'
            if hasattr(self, 'user_lookup_field'):
                user_lookup_field = self.user_lookup_field
            if not _valid_user(request=request, user_id=kwargs.get(user_lookup_field)):
                return Response(status=403)

        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        data = request.data.copy()
        user_field_name = 'user'
        if hasattr(self, 'user_field_name'):
            user_field_name = self.user_field_name
        data[user_field_name] = request.user.id

        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)


class DestroyAPIView(BaseAPI, DRFGDestroyAPIView):
    def get_queryset(self):
        qs = super().get_queryset()
        if hasattr(self, 'for_user') and self.for_user:
            qs = qs.filter(user_id=self.request.user.id)
        return qs

    def delete(self, request, *args, **kwargs):
        if hasattr(self, 'check_validate_user') and self.check_validate_user:
            user_lookup_field = 'id'
            if hasattr(self, 'user_lookup_field'):
                user_lookup_field = self.user_lookup_field
            if not _valid_user(request=request, user_id=kwargs.get(user_lookup_field)):
                return Response(status=403)
        return self.destroy(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance=instance, soft_delete=kwargs.get('soft_delete', False))
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance, soft_delete=False):
        if instance is None:
            return

        if soft_delete:
            instance.available = 0
            instance.save()
        else:
            instance.delete()
