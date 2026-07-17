"""Regression test for :class:`gando.services.getter.BaseGetterService`.

``BaseGetterService.__init__`` unconditionally builds ``self.filters`` from
``filter_schema(**kwargs).model_dump()...`` -- a previous version chained a
nonexistent ``dict.extract()`` onto that, so *instantiating* any concrete
subclass raised ``AttributeError`` regardless of whether ``get_from_db()``
was ever called. This is gando's single most severe latent bug found during
this pass: the "getter service" building block is a documented README
feature with (before this pass) zero test coverage.
"""

from pydantic import BaseModel

from gando.services import BaseGetterService


class _FilterSchema(BaseModel):
    """Every field optional -- mirrors how a real query-param filter schema
    is used (only the fields the caller actually supplied are set)."""

    name: str | None = None
    category: str | None = None


class _OutputSchema(BaseModel):
    id: int
    name: str


class _WidgetGetterService(BaseGetterService):
    """A minimal concrete ``BaseGetterService`` -- ``model`` is never
    exercised by this test (no queryset method is called), only
    construction and the ``filters``/``values`` bookkeeping done in
    ``__init__``."""

    model = None
    output_schema = _OutputSchema
    filter_schema = _FilterSchema
    acceptable_values = ['id', 'name']


def test_instantiation_does_not_raise():
    """Regression: this used to crash unconditionally in ``__init__``."""
    _WidgetGetterService(name='widget-1')


def test_filters_excludes_fields_the_caller_did_not_supply():
    """Only the explicitly-supplied filter field is kept; the untouched
    optional field (defaulting to ``None`` in the pydantic schema) is
    dropped rather than turning into an accidental ``category=None``
    queryset filter."""
    service = _WidgetGetterService(name='widget-1')
    assert service.filters == {'name': 'widget-1'}


def test_filters_is_empty_when_nothing_supplied():
    service = _WidgetGetterService()
    assert service.filters == {}


def test_filters_keeps_every_field_the_caller_supplied():
    service = _WidgetGetterService(name='widget-1', category='tools')
    assert service.filters == {'name': 'widget-1', 'category': 'tools'}


def test_values_defaults_to_every_acceptable_value():
    service = _WidgetGetterService()
    assert set(service.values) == {'id', 'name'}


def test_values_is_restricted_to_the_ones_passed_in():
    service = _WidgetGetterService('id')
    assert service.values == ['id']
