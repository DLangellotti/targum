from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from targum.errors import ProviderError, TargumError
from targum.models import (
    Annotation,
    Document,
    SegmentedDocument,
    Style,
    Token,
    Translation,
    Vocalization,
    read_artifact,
)
from targum.pipeline import Build, Result


def build(source: Path, out: Path, segmenter: object, **kwargs: object) -> Build:
    return Build(
        str(source),
        target_language="en",
        provider_name="null",
        out=out,
        segmenter=segmenter,  # type: ignore[arg-type]
        **kwargs,  # type: ignore[arg-type]
    )


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "declaration.md"
    path.write_text(
        "# הכרזה\n\nבארץ־ישראל קם העם היהודי. בה עוצבה דמותו.\n\nבשנת תרנ״ז נתכנס הקונגרס.\n",
        encoding="utf-8",
    )
    return path


def test_writes_every_artifact(source: Path, tmp_path: Path, fake_segmenter: object) -> None:
    out = tmp_path / "out"
    result = build(source, out, fake_segmenter).run()

    assert (out / "document.json").exists()
    assert (out / "segments.json").exists()
    assert (out / "translations" / "null.natural.en.json").exists()
    assert result.index.exists()


def test_artifacts_are_readable_json(source: Path, tmp_path: Path, fake_segmenter: object) -> None:
    out = tmp_path / "out"
    build(source, out, fake_segmenter).run()
    data = json.loads((out / "document.json").read_text(encoding="utf-8"))
    from targum.models import SCHEMA_VERSION

    assert data["schema_version"] == SCHEMA_VERSION
    assert data["language"] == "he"


def test_a_second_run_redoes_nothing(source: Path, tmp_path: Path, fake_segmenter: object) -> None:
    out = tmp_path / "out"
    build(source, out, fake_segmenter).run()
    again = build(source, out, fake_segmenter).run()
    assert "document" in again.reused
    assert "segments" in again.reused
    assert any(item.startswith("translation") for item in again.reused)


def test_force_redoes_everything(source: Path, tmp_path: Path, fake_segmenter: object) -> None:
    out = tmp_path / "out"
    build(source, out, fake_segmenter).run()
    again = build(source, out, fake_segmenter, force=True).run()
    assert again.reused == []


def test_a_hand_edited_document_wins(source: Path, tmp_path: Path, fake_segmenter: object) -> None:
    # Fixing a bad extraction by editing the artifact and rerunning is how this is
    # meant to work, so the next run must not overwrite the edit.
    out = tmp_path / "out"
    build(source, out, fake_segmenter).run()

    path = out / "document.json"
    document = read_artifact(Document, path)
    assert document is not None
    document.blocks[1].text = "טקסט מתוקן."
    document.write(path)

    result = build(source, out, fake_segmenter).run()
    assert "document (edited)" in result.reused
    assert any("טקסט מתוקן" in segment.text for segment in result.segmented.segments)


def test_editing_the_document_reruns_segmentation(
    source: Path, tmp_path: Path, fake_segmenter: object
) -> None:
    out = tmp_path / "out"
    first = build(source, out, fake_segmenter).run()
    path = out / "document.json"
    document = read_artifact(Document, path)
    assert document is not None
    document.blocks.pop()
    document.write(path)

    second = build(source, out, fake_segmenter).run()
    assert "segments" not in second.reused
    assert len(second.segmented.segments) < len(first.segmented.segments)


def test_a_schema_bump_invalidates_artifacts(
    source: Path, tmp_path: Path, fake_segmenter: object
) -> None:
    out = tmp_path / "out"
    build(source, out, fake_segmenter).run()
    path = out / "segments.json"
    stale = json.loads(path.read_text(encoding="utf-8"))
    stale["schema_version"] = 0
    path.write_text(json.dumps(stale), encoding="utf-8")

    result = build(source, out, fake_segmenter).run()
    assert "segments" not in result.reused


