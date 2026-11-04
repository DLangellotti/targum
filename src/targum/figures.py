"""An article's pictures, kept beside its reader (design.md §12, "A text keeps the shape
its edition gives it", 2026-11-04).

The article said where each picture was (`models.Picture`, on its caption's block). Here
each is fetched once, when the text is built, and kept as a webp at a long edge of
`post.LONG_EDGE` under `<folder>/figures/`, named by its caption's block. The page carries
it inside itself, as it carries a post's pictures and a cover: a reader never fetches
anything from the publisher. A picture that will not come, or will not open, is left out,
and its caption is still a line of the text.
"""

from __future__ import annotations

import io
import logging
import tempfile
from pathlib import Path

from .models import Document

log = logging.getLogger(__name__)

#: Where the pictures are kept, inside the targum's folder.
FOLDER = "figures"
#: The most one picture may weigh before it is kept: a photograph, never a film.
MOST_BYTES = 12 * 1024 * 1024


def kept_path(block_id: str) -> str:
    """Where a caption's picture is kept, relative to the targum's folder."""
    return f"{FOLDER}/{block_id}.webp"


def keep(document: Document, folder: Path) -> int:
    """Fetch and keep each picture the document's captions name. Returns how many."""
    from PIL import Image, ImageOps

    from .ingest.post import LONG_EDGE
    from .ingest.url import download

    kept = 0
    for block in document.blocks:
        picture = block.picture
        if picture is None:
            continue
        target = folder / kept_path(block.id)
        if target.is_file():
            kept += 1
            continue
        try:
            with tempfile.TemporaryDirectory() as scratch:
                fetched = Path(scratch) / "picture"
                download(picture.src, fetched, MOST_BYTES)
                image = ImageOps.exif_transpose(Image.open(fetched))
                image.thumbnail((LONG_EDGE, LONG_EDGE), Image.Resampling.LANCZOS)
                out = io.BytesIO()
                image.convert("RGB").save(out, format="WEBP", quality=82, method=6)
        except Exception as why:  # noqa: BLE001 - one picture is not the article
            log.warning("left an article's picture out: %s (%s)", picture.src, why)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(out.getvalue())
        kept += 1
    return kept
