"""Tests for :func:`gando.utils.http.response.base.inf_response`.

Focus: the ``page_size_inf`` query-param parsing, whose bare ``except`` was
narrowed to ``(TypeError, ValueError)`` so that a non-numeric value falls back
to the paginated path instead of silently swallowing unrelated errors.
"""

from types import SimpleNamespace

from gando.utils.http.response.base import inf_response


class _Serializer:
    """A stand-in DRF serializer exposing a fixed ``data`` payload."""

    def __init__(self, data):
        self.data = data


class _FakeView:
    """Minimal fake of a DRF generic view for exercising ``inf_response``."""

    def __init__(self, page_size_inf):
        self._data = [{"id": 1}, {"id": 2}]
        self.request = SimpleNamespace(
            query_params={"page_size_inf": page_size_inf})

    # -- generic view surface used by inf_response --------------------------
    def get_queryset(self):
        return self._data

    def filter_queryset(self, queryset):
        return queryset

    def paginate_queryset(self, queryset):
        return None  # no pagination configured -> falls through

    def get_serializer(self, queryset, many=False):
        return _Serializer(queryset)


def test_non_numeric_page_size_inf_falls_back_without_error():
    """A non-numeric ``page_size_inf`` must not raise; returns normal data."""
    response = inf_response(_FakeView("not-a-number"))
    assert response.data == [{"id": 1}, {"id": 2}]


def test_page_size_inf_one_returns_infinite_envelope():
    """``page_size_inf == 1`` returns the special INF-count envelope."""
    response = inf_response(_FakeView("1"))
    assert response.data["count"] == "INF"
    assert response.data["results"] == [{"id": 1}, {"id": 2}]
