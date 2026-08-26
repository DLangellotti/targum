"""Drawn covers for the library, made where the rest of a build is made.

The one place targum asks somebody other than Anthropic for something. Claude reads
images and does not draw them, so a cover has to come from an image model, and this is
the seam where that happens — behind the same shape as every other provider in this
codebase, so the rest of the app neither knows nor cares which one answered.

The key comes from the environment the app already runs in, beside `ANTHROPIC_API_KEY`
in `.env`. Without one the app is exactly as it was: the library draws each text's own
first letter, and nothing here is ever reached.

What a cover is asked to be lives in `catalogue.cover_prompt` — mostly prohibitions,
because §10 of the brand guidelines rules out most of what an image model reaches for
when it hears "Hebrew book cover".
"""

from __future__ import annotations

import base64
import os
from typing import Any, Protocol

from ..errors import TargumError

#: Portrait, because a cover is. The nearest size these models offer to the 2:3 the
#: prompt asks for; the tile crops rather than stretches, so exactness is not the point.
SIZE = "1024x1536"

#: Named rather than left to the model's default, which is the difference between three
#: cents an image and twenty-one. A cover is 2.25rem of flat colour in a list; the tier
#: above this buys detail nothing here is large enough to show.
QUALITY = "medium"

#: Image tokens per million, in and out, for the models this knows how to price. Asking
#: for an image is billed by tokens rather than by the picture, so the only exact number
#: comes back with the answer — see `spent`. The text of the prompt bills at a different
#: rate and is a rounding error beside the image.
TOKEN_PRICES = {"gpt-image-2": (8.0, 30.0)}

#: What gets kept, in pixels across. The tile is 2.25rem — thirty-six of them — so this
#: is three times what the densest screen asks for, and about a fiftieth of the weight.
#: The originals are 1024x1536 and two and a half megabytes each: twenty-five of those on
#: one library page is sixty-five megabytes, which is not a page, and every gram of it
#: would be thrown away by the browser scaling them down to a thumbnail anyway. Nothing
#: keeps the original — a cover can always be drawn again, and none of them is precious.
KEPT_WIDTH = 320

TIMEOUT = 180.0


def shrink(image: bytes, width: int = KEPT_WIDTH) -> bytes:
    """One drawn image, down to what is actually shown.

    Twice at two sizes: the library's tile, and the smaller plate a reader carries on
    every page of a book.
    """
    import io

    from PIL import Image

    small = Image.open(io.BytesIO(image))
    # `Image.LANCZOS` is a shim Pillow keeps for old code and does not declare; the
    # enumeration is where the filter actually lives.
    small.thumbnail((width, width * 4), Image.Resampling.LANCZOS)
    kept = io.BytesIO()
    small.convert("RGB").save(kept, format="WEBP", quality=82, method=6)
    return kept.getvalue()


def named(image: bytes) -> tuple[str, str]:
    """What to call a reference image, and what to say it is.

    `edits` reads the type the upload declares, not the bytes behind it. The reference a
    chapter is drawn against is whatever the book left on disk, which is the kept WEBP
    tile — so declaring PNG for everything is right only in the one run where the book's
    own drawing is still in hand.
    """
    if image[:4] == b"RIFF" and image[8:12] == b"WEBP":
        return "cover.webp", "image/webp"
    if image[:3] == b"\xff\xd8\xff":
        return "cover.jpg", "image/jpeg"
    return "cover.png", "image/png"


def can_shrink() -> bool:
    try:
        import PIL  # noqa: F401
    except ImportError:
        return False
    return True


class Illustrator(Protocol):
    """Whatever can turn a prompt into a picture."""

    @property
    def name(self) -> str:
        """Name and model, recorded with what it drew."""

    @property
    def price(self) -> float:
        """Roughly what one image costs, in dollars, for the budget to reserve."""

    def available(self) -> tuple[bool, str]:
        """Whether this can run, and what to do about it if not."""

    def draw(self, prompt: str, reference: bytes | None = None) -> bytes:
        """One image. `reference` is a cover already drawn, for a chapter to match."""


