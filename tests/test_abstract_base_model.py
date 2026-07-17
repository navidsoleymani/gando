"""Database-backed tests for :class:`gando.models.AbstractBaseModel`.

This exercises, against a real (in-memory SQLite) table via ``tests.testapp.
models.Widget``, the behavior every model built on gando's abstract base
inherits automatically: soft-delete manager filtering, the ``available``
flag, and the auto-generated UUID primary key. None of this had any test
coverage before this pass, despite being gando's single most-depended-on
piece of behavior (every model in a consuming project derives from it).
"""

import uuid

import pytest

from tests.testapp.models import Widget

pytestmark = pytest.mark.django_db


def test_id_is_an_auto_generated_uuid():
    """The primary key is a UUID (``uuid.uuid7``), assigned without input."""
    widget = Widget.objects.create(name='a')
    assert isinstance(widget.id, uuid.UUID)


def test_available_defaults_to_one():
    """New rows default to ``available=1`` (visible to the default manager)."""
    widget = Widget.objects.create(name='a')
    assert widget.available == 1


def test_default_manager_excludes_soft_deleted_rows():
    """``.delete()`` soft-deletes; the row disappears from ``objects``."""
    kept = Widget.objects.create(name='kept')
    removed = Widget.objects.create(name='removed')

    removed.delete()

    assert list(Widget.objects.values_list('name', flat=True)) == ['kept']
    assert Widget.objects.filter(pk=kept.pk).exists()
    assert not Widget.objects.filter(pk=removed.pk).exists()


def test_soft_deleted_row_still_exists_physically():
    """Soft delete marks the row, it does not remove it from the table."""
    widget = Widget.objects.create(name='a')
    pk = widget.pk

    widget.delete()

    raw = Widget.all_objects.get(pk=pk)
    assert raw.is_deleted is True
    assert raw.deleted_dt is not None


def test_force_delete_hard_deletes():
    """``force_delete()`` bypasses the soft-delete override entirely."""
    widget = Widget.objects.create(name='a')
    pk = widget.pk

    widget.force_delete()

    assert not Widget.all_objects.filter(pk=pk).exists()


def test_default_manager_excludes_unavailable_rows():
    """Rows with ``available=0`` are hidden even when not soft-deleted."""
    Widget.objects.create(name='a', available=0)
    assert Widget.objects.count() == 0
    assert Widget.all_objects.count() == 1


def test_manager_level_bulk_delete_is_soft():
    """``Widget.objects.delete()`` bulk-soft-deletes every visible row.

    ``BaseSoftDeleteManager.delete`` is a manager-level override (not the
    usual queryset-level ``.all().delete()``) that turns a bulk delete into
    a bulk ``UPDATE ... SET is_deleted=True`` instead of a ``DELETE``.
    """
    a = Widget.objects.create(name='a')
    b = Widget.objects.create(name='b')

    Widget.objects.delete()

    assert Widget.objects.count() == 0
    assert Widget.all_objects.filter(pk__in=[a.pk, b.pk], is_deleted=True).count() == 2
