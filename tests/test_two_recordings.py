"""A portion's two readings: the chanting and the plain reading (targum-internal#412).

What can go wrong here is mostly addressing again — the plain reading is cut per chapter
and an aliyah is not, so a section that crosses a chapter must hear both chapters and
nothing either side of its own verses — and then the page: both readings named, both
credited, and both carried as files beside the reader rather than inside it.
"""

from __future__ import annotations

import json
import re
import shutil
import threading
from collections.abc import Iterator
from datetime import datetime
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from test_parasha_cut import a_book

from targum.accounts import Store
from targum.audio import PAD
from targum.mail import ConsoleMailer
from targum.models import BlockKind, Document, Segment
from targum.recording import Part, Recording
from targum.recording import index as recording_index
from targum.recording import splice as splicing

FIXTURES = Path(__file__).parent / "fixtures" / "parasha"

#: Nitzavim-Vayeilech, the one portion the calendar fixture builds.
PORTION = "sefaria:Deuteronomy 29:9-31:30"


def chapter_part(book: str, chapter: int, verses: int) -> Part:
    """A chapter's file with verse n at [2n, 2n + 1.5]: half a second of quiet between."""
    return Part(
        ref=f"{book} {chapter}",
        audio=f"{book.lower()}-{chapter}.mp3",
        spans={f"{book} {chapter}:{n}": [2.0 * n, 2.0 * n + 1.5] for n in range(1, verses + 1)},
    )


@pytest.fixture
def stand_in(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[list[tuple[Path, float]]]:
    """ffmpeg and ffprobe stood in for: every file is 100 seconds long, and a splice writes
    a few bytes and records what it was asked to join."""
    from targum.audio import tools

    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    joined: list[list[tuple[Path, float]]] = []

    def splice(pieces: list[tuple[Path, float, float]], into: Path) -> None:
        joined.append([(source, round(end - start, 3)) for source, start, end in pieces])
        into.parent.mkdir(parents=True, exist_ok=True)
        into.write_bytes(b"ID3spliced")

    monkeypatch.setattr(tools, "duration", lambda path: 100.0)
    monkeypatch.setattr(tools, "splice", splice)
    return joined


# -- finding the parts -------------------------------------------------------


def test_a_section_across_a_chapter_finds_both_chapters() -> None:
    recording = Recording(
        source="sefaria:Genesis",
        credit="Somebody",
        licence="CC BY-SA 3.0",
        parts=[chapter_part("Genesis", 1, 31), chapter_part("Genesis", 2, 25)],
    )
    refs = [f"Genesis 1:{n}" for n in range(1, 32)] + ["Genesis 2:1", "Genesis 2:2"]
    assert [part.ref for part in recording.parts_for(refs)] == ["Genesis 1", "Genesis 2"]
    assert recording.part_for(refs) is recording.parts[0], "part_for is unchanged"
    assert recording.parts_for(["Genesis 3:1"]) == []
    assert recording.parts_for(["", ""]) == []


def test_a_cut_breathes_but_never_into_a_verse_it_does_not_hold() -> None:
    tight = Part(
        ref="Genesis 2",
        audio="genesis-2.mp3",
        spans={
            "Genesis 2:3": [0.0, 7.9],
            "Genesis 2:4": [8.0, 9.5],
            "Genesis 2:5": [9.6, 11.5],
            "Genesis 2:6": [11.6, 13.0],
        },
    )
    assert splicing.plan(tight, ["Genesis 2:4", "Genesis 2:5"]) == (7.9, 11.6), (
        "the margin stops where the neighbours are"
    )
    roomy = chapter_part("Genesis", 2, 25)
    assert splicing.plan(roomy, ["Genesis 2:4"]) == (8.0 - PAD, 9.5 + PAD)
    assert splicing.plan(roomy, ["Genesis 2:1"]) == (2.0 - PAD, 3.5 + PAD)
    assert splicing.plan(roomy, ["Genesis 1:1"]) is None


def test_the_spliced_spans_run_on_from_one_chapter_into_the_next(
    tmp_path: Path, stand_in: list[list[tuple[Path, float]]]
) -> None:
    for name in ("genesis-1.mp3", "genesis-2.mp3"):
        (tmp_path / name).write_bytes(b"ID3")
    one, two = chapter_part("Genesis", 1, 31), chapter_part("Genesis", 2, 25)
    refs = ["Genesis 1:30", "Genesis 1:31", "Genesis 2:1", "Genesis 2:2", "Genesis 2:3"]
    path, spans = splicing.splice([(tmp_path, one), (tmp_path, two)], refs)
    assert path.is_file()
    # Chapter 1 from 59.65 to 63.85, so chapter 2's piece — from 1.65 — starts at 4.2.
    assert stand_in[0] == [
        (tmp_path / "genesis-1.mp3", 4.2),
        (tmp_path / "genesis-2.mp3", 6.2),
    ]
    assert spans["Genesis 1:30"] == [0.35, 1.85]
    assert spans["Genesis 1:31"] == [2.35, 3.85]
    assert spans["Genesis 2:1"] == [4.55, 6.05]
    assert spans["Genesis 2:3"] == [8.55, 10.05]

    again, same = splicing.splice([(tmp_path, one), (tmp_path, two)], refs)
    assert again == path and same == spans
    assert len(stand_in) == 1, "the same verses of the same files are cut once"


def test_a_cut_that_runs_past_the_end_of_its_file_moves_the_next_one_up(
    tmp_path: Path, stand_in, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum.audio import tools

    monkeypatch.setattr(
        tools, "duration", lambda path: 63.7 if path.name == "genesis-1.mp3" else 99
    )
    for name in ("genesis-1.mp3", "genesis-2.mp3"):
        (tmp_path / name).write_bytes(b"ID3")
    one, two = chapter_part("Genesis", 1, 31), chapter_part("Genesis", 2, 25)
    _, spans = splicing.splice([(tmp_path, one), (tmp_path, two)], ["Genesis 1:31", "Genesis 2:1"])
    # Chapter 1's cut is 61.65 to the file's end at 63.7: 2.05 seconds, not 2.2.
    assert spans["Genesis 2:1"] == pytest.approx([2.05 + PAD, 2.05 + PAD + 1.5])


def test_a_cut_of_nothing_is_an_error_the_caller_can_hold() -> None:
    from targum.errors import TargumError

    with pytest.raises(TargumError):
        splicing.splice([(Path("/nowhere"), chapter_part("Ruth", 1, 22))], ["Ruth 4:1"])


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not on this machine")
def test_a_real_splice_is_as_long_as_its_pieces(tmp_path: Path, monkeypatch) -> None:
    import subprocess

    from targum.audio import tools

    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    for name, seconds in (("a.mp3", 3), ("b.mp3", 2)):
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency=440:duration={seconds}",
            ]
            + [str(tmp_path / name)],
            capture_output=True,
            check=True,
        )
    into = tmp_path / "joined.mp3"
    tools.splice([(tmp_path / "a.mp3", 1.0, 3.0), (tmp_path / "b.mp3", 0.0, 1.5)], into)
    assert tools.duration(into) == pytest.approx(3.5, abs=0.1)


