from django.utils.deprecation import MiddlewareMixin

from gando.http.responses import JsonResponse as Response
from rest_framework.response import Response as DRFResponse

from .request_monitor import Monitor
from .request_response_message import ResponseMessages


class JsonResponse(MiddlewareMixin):

    def process_request(self, request):
        request.monitor = Monitor()
        request.response_messages = ResponseMessages()

    def process_response(self, request, response):
        rsp = response
        if isinstance(response, Response):
            msg = request.response_messages.export()
            d_msg = msg.model_dump()
            rsp = DRFResponse(status=self.__get_status_code(response),
                **d_msg, **response.__dict__)
        return rsp

    def __get_status_code(self, response):
        if hasattr(response, 'status'):
            status_code = getattr(response, 'status')

        elif hasattr(response, 'status_code'):
            status_code = getattr(response, 'status_code')

        else:
            status_code = 200
        return status_code
