"""The one provider here that is not Anthropic, and what it costs.

Claude reads images and does not draw them, so a cover comes from an image model. What
matters in these tests is not the pictures — nothing here draws one — but the two things
the rest of the app trusts this module for: that it stays silent without a key, and that
it reports what was really spent rather than what was guessed at.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from targum import covers
from targum.errors import TargumError


class Answer:
    """What httpx would hand back, with only the parts this reads."""

    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self._payload = payload
        self.status_code = status
        self.text = json.dumps(payload)

    def json(self) -> dict[str, Any]:
        return self._payload


def drawn(**usage: int) -> dict[str, Any]:
    return {"data": [{"b64_json": "aGk="}], "usage": usage}


def test_what_it_cost_comes_back_with_the_answer() -> None:
    """An image is billed by tokens rather than by the picture, so `images × price` is a
    receipt only while the price is flat. gpt-image-2's is not."""
    illustrator = covers.OpenAIImages("gpt-image-2")
    assert illustrator.spent == 0.0

    illustrator._answer(Answer(drawn(input_tokens=1_000, output_tokens=2_000)))

    # $8 per million in, $30 per million out.
    assert illustrator.spent == pytest.approx(1_000 * 8 / 1e6 + 2_000 * 30 / 1e6)


def test_spending_accumulates_across_a_set() -> None:
    illustrator = covers.OpenAIImages("gpt-image-2")
    for _ in range(3):
        illustrator._answer(Answer(drawn(input_tokens=1_000, output_tokens=1_000)))
    assert illustrator.spent == pytest.approx(3 * (1_000 * 8 / 1e6 + 1_000 * 30 / 1e6))


def test_a_model_it_cannot_price_is_still_counted() -> None:
    """Counted at the reservation rate rather than not at all: an unpriced model still
    costs money, and a ledger that says zero is worse than one that says roughly."""
    illustrator = covers.OpenAIImages("some-model-nobody-here-has-priced")
    illustrator._answer(Answer(drawn(input_tokens=1_000, output_tokens=1_000)))
    assert illustrator.spent == pytest.approx(illustrator.price)


def test_an_answer_with_no_image_in_it_is_an_error() -> None:
    illustrator = covers.OpenAIImages()
    with pytest.raises(TargumError, match="came back empty"):
        illustrator._answer(Answer({"data": []}))


def test_the_provider_says_what_went_wrong() -> None:
    """Their message, not ours. "The cover could not be drawn" is true of a bad key, a
    billing limit and a wrong model alike, and only one of those is worth acting on."""
    refused = Answer({"error": {"message": "Billing hard limit has been reached."}}, status=400)
    with pytest.raises(TargumError) as caught:
        covers.OpenAIImages()._answer(refused)
    assert "Billing hard limit" in (caught.value.hint or "")


def test_the_reservation_leaves_room_for_the_longest_book() -> None:
    """The ceiling for one text is $2 and the longest book here wants thirty-six images.
    A reservation over about five cents apiece would have the app refuse its own
    catalogue — which is a thing to find out here rather than from a reader."""
    from targum.serve import MAX_COST

    assert covers.OpenAIImages().price * 36 < MAX_COST


def test_without_a_key_it_says_which_one(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    usable, detail = covers.build().available()
    assert usable is False
    assert "OPENAI_API_KEY" in detail
    assert covers.ready() is False


def test_what_is_kept_is_a_tile_and_not_the_original() -> None:
    """The originals are 1024x1536 and two and a half megabytes. Twenty-five of those on
    one library page is sixty-five megabytes, and every byte would be thrown away by the
    browser scaling them into a 36px tile."""
    from io import BytesIO

    from PIL import Image

    original = BytesIO()
    Image.new("RGB", (1024, 1536), (200, 180, 140)).save(original, format="PNG")
    raw = original.getvalue()

    kept = covers.shrink(raw)
    shown = Image.open(BytesIO(kept))

    assert shown.format == "WEBP"
    assert shown.width == covers.KEPT_WIDTH
    assert shown.height == covers.KEPT_WIDTH * 3 // 2, "the proportions are kept"
    assert len(kept) < len(raw) / 10


def test_it_will_not_draw_what_it_cannot_shrink(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Refused rather than drawn and kept whole: finding out from a reader that the
    library page is sixty-five megabytes is worse than not drawing."""
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(covers, "can_shrink", lambda: False)
    usable, detail = covers.build().available()
    assert usable is False
    assert "covers" in detail


def test_a_chapter_is_drawn_against_the_tile_that_is_really_on_disk() -> None:
    """`edits` reads the type an upload declares, not the bytes behind it, and the only
    thing a cover run leaves on disk is a WEBP tile. A chapter drawn in a later run than
    its book hands that tile back as its reference — under its own name, or the endpoint
    refuses a picture it was told was a PNG."""
    from io import BytesIO

    from PIL import Image

    tile = BytesIO()
    Image.new("RGB", (320, 480), (200, 180, 140)).save(tile, format="WEBP")
    assert covers.named(tile.getvalue()) == ("cover.webp", "image/webp")

    fresh = BytesIO()
    Image.new("RGB", (16, 16), (0, 0, 0)).save(fresh, format="PNG")
    assert covers.named(fresh.getvalue()) == ("cover.png", "image/png")

    photograph = BytesIO()
    Image.new("RGB", (16, 16), (0, 0, 0)).save(photograph, format="JPEG")
    assert covers.named(photograph.getvalue()) == ("cover.jpg", "image/jpeg")


def test_the_reference_goes_up_under_its_own_type(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The whole point of `edits` is that the book's cover goes with the request. What
    the request says that file is has to match what it is."""
    sent: dict[str, Any] = {}

    class Client:
        def __enter__(self) -> Client:
            return self

        def __exit__(self, *_: Any) -> None:
            return None

        def post(self, url: str, **kwargs: Any) -> Answer:
            sent.update(kwargs)
            return Answer(drawn(input_tokens=1, output_tokens=1))

    import httpx

    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(httpx, "Client", lambda **_: Client())
    covers.OpenAIImages().draw("a chapter", reference=b"RIFF\x00\x00\x00\x00WEBPsomething")

    assert sent["files"]["image"][0] == "cover.webp"
    assert sent["files"]["image"][2] == "image/webp"
