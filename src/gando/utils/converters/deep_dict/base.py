def any2dict(obj, **kwargs):
    if obj is None:
        return obj

    if (kwargs.get('max_depth') is not None and
        kwargs.get('depth', 0) > kwargs.get('max_depth')):
        return str(obj)

    kwargs['depth'] = kwargs.get('depth', 0) + 1

    if isinstance(obj, (str, int, float, bool)):
        return obj

    if isinstance(obj, dict):
        tmp = {}
        for k, v in obj.items():
            if k not in kwargs.get('exclude', []):
                tmp[k] = any2dict(v, **kwargs)
        return tmp

    if isinstance(obj, list):
        return [any2dict(v, **kwargs) for v in obj]

    if isinstance(obj, tuple):
        return tuple(any2dict(v, **kwargs) for v in obj)

    if isinstance(obj, set):
        return set(any2dict(v, **kwargs) for v in obj)

    if hasattr(obj, '__dict__'):
        tmp = {}
        for k, v in obj.__dict__.items():
            if k not in kwargs.get('exclude', []):
                tmp[k] = any2dict(v, **kwargs)
        return tmp

    return str(obj)
