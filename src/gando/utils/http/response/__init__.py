from rest_framework.response import Response


def response_updater(response: Response, **kwargs):
    status_code = (kwargs.pop('status_code') if 'status_code' in kwargs else None) or response.status_code
    data = response.data
    inputs = kwargs

    if isinstance(data, dict):
        data.update(inputs)
    elif isinstance(data, list):
        for i in data:
            i.update(inputs)
    elif isinstance(data, str):
        data = {'str': data}
        data.update(inputs)
    else:
        data = inputs

    res = Response(data=data, status=status_code)
    return res


def inf_response(instance):
    queryset = instance.filter_queryset(instance.get_queryset())
    try:
        page_size_inf = int(instance.request.query_params.get("page_size_inf", 0))
    except:
        page_size_inf = 0

    if page_size_inf == 1:
        serializer = instance.get_serializer(queryset, many=True)
        return Response(
            {"count": "INF", "next": None, "previous": None, "results": serializer.data})

    page = instance.paginate_queryset(queryset)
    if page is not None:
        serializer = instance.get_serializer(page, many=True)
        return instance.get_paginated_response(serializer.data)

    serializer = instance.get_serializer(queryset, many=True)
    return Response(serializer.data)
