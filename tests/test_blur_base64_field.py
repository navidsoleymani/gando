"""Tests for :class:`gando.models.fields.base.BlurBase64Field`.

The regression under test: ``pre_save`` must read the image through the
``FieldFile``/storage API (``.open('rb')`` + read) rather than through a local
filesystem path (``_src.file.name``). The fake below deliberately exposes *no*
``.file`` attribute and a storage-relative ``name`` that is not a real local
path, so a regression to the old behaviour would fail these tests.
"""

import io

from PIL import Image

from gando.models.fields.base import BlurBase64Field


def _png_bytes():
    """Return the bytes of a small in-memory PNG image."""
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 30, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeFieldFile:
    """Minimal stand-in for a Django ``FieldFile`` backed by a storage.

    It supports the read/seek/tell protocol PIL needs and an ``open()`` that
    (like remote storages) serves content without any local filesystem path.
    """

    def __init__(self, content):
        self._content = content
        self._buf = io.BytesIO(content) if content is not None else None
        # A storage-relative key, NOT a valid local filesystem path.
        self.name = "remote/bucket/key/photo.png"
        self.opened = False

    def __bool__(self):
        return True

    def open(self, mode="rb"):
        if self._content is None:
            raise FileNotFoundError(self.name)
        self.opened = True
        self._buf.seek(0)
        return self

    def read(self, *args):
        return self._buf.read(*args)

    def seek(self, *args):
        return self._buf.seek(*args)

    def tell(self):
        return self._buf.tell()


class FakeInstance:
    """A bare object carrying the companion ``*_src`` and computed attrs."""


def _make_field():
    """Build a ``BlurBase64Field`` wired as ImageField would wire it."""
    field = BlurBase64Field()
    field.PARENT_FIELD_NAME = "photo"
    field.attname = "photo_blurbase64"
    return field


def test_pre_save_computes_preview_via_storage_api():
    """A readable remote-style file yields a data URI without a local path."""
    field = _make_field()
    src = FakeFieldFile(_png_bytes())
    instance = FakeInstance()
    instance.photo_src = src

    value = field.pre_save(instance, add=True)

    assert src.opened is True
    assert value is not None
    assert value.startswith("data:image/png;base64,")
    assert instance.photo_blurbase64 == value


def test_pre_save_rewinds_file_for_subsequent_save():
    """After computing the preview the file pointer is reset to the start."""
    field = _make_field()
    src = FakeFieldFile(_png_bytes())
    instance = FakeInstance()
    instance.photo_src = src

    field.pre_save(instance, add=True)

    assert src.tell() == 0


def test_pre_save_missing_file_degrades_to_none():
    """An unreadable/missing file yields ``None`` instead of raising."""
    field = _make_field()
    src = FakeFieldFile(None)  # open() raises FileNotFoundError
    instance = FakeInstance()
    instance.photo_src = src

    value = field.pre_save(instance, add=True)

    assert value is None
    assert instance.photo_blurbase64 is None


def test_pre_save_without_src_attr_is_noop():
    """When there is no companion ``*_src`` attribute, nothing is computed."""
    field = _make_field()
    instance = FakeInstance()
    instance.photo_blurbase64 = "preexisting"

    value = field.pre_save(instance, add=True)

    assert value == "preexisting"
