"""Reading the words off a picture: a screenshot, a phone photo of a page.

The model that glosses is the model that reads, one request a picture, and what comes
back is the text as printed — line for line, nikkud where the page had it, English
where the page had English, nothing translated and nothing added. A line the model
could not make out is marked rather than guessed, and the mark is counted so the card
can say how many there were before anybody presses anything.

This is the one place targum spends before a card is drawn: the file choice is the
consent for the reading (decided 2026-09-07, targum-internal#217), it is capped at
`MAX_PAGES` a text, and every read is cached by the picture's bytes so the same
screenshot is never paid for twice — by the price quote, by the build after it, or by
a second drop of the same file. Pictures over the model's own ceiling are scaled down
first, because the cost is per pixel and nothing above 1568 px on the long side reads
any better.

Nothing here is a dependency of the plain install. Pillow, `pillow-heif` and `pypdf`
are the `bring` extra, and a box without them says so in one sentence.
"""

from __future__ import annotations

import base64
import hashlib
import io
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cache import Cache
from .errors import TargumError
from .usage import Usage

#: The pictures a reader can bring. HEIC is what an iPhone takes; the rest is what a
#: screen saves. Lower-case, with the dot, like every other suffix table.
PICTURE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif"})

#: One text, at most. Thirty pages is a handout or a chapter; a book is #197's.
MAX_PAGES = 30

#: What one page is reserved at before it is read, in dollars. The probe read a
#: screenshot for $0.0042 on Sonnet 5 (2026-09-07); a phone photo is more pixels and
#: a longer answer, and a reservation errs high because it is settled to the receipt.
PAGE_RESERVE = 0.01

#: The model's own ceiling on a side. Above it the image is scaled down by the API
#: anyway, after the tokens have been counted on the full size.
LONGEST_SIDE = 1568

#: Part of the cache key, bumped when the prompt changes so nothing already read is
#: served from a reading a different prompt made.
PROMPT_VERSION = 1

PROMPT = (
    "Transcribe every word of text in this picture exactly as printed.\n"
    "- One line of output per printed line. Keep the printed order.\n"
    "- Put one blank line between paragraphs, messages, headings or other blocks, so "
    "that lines belonging to one paragraph are together and different blocks are apart.\n"
    "- Keep Hebrew as Hebrew, with vowel points and cantillation only where the page "
    "shows them. Keep English and any other language as printed. Translate nothing.\n"
    "- Leave out anything that is not the text: menus, timestamps, buttons, page "
    "furniture, watermarks.\n"
    "- If you cannot read a line with confidence, start that line with a ? and your "
    "best reading. If there is no readable text at all, answer with a single line: ?\n"
    "Answer with the text only, no commentary."
)

MISSING = "Reading pictures needs the `bring` extra: uv sync --extra bring"


@dataclass(frozen=True)
class PageRead:
    """What one picture said, and how many of its lines were doubtful."""

    text: str
    doubtful: int

    @property
    def lines(self) -> list[str]:
        return self.text.split("\n")


def is_picture(path: str | Path) -> bool:
    return Path(path).suffix.lower() in PICTURE_SUFFIXES


def _pillow() -> Any:
    try:
        from PIL import Image, ImageOps
    except ImportError as missing:  # pragma: no cover - the extra is installed in CI
        raise TargumError(MISSING) from missing
    try:
        import pillow_heif
    except ImportError:
        # HEIC alone is lost; every other picture still reads.
        return Image, ImageOps
    pillow_heif.register_heif_opener()  # type: ignore[attr-defined]
    return Image, ImageOps


def probe(path: Path) -> tuple[int, int]:
    """The picture's size, or a sentence about why it is not one.

    Asked at the upload door, before anything is priced, so a file with a picture's
    name and something else's bytes is refused where the reader can still choose again.
    """
    Image, _ = _pillow()
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
            return int(width), int(height)
    except Exception as why:
        raise TargumError("That picture could not be read.") from why


