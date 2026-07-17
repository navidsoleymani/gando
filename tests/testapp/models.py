"""A minimal concrete model built on :class:`gando.models.AbstractBaseModel`.

Used by ``tests/test_abstract_base_model.py`` to exercise, against a real
(in-memory SQLite) table, the soft-delete manager filtering and audit fields
that every model built on gando's abstract base inherits.
"""

from django.db import models

from gando.models import AbstractBaseModel


class Widget(AbstractBaseModel):
    """A trivial model with one extra field, for manager/soft-delete tests."""

    name = models.CharField(max_length=100)

    # An unfiltered manager, added only so tests can assert on rows that the
    # default (soft-delete-filtering) ``objects`` manager intentionally hides.
    # Production code built on ``AbstractBaseModel`` is not required to add
    # this -- it exists purely as a test assertion aid.
    all_objects = models.Manager()

    class Meta:
        app_label = 'testapp'
