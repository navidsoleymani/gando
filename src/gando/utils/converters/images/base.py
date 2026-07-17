"""Utilities for computing a tiny blurred base64 preview of an image.

The blurred preview (a very small, blurred PNG encoded as a ``data:`` URI) is
typically stored alongside an image so that clients can render a lightweight
placeholder while the full-resolution image loads.
"""

import base64
import io

from PIL import Image, ImageFilter


def small_blur_base64(image_source):
    """Return a tiny blurred base64 ``data:`` URI for ``image_source``.

    Parameters
    ----------
    image_source : str | os.PathLike | bytes | bytearray | typing.IO
        The image to process. This may be any of:

        * a filesystem path (``str``/``os.PathLike``),
        * raw image ``bytes``/``bytearray``,
        * an already-open, readable binary file-like object (including a
          Django ``File``/``FieldFile`` opened via its storage backend).

        Accepting file-like objects and bytes is what allows the caller to work
        with **remote** storages (S3/GCS/etc.), where a plain filesystem path
        is not available.

    Returns
    -------
    str | None
        A ``data:<mimetype>;base64,<payload>`` string on success, or ``None``
        when the source cannot be decoded as an image (e.g. it is not an image,
        is corrupt, or is unreadable). Returning ``None`` keeps the blurred
        preview an optional, best-effort field rather than a hard failure.
    """
    try:
        source = (
            io.BytesIO(image_source)
            if isinstance(image_source, (bytes, bytearray))
            else image_source
        )
        im = Image.open(source)
        (width, height) = (im.width // 8, im.height // 8)
        mimetype = im.get_format_mimetype()
        im_resized = im.resize((width, height))
        blurred_image = im_resized.filter(ImageFilter.BLUR)
        buffered = io.BytesIO()
        blurred_image.save(buffered, format="PNG")
        encoded_image = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return f"data:{mimetype};base64,{encoded_image}"
    except Exception:
        # The blurred preview is optional: any decoding/IO problem degrades
        # gracefully to "no preview" instead of breaking the caller's save.
        return None
