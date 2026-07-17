"""Tests for :func:`gando.utils.converters.images.small_blur_base64`.

The key behaviour under test is that the function accepts bytes, file-like
objects **and** paths -- this is what lets the blurred-preview computation work
with remote storage backends (S3/GCS) that do not expose a local file path.
"""

import io

import pytest
from PIL import Image

from gando.utils.converters.images import small_blur_base64


def _png_bytes(color=(10, 120, 200)):
    """Return the bytes of a small in-memory PNG image for testing."""
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_accepts_raw_bytes():
    """Raw image bytes are decoded and produce a data URI."""
    result = small_blur_base64(_png_bytes())
    assert isinstance(result, str)
    assert result.startswith("data:image/png;base64,")


def test_accepts_file_like_object():
    """An open binary file-like object (e.g. a storage-opened file) works."""
    file_like = io.BytesIO(_png_bytes())
    result = small_blur_base64(file_like)
    assert result is not None
    assert result.startswith("data:image/png;base64,")


def test_accepts_filesystem_path(tmp_path):
    """A plain filesystem path still works (backwards compatibility)."""
    path = tmp_path / "img.png"
    path.write_bytes(_png_bytes())
    result = small_blur_base64(str(path))
    assert result is not None
    assert result.startswith("data:image/png;base64,")


@pytest.mark.parametrize("bad", [b"not-an-image", io.BytesIO(b"garbage")])
def test_non_image_returns_none(bad):
    """Undecodable input degrades gracefully to ``None`` (no exception)."""
    assert small_blur_base64(bad) is None
