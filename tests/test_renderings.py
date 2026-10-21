"""What a rendering beside the text is (targum-internal#414)."""

from __future__ import annotations

from pathlib import Path

from targum.models import Annotation, Segment, SegmentedDocument, Token, Translation
from targum.renderings import (
    as_segmented,
    commentary_ref,
    companion_key,
    rendering_hash,
    with_commentaries,
    words_in,
    words_key,
    words_path,
)

BESIDE = frozenset({"arc"})


def _translation(name: str, into: str, segments: dict[str, str]) -> Translation:
    return Translation(
        name=name,
        document_hash="h",
        source_language="he",
        target_language=into,
        provider="null",
        segments=segments,
    )


def _segmented() -> SegmentedDocument:
    return SegmentedDocument(
        document_hash="h",
        language="he",
        segmenter="test/1",
        segments=[
            Segment(id=f"s{n}", block_id="b", block_index=0, index=n, text=f"פסוק {n}")
            for n in range(3)
        ],
    )


def test_a_commentary_is_named_by_its_reference_on_both_sides() -> None:
    """Sefaria titles Rashi's Hebrew in Hebrew, so the name a build gives a rendering
    would not say it is a commentary; the source does, the same in both languages."""
    assert commentary_ref("sefaria:Rashi on Genesis") == "Rashi on Genesis"
    assert commentary_ref("sefaria:he:Rashi on Genesis") == "Rashi on Genesis"
    assert commentary_ref("sefaria:en:Rashi_on_Genesis") == "Rashi on Genesis"
    assert commentary_ref("sefaria:en:Genesis") == ""
    assert commentary_ref("published:ru:Genesis") == ""


def test_a_companion_is_kept_under_the_same_key_on_every_text() -> None:
    onkelos = _translation("Targum Onkelos", "arc", {})
    rashi = _translation("Rashi on Genesis", "he", {})
    rashi_en = _translation("Rashi on Exodus", "en", {})
    english = _translation("Metsudah", "en", {})
    assert companion_key(onkelos, "he", BESIDE) == "targum"
    assert companion_key(rashi, "he", BESIDE) == "rashi"
    assert companion_key(rashi_en, "he", BESIDE) == "rashi-en"
    assert companion_key(english, "he", BESIDE) == ""


def test_rashis_words_are_read_from_his_text_and_found_again_only_for_that_text(
    tmp_path: Path,
) -> None:
    rashi = _translation("Rashi on Genesis", "he", {"s0": "פירוש", "s1": "—", "s2": "עוד"})
    text = as_segmented(rashi, _segmented())
    assert [s.id for s in text.segments] == ["s0", "s2"], "an unremarked verse is not read"
    assert text.segments[0].text == "פירוש"

    words = Annotation(
        document_hash=rendering_hash(rashi),
        language="he",
        annotator="test/1",
        method="frequency",
        method_note="",
        tokens={"s0": [Token(start=0, end=5, surface="פירוש", lemma="פירוש", band=3)]},
    )
    words.write(words_path(tmp_path, rashi))
    assert words_key(rashi) in words_in(tmp_path, [rashi])

    edited = rashi.model_copy(update={"segments": {**rashi.segments, "s0": "פירוש אחר"}})
    assert words_in(tmp_path, [edited]) == {}, "another edition's words are not this one's"


def test_rashis_words_join_the_texts_for_the_meanings_only_on_a_whole_build() -> None:
    def annotation(sid: str) -> Annotation:
        return Annotation(
            document_hash="h",
            language="he",
            annotator="test/1",
            method="frequency",
            method_note="",
            tokens={sid: [Token(start=0, end=1, surface="א", lemma="א", band=1)]},
        )

    text, rashi = annotation("s0"), annotation("s0")
    merged = with_commentaries(text, {"Rashi on Genesis|he": rashi})
    assert merged is not None
    assert set(merged.tokens) == {"s0", "s0|Rashi on Genesis|he"}
    assert set(text.tokens) == {"s0"}, "the text's own annotation is not changed"
    assert with_commentaries(text, {"k": rashi}, only=[]) is text