class OpenAIImages:
    """gpt-image, over plain HTTP.

    Not the `openai` package: one dependency for two endpoints, in a project whose only
    other provider is reached the same way. The two calls are `generations` for a cover
    drawn from its prompt and `edits` for a chapter drawn to match one — passing the
    finished cover as the input image is what makes a chapter look like it belongs to
    its book, more than any amount of describing the palette in words.
    """

    MODEL = "gpt-image-2"
    GENERATE = "https://api.openai.com/v1/images/generations"
    EDIT = "https://api.openai.com/v1/images/edits"

    def __init__(self, model: str | None = None) -> None:
        self.model = model or self.MODEL
        #: What has really been spent, in dollars, once the answers have said. The
        #: reservation below is a guess; this is the receipt.
        self.spent = 0.0

    @property
    def name(self) -> str:
        return f"openai/{self.model}"

    @property
    def price(self) -> float:
        """What to reserve per image, before anything is known.

        Deliberately a little above what a cover actually costs at this quality, because
        the budget has to hold before the tokens are counted — and deliberately not much
        above: the ceiling for one text is $2, the longest book here wants thirty-six
        images, and a reservation over about five cents apiece would have the app refuse
        its own catalogue.
        """
        return 0.05

    def available(self) -> tuple[bool, str]:
        if not os.environ.get("OPENAI_API_KEY"):
            return False, "set OPENAI_API_KEY in .env, beside the Anthropic one"
        if not can_shrink():
            # Refused rather than drawn and kept whole: a library page carrying twenty
            # five untouched covers is sixty-five megabytes, and finding that out from a
            # reader is worse than not drawing.
            return False, "uv sync --extra covers  (Pillow, to shrink what comes back)"
        return True, self.model

    def _answer(self, response: Any) -> bytes:
        if response.status_code >= 400:
            # Their message, not ours: it says which of the many things went wrong.
            raise TargumError("The cover could not be drawn.", response.text[:200])
        answer = response.json()
        used = answer.get("usage") or {}
        prices = TOKEN_PRICES.get(self.model)
        if used and prices:
            self.spent += (
                used.get("input_tokens", 0) * prices[0] + used.get("output_tokens", 0) * prices[1]
            ) / 1_000_000
        else:
            # Counted at the reservation rate rather than not at all. A model this does
            # not know the token prices for still costs money.
            self.spent += self.price
        data = answer.get("data") or []
        if not data or not data[0].get("b64_json"):
            raise TargumError("The cover came back empty.", "Nothing was drawn.")
        return base64.b64decode(data[0]["b64_json"])

    def draw(self, prompt: str, reference: bytes | None = None) -> bytes:
        import httpx

        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise TargumError("No image key.", self.available()[1])
        headers = {"Authorization": f"Bearer {key}"}
        with httpx.Client(timeout=TIMEOUT) as client:
            if reference is None:
                return self._answer(
                    client.post(
                        self.GENERATE,
                        headers=headers,
                        json={
                            "model": self.model,
                            "prompt": prompt,
                            "size": SIZE,
                            "quality": QUALITY,
                            "n": 1,
                        },
                    )
                )
            filename, kind = named(reference)
            return self._answer(
                client.post(
                    self.EDIT,
                    headers=headers,
                    data={
                        "model": self.model,
                        "prompt": prompt,
                        "size": SIZE,
                        "quality": QUALITY,
                        "n": 1,
                    },
                    files={"image": (filename, reference, kind)},
                )
            )


def build() -> Illustrator:
    """The illustrator this deployment has, whether or not it can run."""
    return OpenAIImages()


def ready() -> bool:
    """Whether a cover could be drawn right now, for a page deciding whether to offer."""
    return build().available()[0]
