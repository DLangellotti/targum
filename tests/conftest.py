from __future__ import annotations

import json
import os
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
