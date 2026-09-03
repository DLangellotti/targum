"""`scripts/measure_difficulty.py` must not read scripture as modern Hebrew.

Both ways it did are pinned here (targum-internal#172). The script is loaded by path
because `scripts/` is not a package: it is kept out of the wheel on purpose, since
measuring the catalogue is minutes of work no reader should ever wait for.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from targum.catalogue import Entry
from targum.models import Annotation, Token

GENESIS = "sefaria:Genesis"
#: Hebrew, on the shelf, and not scripture — so `is_biblical` is False for it and none of
#: the scripture rules apply.
MODERN = "sefaria:Mishneh Torah, Human Dispositions"


@pytest.fixture(scope="module")
def script() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "measure_difficulty.py"
    spec = importlib.util.spec_from_file_location("measure_difficulty", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def annotation(*, scripture: bool) -> Annotation:
    """One token, tagged the way each path tags it.

    `PART` is what `annotate/scripture.py` maps the Open Scriptures code `T` onto. The
    modern path is Universal Dependencies, which spells the same word `ADP`.
    """
    return Annotation(
        document_hash="h",
        language="he",
        annotator="oshb/2+dicta/1+tanakh/1",  # identical on both paths, which is the bug
        method="curated:tanakh",  # also identical: both band against the Tanakh
        method_note="n",
        tokens={
            "s1": [
                Token(
                    start=0,
                    end=2,
                    surface="את",
                    lemma="את",
                    band=1,
                    pos="PART" if scripture else "ADP",
                )
            ]
        },
    )


def copy_at(root: Path, home: str, source: str, *, scripture: bool) -> Path:
    folder = root / home / "text-he"
    folder.mkdir(parents=True)
    (folder / "document.json").write_text(json.dumps({"source": source}), encoding="utf-8")
    (folder / "annotation.json").write_text(
        annotation(scripture=scripture).model_dump_json(), encoding="utf-8"
    )
    return folder


def test_the_tag_is_what_tells_the_two_paths_apart(script: ModuleType) -> None:
    assert script.by_scripture_path(annotation(scripture=True))
    assert not script.by_scripture_path(annotation(scripture=False))


def test_scripture_prefers_the_hand_tagging_over_directory_order(
    script: ModuleType, tmp_path: Path
) -> None:
    """The bug: `on_disk` took whichever copy the glob reached first.

    `aaa` sorts before `zzz`, so the modern copy is the one the old code returned, and
    Genesis came out at 17 instead of 12.
    """
    copy_at(tmp_path, "aaa", GENESIS, scripture=False)
    copy_at(tmp_path, "zzz", GENESIS, scripture=True)
    found = script.on_disk(tmp_path, GENESIS)
    assert found is not None
    assert script.by_scripture_path(found)


def test_scripture_prefers_the_hand_tagging_whichever_way_the_names_fall(
    script: ModuleType, tmp_path: Path
) -> None:
    """And the other way round, so the test cannot pass on sort order alone."""
    copy_at(tmp_path, "aaa", GENESIS, scripture=True)
    copy_at(tmp_path, "zzz", GENESIS, scripture=False)
    found = script.on_disk(tmp_path, GENESIS)
    assert found is not None
    assert script.by_scripture_path(found)


def test_the_shipped_corpus_breaks_a_tie(script: ModuleType, tmp_path: Path) -> None:
    copy_at(tmp_path, "aaa", MODERN, scripture=False)
    library = copy_at(tmp_path, "library", MODERN, scripture=False)
    (library / "annotation.json").write_text(
        annotation(scripture=False)
        .model_copy(update={"document_hash": "library"})
        .model_dump_json(),
        encoding="utf-8",
    )
    found = script.on_disk(tmp_path, MODERN)
    assert found is not None
    assert found.document_hash == "library"


def test_a_source_with_no_copy_is_none(script: ModuleType, tmp_path: Path) -> None:
    copy_at(tmp_path, "aaa", MODERN, scripture=False)
    assert script.on_disk(tmp_path, GENESIS) is None


def entry(source: str) -> Entry:
    return Entry(
        id="e",
        title="t",
        author="a",
        language="he",
        source=source,
        blurb="b",
        words=1,
        difficulty=11,
    )


def test_a_modern_only_copy_of_scripture_is_not_measured_from_disk(
    script: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The copy on disk is the wrong reading, and the box cannot do better.

    So the answer is a refusal, not the wrong number. 11 stays 11.
    """
    copy_at(tmp_path, "aaa", GENESIS, scripture=False)
    monkeypatch.setattr(
        script, "ingest", SimpleNamespace(load=lambda source: SimpleNamespace(source=source))
    )
    monkeypatch.setattr(script, "segment_document", lambda document, segmenter: document)
    monkeypatch.setattr(script, "HebrewSegmenter", lambda: None)
    monkeypatch.setattr(
        script,
        "Annotator",
        lambda **kwargs: SimpleNamespace(annotate=lambda segmented: annotation(scripture=False)),
    )
    share, how = script.measured(entry(GENESIS), tmp_path)
    assert share is None
    assert "refused" in how


def test_measuring_now_builds_the_annotator_from_the_source(
    script: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bare `Annotator()` is the modern path, and was used for every biblical entry
    that was not already on disk — 47 of them, all Torah portions."""
    seen: dict[str, object] = {}

    def annotator(**kwargs: object) -> SimpleNamespace:
        seen.update(kwargs)
        return SimpleNamespace(annotate=lambda segmented: annotation(scripture=True))

    monkeypatch.setattr(
        script, "ingest", SimpleNamespace(load=lambda source: SimpleNamespace(source=source))
    )
    monkeypatch.setattr(script, "segment_document", lambda document, segmenter: document)
    monkeypatch.setattr(script, "HebrewSegmenter", lambda: None)
    monkeypatch.setattr(script, "Annotator", annotator)
    monkeypatch.setattr(script, "hard_share", lambda annotation, language: 12)

    share, how = script.measured(entry(GENESIS), tmp_path)
    assert (share, how) == (12, "measured now")
    assert seen["bands"] is not None, "scripture must be banded against the Tanakh"
    assert seen["lemmatizer"] is not None, "scripture must be read by the hand tagging"


def test_a_modern_text_is_measured_from_whatever_copy_it_has(
    script: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """None of this may make a non-scripture text harder to measure."""
    copy_at(tmp_path, "aaa", MODERN, scripture=False)
    monkeypatch.setattr(script, "hard_share", lambda annotation, language: 9)
    assert script.measured(entry(MODERN), tmp_path) == (9, "on disk")
