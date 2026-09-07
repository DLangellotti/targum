"""Reading the words off a picture: the request, the marks, the cache, the ceiling."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from targum import vision
from targum.errors import TargumError
from targum.usage import Usage

FIXTURES = Path(__file__).parent / "fixtures" / "pages"
pytest.importorskip("PIL", reason="the bring extra is not installed: uv sync --extra bring")


class Model:
    """Answers every picture with the same page, and remembers what it was asked."""

    def __init__(self, answer: str = "שָׁלוֹם\n\n?עוֹלָם") -> None:
        self.answer = answer
        self.asked: list[dict] = []
        self.messages = self

    def create(self, **request):  # noqa: ANN003 - the SDK's own shape
        self.asked.append(request)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.answer)],
            usage=SimpleNamespace(input_tokens=974, output_tokens=229),
        )


def test_a_doubtful_line_is_marked_and_counted_and_the_mark_removed() -> None:
    read = vision.parse("שלום\n?עולם\n\nthe end\n\n")
    assert read.lines == ["שלום", "עולם", "", "the end"]
    assert read.doubtful == 1


def test_a_picture_with_no_text_is_one_doubtful_line_and_no_words() -> None:
    read = vision.parse("?")
    assert read.text == "" and read.doubtful == 1


def test_one_request_a_picture_with_the_prompt_and_the_bytes(tmp_path: Path) -> None:
    model = Model()
    usage = Usage()
    reads = vision.read_pages(
        [FIXTURES / "screenshot.png"], usage=usage, model="claude-sonnet-5", client=model
    )
    assert [read.text for read in reads] == ["שָׁלוֹם\n\nעוֹלָם"]
    assert reads[0].doubtful == 1
    assert len(model.asked) == 1
    content = model.asked[0]["messages"][0]["content"]
    assert content[0]["type"] == "image" and content[0]["source"]["media_type"] == "image/png"
    assert "exactly as printed" in content[1]["text"]
    assert usage.by_model == {"claude-sonnet-5": (974, 229)}
    assert usage.cost() == pytest.approx(0.0042, abs=0.0002), "the probe's price"


def test_the_same_picture_is_never_read_twice(tmp_path: Path) -> None:
    model = Model()
    first = Usage()
    vision.read_pages([FIXTURES / "screenshot.png"], usage=first, model="m", client=model)
    again = Usage()
    reads = vision.read_pages([FIXTURES / "screenshot.png"], usage=again, model="m", client=model)
    assert len(model.asked) == 1, "the second read came from the cache"
    assert again.calls == 0 and reads[0].text.startswith("שָׁלוֹם")
    assert vision.unread([FIXTURES / "screenshot.png"], "m") == 0
    assert vision.unread([FIXTURES / "screenshot.png"], "other-model") == 1, "keyed on the model"


def test_pages_come_back_in_the_order_given_however_they_were_read(tmp_path: Path) -> None:
    """Four at a time, and still the reader's order: page two is not page one."""
    from PIL import Image

    paths = []
    for n in range(6):
        path = tmp_path / f"{n:02d}.png"
        Image.new("RGB", (10 + n, 10), "white").save(path)
        paths.append(path)

    class Numbered(Model):
        def create(self, **request):  # noqa: ANN003
            self.asked.append(request)
            size = len(request["messages"][0]["content"][0]["source"]["data"])
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=f"page {size}")],
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            )

    model = Numbered()
    reads = vision.read_pages(paths, usage=Usage(), model="m", client=model, workers=4)
    expected = []
    for path in paths:
        import base64

        expected.append(f"page {len(base64.b64encode(vision.prepared(path)[0]))}")
    assert [read.text for read in reads] == expected


def test_more_than_thirty_pages_are_refused_before_any_is_read(tmp_path: Path) -> None:
    model = Model()
    paths = [FIXTURES / "screenshot.png"] * (vision.MAX_PAGES + 1)
    with pytest.raises(TargumError, match="up to 30"):
        vision.read_pages(paths, usage=Usage(), model="m", client=model)
    assert model.asked == []


def test_a_big_photo_is_scaled_to_the_models_ceiling_and_sent_as_jpeg(tmp_path: Path) -> None:
    from PIL import Image

    big = tmp_path / "photo.jpg"
    Image.new("RGB", (4000, 3000), "white").save(big, quality=80)
    data, kind = vision.prepared(big)
    assert kind == "image/jpeg"
    with Image.open(__import__("io").BytesIO(data)) as sent:
        assert max(sent.size) == vision.LONGEST_SIDE
        assert sent.size == (1568, 1176)


def test_a_screenshot_stays_png_and_is_sent_as_it_is() -> None:
    data, kind = vision.prepared(FIXTURES / "screenshot.png")
    assert kind == "image/png" and data == (FIXTURES / "screenshot.png").read_bytes()


def test_a_sideways_phone_photo_is_turned_upright_first(tmp_path: Path) -> None:
    from PIL import Image

    photo = tmp_path / "sideways.jpg"
    image = Image.new("RGB", (300, 100), "white")
    exif = image.getexif()
    exif[0x0112] = 6  # rotated 90° clockwise, the way a phone held upright stores it
    image.save(photo, exif=exif.tobytes())
    data, _kind = vision.prepared(photo)
    with Image.open(__import__("io").BytesIO(data)) as sent:
        assert sent.size == (100, 300)


def test_a_file_that_is_not_a_picture_is_said_so(tmp_path: Path) -> None:
    fake = tmp_path / "notes.png"
    fake.write_text("not a picture", encoding="utf-8")
    with pytest.raises(TargumError, match="could not be read"):
        vision.probe(fake)
    assert vision.probe(FIXTURES / "screenshot.png") == (720, 420)


def test_the_reservation_is_a_penny_a_page_before_the_reading() -> None:
    assert vision.reserve(30) == pytest.approx(0.30)
    assert vision.reserve(1) == pytest.approx(vision.PAGE_RESERVE)


def test_a_messaging_conversation_is_marked_and_the_mark_taken_off() -> None:
    read = vision.parse("[conversation]\nאמא: מה שלומך?\n\nme: טוב")
    assert read.conversation is True
    assert read.lines == ["אמא: מה שלומך?", "", "me: טוב"], "the marker is not a line"
    assert vision.parse("אמא: מה שלומך?").conversation is False
    assert vision.parse("[Conversation]\nx: y").conversation is True, "however it is cased"


def test_the_cache_remembers_that_a_picture_was_a_conversation() -> None:
    model = Model("[conversation]\nאמא: שלום\n\nme: שלום")
    first = vision.read_pages([FIXTURES / "screenshot.png"], usage=Usage(), model="c", client=model)
    again = vision.read_pages([FIXTURES / "screenshot.png"], usage=Usage(), model="c", client=model)
    assert first[0].conversation and again[0].conversation
    assert len(model.asked) == 1