def test_the_translation_cache_survives_a_new_output_directory(
    source: Path, tmp_path: Path, fake_segmenter: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    build(source, tmp_path / "one", fake_segmenter).run()
    elsewhere = build(source, tmp_path / "two", fake_segmenter).run()
    assert "translation (cache)" in elsewhere.reused


def test_style_is_part_of_the_cache_key(
    source: Path, tmp_path: Path, fake_segmenter: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    build(source, tmp_path / "one", fake_segmenter).run()
    other = build(source, tmp_path / "two", fake_segmenter, style=Style.direct).run()
    assert "translation (cache)" not in other.reused


def test_translation_covers_every_segment(
    source: Path, tmp_path: Path, fake_segmenter: object
) -> None:
    result = build(source, tmp_path / "out", fake_segmenter).run()
    assert set(result.translation.segments) == {s.id for s in result.segmented.segments}


def test_empty_source_says_so(tmp_path: Path, fake_segmenter: object) -> None:
    empty = tmp_path / "empty.txt"
    empty.write_text("   \n\n  \n", encoding="utf-8")
    with pytest.raises(TargumError, match="No text found"):
        build(empty, tmp_path / "out", fake_segmenter).run()


def test_default_output_directory_is_named_for_the_source(
    source: Path, tmp_path: Path, fake_segmenter: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    builder = Build(
        str(source),
        target_language="en",
        provider_name="null",
        segmenter=fake_segmenter,  # type: ignore[arg-type]
    )
    result = builder.run()
    assert result.out_dir == tmp_path / "targum-out" / "declaration-he"


def test_translation_carries_its_provenance(
    source: Path, tmp_path: Path, fake_segmenter: object
) -> None:
    out = tmp_path / "out"
    build(source, out, fake_segmenter, style=Style.direct).run()
    translation = read_artifact(Translation, out / "translations" / "null.direct.en.json")
    assert translation is not None
    assert translation.provider == "null"
    assert translation.style is Style.direct
    assert translation.kind == "machine"


def test_a_new_ingester_version_re_ingests(
    source: Path, tmp_path: Path, fake_segmenter: object
) -> None:
    """An ingester change is stale extraction, not a hand edit, so the artifact loses.

    Without this the two cases are indistinguishable by hash and every improvement to
    an ingester is invisible on documents built before it.
    """
    out = tmp_path / "out"
    build(source, out, fake_segmenter).run()

    path = out / "document.json"
    document = read_artifact(Document, path)
    assert document is not None
    document.ingester = "markdown/0"
    document.blocks[1].text = "stale extraction"
    document.content_hash = document.recompute_hash()
    document.write(path)

    result = build(source, out, fake_segmenter).run()
    assert "document (edited)" not in result.reused
    assert not any("stale extraction" in s.text for s in result.segmented.segments)


def test_a_changed_source_file_wins_over_the_artifact(
    source: Path, tmp_path: Path, fake_segmenter: object
) -> None:
    """Editing document.json is a fix. Editing the source is a different text."""
    out = tmp_path / "out"
    build(source, out, fake_segmenter).run()
    source.write_text("# אחר\n\nטקסט אחר לגמרי.\n", encoding="utf-8")

    result = build(source, out, fake_segmenter).run()
    assert "document (edited)" not in result.reused
    assert any("לגמרי" in segment.text for segment in result.segmented.segments)


# --- announcing, and opening before the meanings arrive ----------------------


class Announcements:
    """Everything the build told the caller, in order."""

    def __init__(self) -> None:
        self.said: list[str] = []

    def __call__(self, message: str) -> None:
        self.said.append(message)

    def mentions(self, word: str) -> bool:
        return any(word.lower() in message.lower() for message in self.said)


class FakeAnnotator:
    """One token per segment, so the pipeline has words without needing Stanza."""

    name = "fake/1"

    # The vocalization is offered to every annotator now, because a word's reading is
    # worked out from its vowels. This one has no use for it and says so by ignoring it.
    def annotate(
        self, segmented: SegmentedDocument, vocalization: Vocalization | None = None
    ) -> Annotation:
        return Annotation(
            document_hash=segmented.document_hash,
            language=segmented.language,
            annotator=self.name,
            method="frequency",
            method_note="made up",
            tokens={
                segment.id: [
                    Token(
                        start=0,
                        end=len(segment.text.split()[0]),
                        surface=segment.text.split()[0],
                        lemma=segment.text.split()[0],
                        band=3,
                    )
                ]
                for segment in segmented.segments
                if segment.text.split()
            },
        )


class FakeGlosses:
    """Stands in for the Anthropic lookup, and records when it was asked."""

    name = "fake-glosses/1"
    calls: list[float] = []

    def __init__(self, model: str | None = None, **_: object) -> None:
        self.model = model

    def available(self) -> tuple[bool, str]:
        return True, ""

    def gloss(
        self,
        lemmas: list[str],
        source_language: str,
        target_language: str,
        on_progress: object = None,
    ) -> dict[str, tuple[str, str]]:
        type(self).calls.append(time.time())
        return {lemma: (f"meaning of {lemma}", "noun") for lemma in lemmas}


class FailingGlosses(FakeGlosses):
    def gloss(self, *args: object, **kwargs: object) -> dict[str, tuple[str, str]]:
        raise ProviderError("The glossary provider fell over.", "try again later")


@pytest.fixture
def fake_glosses(monkeypatch: pytest.MonkeyPatch) -> type[FakeGlosses]:
    FakeGlosses.calls = []
    monkeypatch.setattr("targum.annotate.gloss.AnthropicGlosses", FakeGlosses)
    return FakeGlosses


def glossed_build(source: Path, out: Path, segmenter: object, **kwargs: object) -> Build:
    return build(
        source,
        out,
        segmenter,
        gloss=True,
        annotator=FakeAnnotator(),  # type: ignore[arg-type]
        **kwargs,
    )


def test_every_slow_stage_announces_itself(
    source: Path, tmp_path: Path, fake_segmenter: object
) -> None:
    """A stage that works in silence is indistinguishable from a hang.

    `targum serve` shows the last thing the build said, falling back to the translation
    count. Vowel points and rendering used to say nothing, so the page went on showing
    the count it had already finished with while they ran.
    """
    said = Announcements()
    build(
        source,
        tmp_path / "out",
        fake_segmenter,
        difficulty=True,
        annotator=FakeAnnotator(),  # type: ignore[arg-type]
        notify=said,
    ).run()

    assert said.mentions("dictionary form"), said.said
    assert said.mentions("vowel points"), said.said
    assert said.mentions("reader"), said.said


def test_a_reused_annotation_still_announces_the_stage(
    source: Path, tmp_path: Path, fake_segmenter: object, fake_glosses: type[FakeGlosses]
) -> None:
    """The second run is where this bit: reusing the artifact skipped the message."""
    out = tmp_path / "out"
    first = Announcements()
    glossed_build(source, out, fake_segmenter, notify=first).run()

    again = Announcements()
    result = glossed_build(source, out, fake_segmenter, notify=again).run()

    assert "difficulty" in result.reused, result.reused
    assert again.mentions("dictionary form"), again.said


def test_the_reader_exists_before_any_word_is_looked_up(
    source: Path, tmp_path: Path, fake_segmenter: object, fake_glosses: type[FakeGlosses]
) -> None:
    """The whole point: something readable, before the long part starts."""
    out = tmp_path / "out"
    seen: list[Path] = []

    def ready(result: Result) -> None:
        # Readable on disk, and the lookups have not begun.
        assert result.index.exists(), "on_ready fired before anything was written"
        assert '<main id="reader">' in result.index.read_text(encoding="utf-8")
        assert fake_glosses.calls == [], "glossing started before the reader opened"
        seen.append(result.index)

    result = glossed_build(source, out, fake_segmenter).run(on_ready=ready)

    assert seen, "on_ready never fired"
    assert fake_glosses.calls, "the glossary was never built"
    assert result.glossary is not None


def test_the_meanings_are_baked_in_afterwards(
    source: Path, tmp_path: Path, fake_segmenter: object, fake_glosses: type[FakeGlosses]
) -> None:
    """Opening the file again must not depend on a server being there to hand them over."""
    out = tmp_path / "out"
    at_open: list[str] = []
    result = glossed_build(source, out, fake_segmenter).run(
        on_ready=lambda r: at_open.append(r.index.read_text(encoding="utf-8"))
    )

    assert "meaning of" not in at_open[0]
    assert "meaning of" in result.index.read_text(encoding="utf-8")
    assert (out / "glossary.json").exists()


def test_a_failed_lookup_costs_the_meanings_not_the_reader(
    source: Path, tmp_path: Path, fake_segmenter: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Someone is already reading it. Do not take the book back."""
    monkeypatch.setattr("targum.annotate.gloss.AnthropicGlosses", FailingGlosses)
    said = Announcements()
    out = tmp_path / "out"

    result = glossed_build(source, out, fake_segmenter, notify=said).run()

    assert result.index.exists()
    assert result.glossary is None
    assert said.mentions("without word meanings"), said.said


def test_the_second_pass_leaves_no_stale_section_files(
    source: Path, tmp_path: Path, fake_segmenter: object, fake_glosses: type[FakeGlosses]
) -> None:
    """It writes over the directory rather than emptying it, so check nothing lingers."""
    out = tmp_path / "out"
    before: list[str] = []
    result = glossed_build(source, out, fake_segmenter).run(
        on_ready=lambda r: before.extend(sorted(p.name for p in r.pages))
    )
    after = sorted(path.name for path in result.pages)

    assert before == after
    assert sorted(p.name for p in (out / "reader").glob("*.html")) == after


class Dies:
    """Translates a batch, writes it down, and then falls over.

    Stands in for the ordinary way a long run ends badly: a network that drops, a laptop
    that sleeps, a rate limit at sentence four hundred.
    """

    name = "dies"
    needs_key = False
    default_model = None

    def __init__(self, size: int = 2, batches_before_dying: int = 1) -> None:
        self.size = size
        self.batches_before_dying = batches_before_dying
        self.asked: list[list[str]] = []

    def available(self) -> tuple[bool, bool | str]:
        return True, "falls over on purpose"

    def translate(  # type: ignore[no-untyped-def]
        self, segments, source_language, target_language, style, on_progress=None, on_batch=None
    ):
        from targum.errors import ProviderError

        self.asked.append([segment.id for segment in segments])
        done: dict[str, str] = {}
        for number, start in enumerate(range(0, len(segments), self.size)):
            if number >= self.batches_before_dying:
                raise ProviderError("The provider fell over.", "mid-run")
            done |= {s.id: f"[en] {s.text}" for s in segments[start : start + self.size]}
            if on_batch:
                on_batch(dict(done))
        return done


def test_an_interrupted_run_writes_down_what_it_paid_for(
    source: Path, tmp_path: Path, fake_segmenter: object
) -> None:
    """A book that died at 80% used to re-translate from zero. Every batch that came back
    had been paid for and nothing but the whole run was ever written down."""
    from targum.errors import ProviderError

    builder = build(source, tmp_path / "out", fake_segmenter)
    plan = builder.plan()
    assert plan.segmented is not None
    builder.provider = Dies()  # type: ignore[assignment]

    with pytest.raises(ProviderError):
        builder.run(plan)

    held = builder.held(builder.cache_key(plan.segmented))
    assert held, "the batch that succeeded is on the ledger"
    assert len(held) < len(plan.segmented.segments), "and only that batch"


def test_the_next_attempt_buys_only_what_is_missing(
    source: Path, tmp_path: Path, fake_segmenter: object
) -> None:
    from targum.errors import ProviderError

    first = build(source, tmp_path / "out", fake_segmenter)
    plan = first.plan()
    assert plan.segmented is not None
    first.provider = Dies()  # type: ignore[assignment]
    with pytest.raises(ProviderError):
        first.run(plan)
    paid = set(first.held(first.cache_key(plan.segmented)))

    # A second attempt, with a provider that survives, on the same cache.
    second = build(source, tmp_path / "out2", fake_segmenter)
    finishes = Dies(batches_before_dying=99)
    second.provider = finishes  # type: ignore[assignment]
    result = second.run()

    asked = set(finishes.asked[0])
    assert asked, "it still had something to do"
    assert not (asked & paid), "and never asked again for a sentence already bought"
    assert set(result.translation.segments) >= paid | asked, "the reader gets all of it"


def test_a_chapter_is_only_free_when_all_of_it_is_bought(
    source: Path, tmp_path: Path, fake_segmenter: object
) -> None:
    """`bought` used to be "is there a cache entry". Once a dying run leaves a partial
    one, an entry alone stopped meaning a chapter was paid for — and calling it free is
    how a reader gets charged for what a page told them they already had."""
    builder = build(source, tmp_path / "out", fake_segmenter)
    plan = builder.plan()
    assert plan.segmented is not None
    run = plan.segmented.segments

    assert builder.bought(plan.segmented, run) is False, "nothing bought yet"

    part = {segment.id: "x" for segment in run[:1]}
    builder.cache.put("translate", builder.cache_key(plan.segmented, run), {"segments": part})
    assert builder.bought(plan.segmented, run) is False, "a partial entry is not a purchase"

    whole = {segment.id: "x" for segment in run}
    builder.cache.put("translate", builder.cache_key(plan.segmented, run), {"segments": whole})
    assert builder.bought(plan.segmented, run) is True
