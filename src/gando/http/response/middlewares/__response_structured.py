from django.utils.deprecation import MiddlewareMixin

from gando.http.response import JsonResponse as Response

from .__request_monitor import Monitor
from .__request_response_message import ResponseMessages


class JsonResponse(MiddlewareMixin):

    def process_request(self, request):
        request.monitor = Monitor()
        request.response_messages = ResponseMessages()

    def process_response(self, request, response):
        msg = request.response_messages.export()
        dmsg = msg.model_dump()
        rsp = Response(status=self.__get_status_code(response), **dmsg, **response.__dict__)
        return rsp

    def __get_status_code(self, response):
        try:
            status_code = getattr(response, 'status')
        except:
            status_code = getattr(response, 'status_code')
        return status_code
