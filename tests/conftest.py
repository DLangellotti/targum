from __future__ import annotations

import json
import os
import socket
from collections.abc import Callable
from pathlib import Path

import pytest

# The catalogue is private data read from a file at import time, so the suite names its
# own — a handful of entries of the same shape — before anything imports it. Set here,
# at the top of conftest, because a fixture would be too late for a module-level import.
os.environ["TARGUM_CATALOGUE"] = str(Path(__file__).parent / "fixtures" / "catalogue.json")

from targum.models import Block, BlockKind, Document, SegmentedDocument, Translation
from targum.segment import is_downloaded

FIXTURES = Path(__file__).parent / "fixtures"
DECLARATION = FIXTURES / "texts" / "il-declaration-1948.he.md"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "stanza: needs a downloaded Stanza model")
    config.addinivalue_line("markers", "network: reaches a real site; off unless asked")
    config.addinivalue_line("markers", "benchmark: scores the aligner; off unless asked")
    config.addinivalue_line("markers", "ffmpeg: needs ffmpeg on the PATH")


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):
    """Never touch the real cache from a test run.

    Downloaded language models are kept where they are: they are large, and the tests
    that need one skip rather than fetch it.
    """
    from targum.paths import model_dir

    monkeypatch.setenv("TARGUM_MODEL_DIR", str(model_dir()))
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path_factory.mktemp("cache")))


@pytest.fixture(autouse=True)
def shelves_shut(monkeypatch: pytest.MonkeyPatch) -> None:
    """The public catalogue is off unless a test says otherwise.

    It is read from the environment, so a developer who has it exported — anybody who
    has just been looking at the public pages on a local server — saw three unrelated
    tests fail with no hint as to why. The suite decides this, not the shell.
    """
    monkeypatch.delenv("TARGUM_PUBLIC_SHELVES", raising=False)


@pytest.fixture(scope="session")
def free_port() -> Callable[[], int]:
    """A port to start a test server on, asked of the operating system.

    Fixed ports were the obvious thing and the wrong one. Every server here is a daemon
    thread that outlives the test that started it, so an interrupted run leaves one
    holding the port; the next run's server then fails to bind, its tests talk to the
    *previous* run's server over the previous run's directories, and what you get is
    dozens of failures about accounts and shelves with nothing anywhere saying "port".
    Two suites at once does the same thing. Both cost an afternoon to recognise once.

    Binding to port 0 asks the kernel for one nothing is using and hands it back. There
    is a gap between closing this socket and the server opening its own, so this is not
    a guarantee — but it is a race against the rest of the machine rather than a
    certainty of colliding with ourselves.

    A factory rather than a port: a session fixture handing out one number would give
    every server the same one, which is the bug it is here to fix.
    """

    def pick() -> int:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    return pick


@pytest.fixture(autouse=True)
def isolated_weekly(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):
    """No test sees a real issue of the weekly.

    Its root falls back to `./targum-out/weekly`, and the suite runs in a working tree
    that has a `targum-out` in it — so without this a developer's own published issues
    would turn up inside `catalogue.everything()` and the library tests would pass or
    fail depending on what was on that laptop. The read is cached on the file's mtime,
    so that is cleared too: two tests can otherwise write different issues to the same
    path inside one clock tick.
    """
    from targum.weekly import index

    monkeypatch.setenv("TARGUM_WEEKLY_DIR", str(tmp_path_factory.mktemp("weekly")))
    monkeypatch.setattr(index, "_cached", None)
    yield
    index._cached = None


@pytest.fixture
def weekly_root(monkeypatch: pytest.MonkeyPatch) -> Path:
    """The fixture weekly: two published issues at three levels, and one draft.

    Checked before it is handed over, because this is a directory on disk rather than
    something built per test, and a missing reader in it is invisible: `readable` drops
    an edition whose reader is not there, so the catalogue quietly loses that entry and
    the tests downstream fail on arithmetic that never mentions a file. One edition's
    reader going missing failed two tests here with `assert None is not None` and no
    hint of why. This says which file, once, in the fixture that owns it.
    """
    from targum.weekly import index

    root = FIXTURES / "weekly"
    absent = [
        str(reader.relative_to(root))
        for reader in sorted(root.glob("weekly-*-he"))
        if not (reader / "reader" / "index.html").is_file()
    ]
    assert not absent, f"the weekly fixture is missing readers: {', '.join(absent)}"
    monkeypatch.setenv("TARGUM_WEEKLY_DIR", str(root))
    monkeypatch.setattr(index, "_cached", None)
    return root


@pytest.fixture(autouse=True)
def offline(request: pytest.FixtureRequest) -> None:
    """The suite stays offline and free unless TARGUM_NETWORK_TESTS is set."""
    import os

    if request.node.get_closest_marker("network") and not os.environ.get("TARGUM_NETWORK_TESTS"):
        pytest.skip("set TARGUM_NETWORK_TESTS=1 to run tests that reach the network")


@pytest.fixture
def epub_source() -> Path:
    return FIXTURES / "texts" / "reading-old-books.epub"