# -- the readings a section has -----------------------------------------------


def verse(ref: str, sid: str) -> Segment:
    return Segment(
        id=sid, block_id=sid, block_index=0, index=0, kind=BlockKind.verse, text="שלום", ref=ref
    )


def shelve(root: Path, recording: Recording) -> Path:
    folder = root / recording_index.slug(recording.source)
    folder.mkdir(parents=True, exist_ok=True)
    for part in recording.parts:
        (folder / part.audio).write_bytes(b"ID3not-really-audio")
    (folder / recording_index.MANIFEST).write_text(recording.model_dump_json(), encoding="utf-8")
    return folder


@pytest.fixture
def genesis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Bereshit's first aliyah chanted, and Genesis 1–2 read plainly."""
    root = tmp_path / "recordings"
    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(root))
    shelve(
        root,
        Recording(
            source="sefaria:Genesis",
            credit="Rabbi Dan Be'eri",
            licence="CC BY-SA 3.0",
            licence_url="https://creativecommons.org/licenses/by-sa/3.0/",
            parts=[chapter_part("Genesis", 1, 31), chapter_part("Genesis", 2, 25)],
        ),
    )
    refs = [f"Genesis 1:{n}" for n in range(1, 32)] + [f"Genesis 2:{n}" for n in (1, 2, 3)]
    shelve(
        root,
        Recording(
            source="sefaria:Genesis 1:1-6:8",
            credit="PocketTorah, Avery-Binder trope",
            licence="CC BY-SA 3.0",
            parts=[
                Part(
                    ref="Bereshit 1",
                    audio="aliyah-01.mp3",
                    spans={ref: [float(n), n + 0.9] for n, ref in enumerate(refs)},
                )
            ],
        ),
    )
    return root