def prepared(path: Path) -> tuple[bytes, str]:
    """The picture as the model should see it: upright, no bigger than it needs to be.

    A phone stores the photo sideways and the orientation in a tag; a model shown the
    bytes sees the page sideways, so the tag is applied first. A screenshot stays PNG,
    because letters are edges and JPEG blurs edges; a photo is a photo and JPEG at 90
    keeps every letter a camera caught.
    """
    Image, ImageOps = _pillow()
    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened) or opened
        image.load()
        width, height = image.size
        longest = max(width, height)
        if longest > LONGEST_SIDE:
            scale = LONGEST_SIDE / longest
            image = image.resize((max(1, round(width * scale)), max(1, round(height * scale))))
        keep_png = (opened.format or "").upper() == "PNG"
        if keep_png and longest <= LONGEST_SIDE:
            return path.read_bytes(), "image/png"
        out = io.BytesIO()
        if keep_png:
            image.save(out, format="PNG", optimize=True)
            return out.getvalue(), "image/png"
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        image.save(out, format="JPEG", quality=90)
        return out.getvalue(), "image/jpeg"


def parse(answer: str) -> PageRead:
    """The model's answer as lines, with the doubtful marks counted and removed."""
    lines: list[str] = []
    doubtful = 0
    for raw in answer.replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        if line.startswith("?"):
            doubtful += 1
            line = line[1:].strip()
        lines.append(line)
    # A picture with no text at all answers "?" alone: one doubtful line, no words.
    while lines and not lines[-1]:
        lines.pop()
    while lines and not lines[0]:
        lines.pop(0)
    return PageRead("\n".join(lines), doubtful)


def reserve(pages: int) -> float:
    """What reading this many pictures is reserved at, before any are read."""
    return round(pages * PAGE_RESERVE, 4)


def _key(path: Path, model: str) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return Cache().key("reading", sha256=digest, model=model, prompt=PROMPT_VERSION)


def cached(paths: list[Path], model: str) -> list[PageRead | None]:
    """What is already read of these, in order. None where a picture still costs."""
    cache = Cache()
    out: list[PageRead | None] = []
    for path in paths:
        held = cache.get("reading", _key(path, model))
        if isinstance(held, dict) and isinstance(held.get("text"), str):
            out.append(PageRead(str(held["text"]), int(held.get("doubtful") or 0)))
        else:
            out.append(None)
    return out


def unread(paths: list[Path], model: str) -> int:
    """How many of these have not been read yet, which is what a reservation prices."""
    return sum(1 for held in cached(paths, model) if held is None)


def read_one(image: bytes, media_type: str, *, model: str, usage: Usage, client: Any) -> PageRead:
    """One request, one picture. The tokens land in `usage` the way a gloss's do."""
    response = client.messages.create(
        model=model,
        max_tokens=4000,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64.b64encode(image).decode("ascii"),
                        },
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
    )
    used = getattr(response, "usage", None)
    came_in = int(getattr(used, "input_tokens", 0) or 0)
    went_out = int(getattr(used, "output_tokens", 0) or 0)
    usage.add(model, came_in, went_out)
    answer = "".join(
        str(getattr(part, "text", ""))
        for part in response.content
        if getattr(part, "type", "") == "text"
    )
    return parse(answer)


def read_pages(
    paths: list[Path],
    *,
    usage: Usage,
    model: str | None = None,
    client: Any = None,
    workers: int = 4,
) -> list[PageRead]:
    """Every picture read, in order, from the cache where it can be and the model where
    it cannot. Four at a time: a phone's worth of photos is a dozen requests, and a
    reader waiting on a card should not wait on them one after another."""
    from .annotate.gloss import GLOSS_MODEL

    chosen = model or GLOSS_MODEL
    if len(paths) > MAX_PAGES:
        raise TargumError(f"That is {len(paths)} pages. targum reads up to {MAX_PAGES} at a time.")
    held = cached(paths, chosen)
    wanted = [index for index, read in enumerate(held) if read is None]
    if wanted:
        if client is None:
            from .translate.anthropic_provider import AnthropicProvider

            client = AnthropicProvider(chosen).client()
        cache = Cache()

        def fetch(index: int) -> tuple[int, PageRead]:
            image, media_type = prepared(paths[index])
            read = read_one(image, media_type, model=chosen, usage=usage, client=client)
            return index, read

        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(wanted)))) as pool:
            for index, read in pool.map(fetch, wanted):
                held[index] = read
                cache.put(
                    "reading",
                    _key(paths[index], chosen),
                    {"text": read.text, "doubtful": read.doubtful},
                )
    return [read for read in held if read is not None]


def can_read() -> tuple[bool, str]:
    """Whether a picture could be read right now: the extra, and a key."""
    try:
        _pillow()
    except TargumError as missing:
        return False, missing.message
    from .translate.anthropic_provider import AnthropicProvider

    return AnthropicProvider().available()
