from pydantic import BaseModel as Base
from functools import lru_cache
import contextlib

from django.conf import settings


class ExceptionHandlerObject(Base):
    HANDLING: bool = False
    COMMUNICATION_WITH_SOFTWARE_SUPPORT: str = None


class UserAgentDeviceHandlerObject(Base):
    HANDLING: bool = False
    COOKIE_NAME: str = 'uad'


class DefaultValues(Base):
    SMALL_TEXT: str = 'Undefined'
    SHORT_TEXT: str = 'Undefined'
    LONG_TEXT: str = 'Undefined'


class Gando(Base):
    MONITOR_KEYS: list = list()
    DEBUG: bool = True
    CACHING: bool = False
    MONITOR: dict = dict()
    EXCEPTION_HANDLER: ExceptionHandlerObject = ExceptionHandlerObject()
    PASTE_TO_REQUEST: dict = dict()
    USER_AGENT_DEVICE_HANDLER: UserAgentDeviceHandlerObject = UserAgentDeviceHandlerObject()
    DEVELOPMENT_STATE: bool = True
    DEFAULTS: DefaultValues = DefaultValues()


@lru_cache()
def __get_settings():
    input_conf = {}

    with contextlib.suppress(Exception):
        input_conf = settings.GANDO

    with contextlib.suppress(Exception):
        input_conf['DEBUG'] = settings.DEBUG

    input_conf['EXCEPTION_HANDLER'] = (
        ExceptionHandlerObject(
            **input_conf['EXCEPTION_HANDLER'])
        if 'EXCEPTION_HANDLER' in input_conf
        else ExceptionHandlerObject()
    )
    input_conf['USER_AGENT_DEVICE_HANDLER'] = (
        UserAgentDeviceHandlerObject(
            **input_conf['USER_AGENT_DEVICE_HANDLER'])
        if 'USER_AGENT_DEVICE_HANDLER' in input_conf
        else UserAgentDeviceHandlerObject()
    )
    input_conf['DEFAULTS'] = (
        DefaultValues(
            **input_conf['DEFAULTS'])
        if 'DEFAULTS' in input_conf
        else DefaultValues()
    )

    return Gando(**input_conf)


SETTINGS = __get_settings()