def aliyah_one() -> list[Segment]:
    return [verse("Genesis 1:1", "a"), verse("Genesis 1:31", "b"), verse("Genesis 2:3", "c")]


def test_an_aliyah_is_heard_chanted_and_spoken(genesis: Path, stand_in) -> None:
    from targum.render.builder import voices

    document = Document(source="sefaria:Genesis 1:1-6:8", title="", language="he", blocks=[])
    chanted, spoken = voices(document, aliyah_one(), beside=True)
    assert (chanted.voice, spoken.voice) == ("chanted", "spoken"), "the chanting first"
    assert chanted.credited == "Chanted by" and chanted.credit.startswith("PocketTorah")
    assert spoken.credited == "Read by" and spoken.credit == "Rabbi Dan Be'eri"
    assert chanted.beside and spoken.beside, "both named on the disk, neither inlined"
    assert not chanted.audio.startswith("data:") and Path(chanted.audio).is_file()
    assert set(spoken.spans) == {"a", "b", "c"}, "Genesis 2:3 is heard, from chapter 2"
    assert len(stand_in[0]) == 2, "one piece of each chapter"


def test_a_section_with_no_chanting_has_the_plain_reading_alone(genesis: Path, stand_in) -> None:
    from targum.render.builder import voices

    document = Document(source="sefaria:Genesis 2:4-2:9", title="", language="he", blocks=[])
    (spoken,) = voices(document, [verse("Genesis 2:4", "x")], beside=True)
    assert spoken.voice == "spoken" and spoken.spans == {"x": [0.35, 1.85]}


def test_a_book_and_a_text_not_asked_keep_their_one_inlined_reading(genesis: Path) -> None:
    from targum.render.builder import speech, voices

    book = Document(source="sefaria:Genesis", title="", language="he", blocks=[])
    (alone,) = voices(book, aliyah_one(), beside=False)
    assert alone == speech(book, aliyah_one())
    assert alone.audio.startswith("data:audio/mpeg;base64,") and alone.voice == ""
    # A book's own reader asked to carry its sound beside: the recording is the plain
    # reading already, so it is not offered twice.
    (beside,) = voices(book, aliyah_one(), beside=True)
    assert beside.voice == "" and beside.beside
    portion = Document(source="sefaria:Genesis 1:1-6:8", title="", language="he", blocks=[])
    (kept,) = voices(portion, aliyah_one(), beside=False)
    assert kept.audio.startswith("data:") and kept.credit.startswith("PocketTorah")


def test_without_ffmpeg_a_crossing_section_keeps_its_first_chapter(
    genesis: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from targum.audio import tools
    from targum.errors import TargumError
    from targum.render.builder import voices

    def broken(*_: object) -> float:
        raise TargumError(tools.UNREADABLE)

    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(tools, "duration", broken)
    document = Document(source="sefaria:Genesis 1:1-6:8", title="", language="he", blocks=[])
    _, spoken = voices(document, aliyah_one(), beside=True)
    assert spoken.audio.endswith("genesis-1.mp3")
    assert set(spoken.spans) == {"a", "b"}, "the verse in chapter 2 goes without a control"


# -- the portion, built and served ------------------------------------------------


@pytest.fixture
def portion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stand_in) -> Path:
    """Nitzavim-Vayeilech built, with Deuteronomy read plainly and chapter 29 chanted."""
    from targum.parasha import build as corpus_build
    from targum.parasha import calendar as cal

    monkeypatch.setenv("TARGUM_PARASHA_DIR", str(tmp_path / "parasha"))
    monkeypatch.setenv("TARGUM_PUBLIC_SHELVES", "1")
    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(tmp_path / "recordings"))
    a_wednesday = datetime(2026, 9, 2, 12, tzinfo=ZoneInfo(cal.FLIP_ZONE))
    monkeypatch.setattr(cal, "now_in_flip_zone", lambda moment=None: a_wednesday)
    (tmp_path / "parasha" / "calendar").mkdir(parents=True)
    for one in FIXTURES.glob("*.json"):
        shutil.copy(one, tmp_path / "parasha" / "calendar" / one.name)
    library = tmp_path / "library"
    a_book(library / "דברים-he", "Deuteronomy", "דברים", {29: 29, 30: 20, 31: 30})
    a_book(library / "ישעיהו-he", "Isaiah", "ישעיהו", {61: 11, 62: 12, 63: 19})
    a_book(library / "חבקוק-he", "Habakkuk", "חבקוק", {3: 19})
    shelve(
        tmp_path / "recordings",
        Recording(
            source="sefaria:Deuteronomy",
            credit="Rabbi Dan Be'eri",
            licence="CC BY-SA 3.0",
            licence_url="https://creativecommons.org/licenses/by-sa/3.0/",
            parts=[chapter_part("Deuteronomy", c, n) for c, n in ((29, 29), (30, 20), (31, 30))],
        ),
    )
    shelve(
        tmp_path / "recordings",
        Recording(
            source=PORTION,
            credit="PocketTorah, Avery-Binder trope",
            licence="CC BY-SA 3.0",
            parts=[
                chapter_part("Deuteronomy", 29, 29).model_copy(update={"audio": "aliyah-01.mp3"})
            ],
        ),
    )
    corpus_build.build(
        years=[2026],
        corpus_years=[2026],
        schedules=[cal.Schedule.diaspora],
        library=library,
    )
    return tmp_path / "parasha" / "read" / "nitzavim-vayeilech" / "reader"


