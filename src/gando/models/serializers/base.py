"""Serializers that turn Django ``QueryDict``-style flat data into nested dicts.

The main entry point is :class:`QueryDictSerializer`. It understands two
different flattening conventions and expands both into a nested structure:

* ``__`` (double underscore) is treated as an explicit nesting separator, so
  ``{"a__b": 1, "a__c": 2}`` becomes ``{"a": {"b": 1, "c": 2}}``.
* For every prefix registered in ``image_fields_name`` a *single* underscore is
  treated as an image sub-field separator, so with
  ``image_fields_name=["avatar"]`` the keys ``avatar_src`` and ``avatar_width``
  become ``{"avatar": {"src": ..., "width": ...}}``.

Additionally, any leaf key literally named ``src`` is prefixed with
``settings.MEDIA_URL`` so that clients receive absolute media paths.
"""


class QueryDictSerializer:
    """Expand a flat ``QueryDict``-like mapping into a nested dictionary.

    Parameters
    ----------
    image_fields_name : list[str] | None
        The list of image field prefixes whose ``<prefix>_<subfield>`` keys
        should be grouped under a single nested ``<prefix>`` dict. Defaults to
        an empty list (no image grouping).

    Examples
    --------
    >>> QueryDictSerializer()({"a__b": 1, "a__c": 2})
    {'a': {'b': 1, 'c': 2}}
    >>> QueryDictSerializer(image_fields_name=["avatar"])(
    ...     {"avatar_width": 10, "avatar_height": 20})
    {'avatar': {'width': 10, 'height': 20}}
    """

    def __init__(self, image_fields_name=None):
        self.image_fields_name = [] if not image_fields_name else image_fields_name

    def __call__(self, input_data):
        """Serialize ``input_data`` (dict, list or scalar) into nested form."""
        return self.__parser(input_data)

    def __parser(self, input_data):
        """Recursively expand flat keys into nested dicts.

        Lists are mapped element-wise, dicts are expanded key by key, and any
        other (scalar) value is returned unchanged.
        """
        if isinstance(input_data, list):
            return [self.__parser(i) for i in input_data]

        if isinstance(input_data, dict):
            tmp = dict()
            for k, v in input_data.items():
                k__split = k.split('__', 1)
                if len(k__split) == 1:
                    k_split = self.__image_field_name_parser(k)
                    if len(k_split) == 1:
                        _ = self.__parser(v)
                        v_ = _ if k not in tmp else self.__updater(tmp[k], _)
                        tmp[k] = v_ if k != 'src' else f'{self.__media_url}{v_}'
                    else:
                        _ = self.__parser({k_split[1]: v})
                        v_ = _ if k_split[0] not in tmp else self.__updater(
                            tmp[k_split[0]], _)
                        tmp[k_split[0]] = (
                            v_ if k != 'src' else f'{self.__media_url}{v_}')
                else:
                    _ = self.__parser({k__split[1]: v})
                    v_ = _ if k__split[0] not in tmp else self.__updater(
                        tmp[k__split[0]], _)
                    tmp[k__split[0]] = (
                        v_ if k != 'src' else f'{self.__media_url}{v_}')
            return tmp
        return input_data

    def __updater(self, a, b):
        """Deep-merge two already-parsed values ``a`` and ``b``.

        The merge is used when the same (top-level or nested) key is produced
        more than once while flattening. The rules are:

        * Two dicts are merged recursively; keys present in ``b`` are merged
          into (and, for scalar collisions, override/append onto) ``a`` without
          mutating either operand.
        * If ``a`` is a list, ``b`` is appended to a copy of it.
        * Otherwise the two values are collected into a new ``[a, b]`` list.

        Notes
        -----
        This replaces an earlier implementation whose nested ``for``/``for``
        loop produced order-dependent, lossy results for dicts with more than
        one key. See ``tests/test_query_dict_serializer.py`` for regression
        coverage.
        """
        if isinstance(a, dict) and isinstance(b, dict):
            out = dict(a)
            for key, value in b.items():
                if key in out:
                    out[key] = self.__updater(out[key], value)
                else:
                    out[key] = value
            return out

        if isinstance(a, list):
            return a + [b]

        if isinstance(b, list):
            return [a, b]

        return [a, b]

    def __image_field_name_parser(self, field_name):
        """Split ``field_name`` into ``[prefix, subfield]`` for image fields.

        For every registered image prefix ``img``, a field named
        ``f"{img}_{subfield}"`` is split into ``[img, subfield]``. If no prefix
        matches, ``[field_name]`` is returned unchanged.

        The match requires the field name to start with ``f"{img}_"`` (prefix
        **plus** the separating underscore); a name that merely shares leading
        characters with a prefix (e.g. ``imagery`` vs. prefix ``image``) is not
        treated as an image sub-field.

        Notes
        -----
        The previous implementation used a single ``equal`` flag initialised
        once *outside* the loop, so once it was set to ``False`` by a
        non-matching prefix it stayed ``False`` for every later prefix, causing
        valid matches to be missed. It also compared only the raw prefix
        characters (ignoring the trailing underscore), which raised
        ``IndexError`` for names like ``image`` when a shorter prefix such as
        ``ima`` was registered. Both issues are fixed here with
        :meth:`str.startswith`.
        """
        for img in self.image_fields_name:
            prefix = f'{img}_'
            if field_name.startswith(prefix):
                return [img, field_name[len(prefix):]]
        return [field_name]

    @property
    def __media_url(self):
        """Return ``settings.MEDIA_URL`` or ``''`` when it is not configured.

        Uses :func:`getattr` with a default instead of a bare ``except`` so
        that unrelated import/configuration errors are no longer silently
        swallowed.
        """
        from django.conf import settings

        return getattr(settings, 'MEDIA_URL', '') or ''
