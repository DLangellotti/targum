"""Pictures and PDFs through the hosted door: the gate, the set, the reading at prepare."""

from __future__ import annotations

import json as json_module
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from targum import vision
from targum.accounts import Store
from targum.mail import ConsoleMailer
from targum.serve import MAX_PICTURE_BYTES, Handler, Library

FIXTURES = Path(__file__).parent / "fixtures" / "pages"
pytest.importorskip("PIL", reason="the bring extra is not installed: uv sync --extra bring")
pytest.importorskip("pypdf", reason="the bring extra is not installed: uv sync --extra bring")


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[int, str, Path, Library]]:
    """A running server on a free port, with a ledger, so a reading's claim can be read."""
    import io

    out = tmp_path / "targum-out"
    out.mkdir()
    token = "test-key"
    library = Library(out, store=Store(tmp_path / "ledger.db"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    handler = type(
        "TestHandler",
        (Handler,),
        {
            "library": library,
            "token": token,
            "page": "<html>start</html>",
            "progress": "<html>your progress</html>",
            "shelf": "<html>library</html>",
            "lists": {k: "<html></html>" for k in ("texts", "words", "phrases")},
            "store": Store(tmp_path / "words.db"),
            "mailer": ConsoleMailer(io.StringIO()),
            "address": f"http://127.0.0.1:{port}",
        },
    )
    server.RequestHandlerClass = handler
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port, token, out, library
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def reading(monkeypatch: pytest.MonkeyPatch) -> list[bytes]:
    """The model, pretending: every picture reads as two lines, one of them doubtful,
    named for its bytes so two pictures come out as two pages. Remembers what it read."""
    read: list[bytes] = []

    def pretend(image: bytes, media_type: str, *, model: str, usage, client):  # noqa: ANN001
        read.append(image)
        usage.add(model, 1000, 200)
        return vision.parse(f"שׁוּרָה {len(image)}\n\n?שורה מסופקת")

    monkeypatch.setattr(vision, "read_one", pretend)
    monkeypatch.setattr(vision, "can_read", lambda: (True, ""))
    return read


def raw(port: int, path: str, body: bytes, kind: str = "application/octet-stream"):
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request("POST", path, body, {"Content-Type": kind})
        response = connection.getresponse()
        return response.status, json_module.loads(response.read())
    finally:
        connection.close()


def begin(port: int, token: str, name: str, size: int):
    return raw(
        port,
        f"/upload/begin?k={token}",
        json_module.dumps({"name": name, "size": size}).encode(),
        "application/json",
    )


def send(port: int, token: str, name: str, body: bytes) -> tuple[int, dict]:
    """One file, up the chunked door in one chunk, ended."""
    status, opened = begin(port, token, name, len(body))
    assert status == 200, opened
    upload = opened["upload"]
    assert raw(port, f"/upload/{upload}/0?k={token}", body)[0] == 200
    return raw(port, f"/upload/{upload}/end?k={token}", b"{}", "application/json")


def prepare(port: int, token: str, payload: dict) -> tuple[int, dict]:
    return raw(
        port,
        f"/prepare?k={token}",
        json_module.dumps({"to": "en", "from": "he", "words": True, **payload}).encode(),
        "application/json",
    )


# --- the gate -------------------------------------------------------------------------


def test_a_picture_and_a_pdf_are_taken_at_the_door_under_their_own_ceiling(served) -> None:
    port, token, _out, _library = served
    assert begin(port, token, "page.png", 10)[0] == 200
    assert begin(port, token, "page.HEIC", 10)[0] == 200
    assert begin(port, token, "handout.pdf", 10)[0] == 200
    status, answer = begin(port, token, "page.jpg", MAX_PICTURE_BYTES + 1)
    assert status == 413 and "over 25 MB" in answer["error"]
    status, answer = begin(port, token, "notes.docx", 10)
    assert status == 400 and "picture" in answer["error"]


def test_a_picture_is_proved_a_picture_at_the_door(served, reading) -> None:
    port, token, _out, _library = served
    status, done = send(port, token, "screen.png", (FIXTURES / "screenshot.png").read_bytes())
    assert status == 200 and done["picture"] is True and done["upload"]
    status, refused = send(port, token, "fake.png", b"not a picture at all")
    assert status == 400 and "could not be read" in refused["error"]
    assert reading == [], "nothing is read at the door; the reading is the quote's"


def test_a_pdf_is_counted_at_the_door_and_a_book_refused(served, tmp_path: Path) -> None:
    from pypdf import PdfWriter

    port, token, _out, _library = served
    status, done = send(port, token, "handout.pdf", (FIXTURES / "handout.pdf").read_bytes())
    assert status == 200 and done["pages"] == 1
    writer = PdfWriter()
    for _ in range(31):
        writer.add_blank_page(width=100, height=100)
    long = tmp_path / "book.pdf"
    with long.open("wb") as out:
        writer.write(out)
    status, refused = send(port, token, "book.pdf", long.read_bytes())
    assert status == 413 and "31 pages" in refused["error"] and "up to 30" in refused["error"]


# --- the set, and the reading at prepare ------------------------------------------------


def two_pictures(tmp_path: Path) -> list[bytes]:
    from PIL import Image

    pictures = []
    for n, width in enumerate((300, 320)):
        path = tmp_path / f"photo{n}.jpg"
        Image.new("RGB", (width, 200), "white").save(path, quality=85)
        pictures.append(path.read_bytes())
    return pictures


def test_several_pictures_are_one_text_read_at_the_quote_and_shown_on_the_card(
    served, reading, tmp_path: Path
) -> None:
    port, token, out, library = served
    ids = []
    for n, body in enumerate(two_pictures(tmp_path)):
        status, done = send(port, token, f"page{n}.jpg", body)
        assert status == 200, done
        ids.append(done["upload"])
    status, job = prepare(port, token, {"uploads": ids})
    assert status == 200, job
    assert job["pages"] == 2, job
    assert len(reading) == 2, "each picture read once, at the quote"
    assert job["doubtful"] == 2, "one doubtful line a page, counted"
    assert job["excerpt"][0].startswith("שׁוּרָה"), job["excerpt"]
    assert len(job["excerpt"]) == 4
    assert job["stage"] in {"ready", "blocked"}, job
    assert not job["error"], job

    # One folder, numbered in the order chosen, with the chunked door's marks gone so
    # the sweep never eats a text's source.
    sets = [f for f in (out / "local" / "uploads").iterdir() if f.is_dir()]
    assert len(sets) == 1, sets
    assert sorted(p.name for p in sets[0].iterdir()) == ["01-page0.jpg", "02-page1.jpg"]

    # The reading is the one spend before a card: reserved, then settled to the receipt.
    held = library.jobs[job["id"]]
    assert held.reading == pytest.approx(2 * (1000 * 2.0 + 200 * 10.0) / 1_000_000)
    assert held.spent == held.reading
    row = next(r for r in library.store.jobs() if r["id"] == job["id"])
    assert row["spent"] == pytest.approx(held.reading)
    assert row["claimed"] == pytest.approx(held.reading), "settled, not left at the reserve"

    # The build that follows reads nothing again: the same bytes are in the cache.
    library.prepare(held)
    assert len(reading) == 2


def test_a_pdf_with_a_text_layer_is_read_by_nothing_that_costs(served, reading) -> None:
    port, token, _out, library = served
    status, done = send(port, token, "handout.pdf", (FIXTURES / "handout.pdf").read_bytes())
    assert status == 200
    status, job = prepare(port, token, {"upload": done["upload"]})
    assert status == 200, job
    assert reading == [], "no model read a page"
    assert job["pages"] == 1 and job["doubtful"] == 1, job
    assert job["excerpt"][0].startswith("נָסַעְתִּי"), job["excerpt"]
    assert library.jobs[job["id"]].reading == 0.0
    assert not job["error"], job


def test_a_scan_is_refused_at_the_quote_and_nothing_is_spent(served, reading) -> None:
    port, token, _out, library = served
    status, done = send(port, token, "scan.pdf", (FIXTURES / "scan.pdf").read_bytes())
    assert status == 200
    status, job = prepare(port, token, {"upload": done["upload"]})
    assert status == 200, job
    assert job["stage"] == "failed" and "scan" in job["error"], job
    assert reading == [] and library.jobs[job["id"]].reading == 0.0


def test_a_thirty_first_picture_is_refused_before_any_is_read(served, reading) -> None:
    port, token, _out, _library = served
    body = (FIXTURES / "screenshot.png").read_bytes()
    ids = []
    for n in range(31):
        # The same bytes are one file at the door; vary them so there are 31 uploads.
        status, done = send(port, token, f"p{n}.png", body + bytes([n]))
        assert status == 200, done
        ids.append(done["upload"])
    status, answer = prepare(port, token, {"uploads": ids})
    assert status == 400 and "up to 30" in answer["error"], answer
    assert reading == []


def test_pictures_and_something_else_together_are_refused(served, reading) -> None:
    port, token, _out, _library = served
    _s, picture = send(port, token, "page.png", (FIXTURES / "screenshot.png").read_bytes())
    _s, handout = send(port, token, "handout.pdf", (FIXTURES / "handout.pdf").read_bytes())
    status, answer = prepare(port, token, {"uploads": [picture["upload"], handout["upload"]]})
    assert status == 400 and "pictures of one text" in answer["error"]
    assert reading == []


def test_without_a_key_the_card_says_nothing_new_can_be_built_and_nothing_is_read(
    served, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from targum.serve import NO_KEY

    port, token, _out, _library = served
    read: list[bytes] = []
    monkeypatch.setattr(vision, "read_one", lambda *a, **k: read.append(b"x"))
    monkeypatch.setattr(vision, "can_read", lambda: (False, "no key"))
    _s, done = send(port, token, "page.png", (FIXTURES / "screenshot.png").read_bytes())
    status, job = prepare(port, token, {"upload": done["upload"]})
    assert status == 200 and job["stage"] == "blocked" and job["blocked"] == NO_KEY, job
    assert read == []


def test_a_refused_reservation_blocks_the_card_before_the_reading(
    served, reading, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, token, _out, library = served
    library.budget = 0.0  # the box is out of money for the day
    _s, done = send(port, token, "page.png", (FIXTURES / "screenshot.png").read_bytes())
    status, job = prepare(port, token, {"upload": done["upload"]})
    assert status == 200 and job["stage"] == "blocked" and job["blocked"], job
    assert reading == [], "refused before a picture was read"