@pytest.fixture
def hebrew_source() -> Path:
    return DECLARATION


@pytest.fixture
def needs_hebrew_model() -> None:
    if not is_downloaded("he"):
        pytest.skip("Hebrew model not downloaded: run `targum models fetch he`")


class FakeSegmenter:
    """Splits on a full stop. Enough to exercise everything around the segmenter."""

    name = "fake/1"

    def split(self, texts: list[str], language: str) -> list[list[str]]:
        return [[part.strip() + "." for part in text.split(".") if part.strip()] for text in texts]


@pytest.fixture
def fake_segmenter() -> FakeSegmenter:
    return FakeSegmenter()


@pytest.fixture
def document() -> Document:
    blocks = [
        Block(id="b0000", kind=BlockKind.heading, level=1, text="הכרזה על הקמת מדינת ישראל"),
        Block(id="b0001", text="בארץ־ישראל קם העם היהודי. בה עוצבה דמותו הרוחנית."),
        Block(id="b0002", text="בשנת תרנ״ז (1897) נתכנס הקונגרס הציוני."),
    ]
    return Document(
        source="memory", title="Declaration", language="he", blocks=blocks, content_hash="abc123"
    )


@pytest.fixture
def segmented(document: Document, fake_segmenter: FakeSegmenter) -> SegmentedDocument:
    from targum.segment import segment_document

    return segment_document(document, fake_segmenter)


@pytest.fixture
def translation(segmented: SegmentedDocument) -> Translation:
    return Translation(
        name="English, natural",
        document_hash=segmented.document_hash,
        source_language="he",
        target_language="en",
        provider="null",
        segments={s.id: f"[en] {s.text}" for s in segmented.segments},
    )


class Cassette:
    """Replays recorded provider answers, so the suite runs offline and free.

    A cassette is a list of responses keyed in order. A request for segments the
    cassette does not cover returns them empty, which is how the retry path is tested.
    """

    def __init__(self, responses: list[dict[str, str]]) -> None:
        self.responses = list(responses)
        self.calls: list[str] = []

    def messages_parse(self, **kwargs: object) -> object:
        self.calls.append(str(kwargs.get("messages")))
        table = self.responses.pop(0) if self.responses else {}
        return _Response(table)


class _Response:
    def __init__(self, table: dict[str, str]) -> None:
        from targum.translate.anthropic_provider import _Batch, _Line

        self.stop_reason = "end_turn"
        self.parsed_output = _Batch(
            segments=[_Line(id=key, text=value) for key, value in table.items()]
        )


@pytest.fixture
def cassette_dir() -> Path:
    return FIXTURES / "cassettes"


def load_cassette(name: str) -> list[dict[str, str]]:
    path = FIXTURES / "cassettes" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def cassette_factory():
    def make(responses: list[dict[str, str]]) -> Cassette:
        return Cassette(responses)

    return make


class FakeAudioTools:
    """Stands in for ffmpeg and ffprobe, so no audio fixture is ever shipped.

    What the audio tests assert is the plumbing — parts, caching, spans, budgets — and
    a described recording keeps the same time as a real one. Cut files get their own
    name as bytes, so a page holding the wrong part is caught by its content.
    """

    def __init__(self) -> None:
        self.duration = 3600.0
        self.title = ""
        self.artist = ""
        #: (start, end, title) chapter marks the file claims to carry.
        self.chapters: list[tuple[float, float, str]] = []
        #: (start, end) silences, in seconds into the whole file.
        self.pauses: list[tuple[float, float]] = []
        self.cuts: list[tuple[str, float, float]] = []
        self._lengths: dict[str, float] = {}

    def probe(self, path: object) -> dict:
        return {
            "format": {
                "duration": str(self.duration),
                "tags": {"title": self.title, "artist": self.artist},
            },
            "streams": [{"codec_type": "audio", "codec_name": "mp3"}],
            "chapters": [
                {"start_time": str(a), "end_time": str(b), "tags": {"title": t}}
                for a, b, t in self.chapters
            ],
        }

    def cut(self, source: Path, into: Path, start: float, end: float) -> None:
        into.parent.mkdir(parents=True, exist_ok=True)
        into.write_bytes(into.name.encode("utf-8"))
        self.cuts.append((into.name, round(start, 3), round(end, 3)))
        self._lengths[into.name] = end - start

    def length(self, path: Path) -> float:
        return self._lengths.get(Path(path).name, self.duration)

    def silences(self, path: object, start: float, length: float) -> list[tuple[float, float]]:
        return [(a, b) for a, b in self.pauses if start <= a and b <= start + length]


@pytest.fixture
def fake_audio(monkeypatch: pytest.MonkeyPatch) -> FakeAudioTools:
    from targum.audio import tools

    fake = FakeAudioTools()
    monkeypatch.setattr(tools, "ffprobe_json", fake.probe)
    monkeypatch.setattr(tools, "duration", fake.length)
    monkeypatch.setattr(tools, "cut", fake.cut)
    monkeypatch.setattr(tools, "silences", fake.silences)
    return fake