def payload(page: str) -> dict:
    found = re.search(
        r'<script type="application/json" id="targum-data">(.*?)</script>', page, re.S
    )
    assert found, "the page carries its data"
    return json.loads(found.group(1))


def test_the_first_aliyah_carries_both_readings_beside_it(portion: Path) -> None:
    page = (portion / "sec-0001.html").read_text(encoding="utf-8")
    speech = payload(page)["speech"]
    assert speech["audio"] == "audio/chanted-0001.mp3"
    assert [one["key"] for one in speech["voices"]] == ["chanted", "spoken"]
    assert speech["voices"][1]["audio"] == "audio/spoken-0001.mp3"
    assert speech["voices"][1]["spans"], "the plain reading follows along verse by verse"
    assert (portion / "audio" / "chanted-0001.mp3").is_file()
    assert (portion / "audio" / "spoken-0001.mp3").is_file()
    assert "data:audio" not in page, "nothing inlined"
    assert 'data-recording="chanted"' in page and 'data-recording="spoken"' in page
    assert "Chanted by PocketTorah, Avery-Binder trope" in page
    assert "Read by Rabbi Dan Be" in page


def test_an_aliyah_with_no_chanting_has_one_reading_and_no_switch(portion: Path) -> None:
    last = sorted(portion.glob("sec-*.html"))[-1]
    page = last.read_text(encoding="utf-8")
    speech = payload(page)["speech"]
    assert speech["audio"].startswith("audio/spoken-")
    assert "voices" not in speech
    assert "data-recording=" not in page
    assert "Read by Rabbi Dan Be" in page


def test_an_aliyah_across_a_chapter_is_joined_from_both(portion: Path, stand_in) -> None:
    sources = [{source.name for source, _ in pieces} for pieces in stand_in]
    assert any(len(names) > 1 for names in sources), "some aliyah crossed a chapter"


@pytest.fixture
def serving(tmp_path: Path, portion: Path) -> Iterator[int]:
    from targum.serve import Handler, Library

    out = tmp_path / "targum-out"
    out.mkdir(exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    server.RequestHandlerClass = type(
        "TestHandler",
        (Handler,),
        {
            "library": Library(out),
            "token": "test-key",
            "page": "<html>start</html>",
            "shelf": "<html>library</html>",
            "store": Store(tmp_path / "words.db"),
            "mailer": ConsoleMailer(),
            "address": f"http://127.0.0.1:{port}",
        },
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        server.shutdown()
        server.server_close()


def test_a_reading_beside_the_page_is_served_as_sound(serving: int) -> None:
    base = "/parasha/read/nitzavim-vayeilech/reader/audio"
    conn = HTTPConnection("127.0.0.1", serving)
    conn.request("GET", f"{base}/spoken-0001.mp3", headers={"Range": "bytes=0-2"})
    answer = conn.getresponse()
    assert answer.status == 206, "a player seeks by ranges"
    assert answer.getheader("Content-Type") == "audio/mpeg"
    assert answer.read() == b"ID3"
    conn.close()
    for wrong in (f"{base}/nothing.mp3", f"{base}/../sec-0001.mp3", f"{base}/x.wav"):
        conn = HTTPConnection("127.0.0.1", serving)
        conn.request("GET", wrong)
        assert conn.getresponse().status == 404, wrong
        conn.close()
