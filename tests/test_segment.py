from __future__ import annotations

import pytest

from targum.ids import segment_id
from targum.models import BlockKind, Document, SegmentedDocument
from targum.segment import segment_document, stanza_code


def test_headings_are_never_split(document: Document, fake_segmenter: object) -> None:
    segmented = segment_document(document, fake_segmenter)  # type: ignore[arg-type]
    headings = [s for s in segmented.segments if s.kind is BlockKind.heading]
    assert len(headings) == 1
    assert headings[0].text == "הכרזה על הקמת מדינת ישראל"


def test_splits_paragraphs_into_sentences(segmented: SegmentedDocument) -> None:
    from_block_one = [s for s in segmented.segments if s.block_index == 1]
    assert len(from_block_one) == 2
    assert [s.index for s in from_block_one] == [0, 1]


def test_ids_are_stable_across_runs(document: Document, fake_segmenter: object) -> None:
    first = segment_document(document, fake_segmenter)  # type: ignore[arg-type]
    second = segment_document(document, fake_segmenter)  # type: ignore[arg-type]
    assert [s.id for s in first.segments] == [s.id for s in second.segments]


def test_id_changes_when_the_text_changes() -> None:
    # An edit upstream must not silently rebind a translation to different words.
    assert segment_id(1, 0, "one text") != segment_id(1, 0, "another text")
    assert segment_id(1, 0, "same") != segment_id(2, 0, "same")


def test_ids_are_unique(segmented: SegmentedDocument) -> None:
    ids = [s.id for s in segmented.segments]
    assert len(ids) == len(set(ids))


def test_carries_the_document_hash(document: Document, segmented: SegmentedDocument) -> None:
    assert segmented.document_hash == document.content_hash


@pytest.mark.parametrize(("given", "expected"), [("he", "he"), ("he-IL", "he"), ("iw", "he")])
def test_language_tags_map_onto_stanza_codes(given: str, expected: str) -> None:
    assert stanza_code(given) == expected


def _hebrew(text: str) -> Document:
    from targum.ids import content_hash
    from targum.models import Block

    return Document(
        source="memory",
        language="he",
        blocks=[Block(id="b0000", text=text)],
        content_hash=content_hash(text),
    )


def _sentences(text: str) -> list[str]:
    from targum.segment import HebrewSegmenter

    return [s.text for s in segment_document(_hebrew(text), HebrewSegmenter()).segments]


def test_hebrew_abbreviations_do_not_split() -> None:
    # Gershayim (״) and geresh (׳) look like quote marks and are not, and the ASCII
    # quote and apostrophe stand in for them in most of what is on the shelf.
    text = "בשנת תרנ״ז (1897) נתכנס הקונגרס. ד״ר אברהם גרנובסקי חתם ביום ה׳ אייר תש״ח."
    assert _sentences(text) == [
        "בשנת תרנ״ז (1897) נתכנס הקונגרס.",
        "ד״ר אברהם גרנובסקי חתם ביום ה׳ אייר תש״ח.",
    ]
    assert _sentences('ד"ר כהן כתב במה"ע וכו\'. הלך.') == ['ד"ר כהן כתב במה"ע וכו\'.', "הלך."]


def test_an_exclamation_ends_a_sentence() -> None:
    """Stanza's Hebrew tokenizer never once split on one: 2,100 exclamation marks sat
    mid-segment on the 47 readers, each ahead of the sentence that followed it."""
    assert _sentences("גזלן! למה אינך עושה כלום? כן.") == ["גזלן!", "למה אינך עושה כלום?", "כן."]
    assert _sentences("שקר!! והוא יכול?! זה!… כן") == ["שקר!!", "והוא יכול?!", "זה!…", "כן"]


def test_a_quoted_sentence_stays_inside_the_one_that_quotes_it() -> None:
    """`"מה אתה רוצה?" שאל.` is one thing said and who said it; the tag alone translates
    to a fragment. A full stop after the closing quote is bare and ends it."""
    assert _sentences('"מה אתה רוצה?" שאל. "כלום!" ענתה. "קורס". חדש') == [
        '"מה אתה רוצה?" שאל.',
        '"כלום!" ענתה.',
        '"קורס".',
        "חדש",
    ]
    assert _sentences("(מה יש?) אמר. (כן!) סוף.") == ["(מה יש?) אמר.", "(כן!) סוף."]


def test_a_dash_after_the_mark_keeps_the_speech_tag_with_its_speech() -> None:
    """Ben-Yehuda's dialogue: `– מה יש? – שאל הוא עברית.` Stanza cut at the question
    mark, and the English reader carried "he asked in Hebrew." as a segment of its own."""
    assert _sentences("– מה יש? – שאל הוא עברית. הוא ענה.") == [
        "– מה יש? – שאל הוא עברית.",
        "הוא ענה.",
    ]
    # A dash that opens a word rather than standing alone is not a tag.
    assert _sentences("הלך. -ה נשאר.") == ["הלך.", "-ה נשאר."]


def test_an_ellipsis_is_a_pause_unless_a_new_speaker_follows() -> None:
    assert _sentences("כן… אתה בא? הלכתי… ושם נשארתי.") == ["כן… אתה בא?", "הלכתי… ושם נשארתי."]
    assert _sentences('הלכתי… – ומה? אמר... "בוא"') == ["הלכתי…", "– ומה?", "אמר...", '"בוא"']


def test_an_initial_does_not_end_a_sentence() -> None:
    assert _sentences("ושם N. O. Body ישב. נ.ב. שלום.") == ["ושם N. O. Body ישב.", "נ.ב. שלום."]
    assert _sentences("א. הלך. ב. בא.") == ["א. הלך.", "ב. בא."], "at the start of the text too"


def test_a_gershayim_inside_a_word_is_not_a_quote_before_an_initial() -> None:
    """`חו"ל.` ended nothing at first: the ASCII quote was read as an opening quote and the
    ל as an initial. Thirty-three boundaries on four readers were silently un-drawn."""
    assert _sentences('הוא נסע לחו"ל. למחרת חזר.') == ['הוא נסע לחו"ל.', "למחרת חזר."]
    assert _sentences("הוא בן 5. הוא גדול.") == ["הוא בן 5.", "הוא גדול."], (
        "a digit is not an initial"
    )


def test_a_dash_the_block_ends_on_stays_where_it_is() -> None:
    assert _sentences("מה? –") == ["מה? –"], "never a one-character segment"
    assert _sentences("מה? – – – כן.") == ["מה?", "– – – כן."], "three dashes are a section break"


def test_a_closer_between_two_marks_leaves_the_last_one_bare() -> None:
    assert _sentences('הוא אמר "לא.". ואז הלך.') == ['הוא אמר "לא.".', "ואז הלך."]


def test_invisible_marks_after_a_full_stop_are_looked_through() -> None:
    """Pasted Wikipedia and Wikisource text carries a right-to-left mark after nearly
    every full stop, and ingest normalises to NFC and nothing else."""
    for mark in ("\u200f", "\u200e", "\u200b", "\u2069"):
        assert _sentences(f"שלום.{mark} בוקר טוב.") == [f"שלום.{mark}", "בוקר טוב."], repr(mark)


def test_sof_pasuk_ends_a_sentence_in_prose() -> None:
    assert _sentences("בראשית ברא׃ והארץ היתה׃") == ["בראשית ברא׃", "והארץ היתה׃"]


def test_a_mark_inside_something_ends_nothing() -> None:
    assert _sentences("פאי הוא 3.14 בערך. כן.") == ["פאי הוא 3.14 בערך.", "כן."]
    assert _sentences('מה?"בוא" אמר.') == ['מה?"בוא" אמר.']


@pytest.mark.parametrize(
    ("text", "expected"),
    [("", []), ("   ", []), ("רק שלום", ["רק שלום"]), ("…", ["…"]), (". . .", [".", ".", "."])],
)
def test_sentences_on_the_edges(text: str, expected: list[str]) -> None:
    from targum.segment.hebrew import sentences

    assert sentences(text) == expected


def test_a_block_of_any_size_splits_in_linear_time() -> None:
    """A reader can upload a single block of a megabyte, or a line of ten thousand dots,
    and the build queue is one worker: the first version was quadratic in the block and
    cubic in a run of marks, and a crafted paragraph would have parked every build."""
    import time

    from targum.segment.hebrew import sentences

    started = time.perf_counter()
    assert sentences("." * 20_000 + "x") == ["." * 20_000 + "x"]
    assert len(sentences("א. " * 20_000)) == 1
    assert len(sentences("הוא הלך. " * 50_000)) == 50_000
    assert time.perf_counter() - started < 2.0


def test_nothing_is_dropped_and_nothing_is_reordered() -> None:
    text = "  אחת. שתיים!  שלוש?   ארבע…  "
    pieces = _sentences(text)
    assert pieces == ["אחת.", "שתיים!", "שלוש?", "ארבע…"]
    assert "".join(text.split()) == "".join("".join(piece.split()) for piece in pieces)


def test_hebrew_never_reaches_a_stanza_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pin for targum-internal#146: Stanza's Hebrew models are trained on a
    NonCommercial treebank, and after the annotator swap the sentence splitter was the
    one place a Hebrew text still went through them."""
    import stanza

    from targum.errors import TargumError
    from targum.segment import HebrewSegmenter, StanzaSegmenter

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("Stanza was built for a Hebrew text")

    monkeypatch.setattr(stanza, "Pipeline", refuse)
    monkeypatch.setattr(stanza, "download", refuse)

    segmented = segment_document(_hebrew("קם העם. בה עוצבה דמותו."), HebrewSegmenter())
    assert len(segmented.segments) == 2
    assert segmented.segmenter.startswith("hebrew-rules/")
    assert "+stanza/" in segmented.segmenter, "the delegate is named, as the annotator's is"

    with pytest.raises(TargumError, match="NonCommercial"):
        StanzaSegmenter().pipeline("he")


def test_the_delegate_is_told_not_to_download(monkeypatch: pytest.MonkeyPatch) -> None:
    import stanza

    from targum.errors import ModelMissing
    from targum.segment import HebrewSegmenter, stanza_segmenter

    monkeypatch.setattr(stanza_segmenter, "is_downloaded", lambda *args, **kwargs: False)
    monkeypatch.setattr(stanza, "download", lambda *args, **kwargs: pytest.fail("downloaded"))
    with pytest.raises(ModelMissing, match="not downloaded"):
        HebrewSegmenter(auto_download=False).split(["Один. Два."], "ru")


def test_the_name_carries_the_installed_stanza_version(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.metadata as metadata

    from targum.segment import stanza_segmenter

    monkeypatch.setattr(metadata, "version", lambda name: "9.9.9")
    assert stanza_segmenter.StanzaSegmenter().name == "stanza/9.9.9"

    def missing(name: str) -> str:
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(metadata, "version", missing)
    assert stanza_segmenter.StanzaSegmenter().name == "stanza/unknown"


def test_other_languages_still_go_to_the_delegate() -> None:
    from targum.segment import HebrewSegmenter

    class Counting:
        name = "fake/1"

        def __init__(self) -> None:
            self.asked: list[str] = []

        def split(self, texts: list[str], language: str) -> list[list[str]]:
            self.asked.append(language)
            return [[text] for text in texts]

    delegate = Counting()
    segmenter = HebrewSegmenter(other=delegate)
    assert segmenter.split(["One. Two."], "en") == [["One. Two."]]
    assert segmenter.split(["אחת. שתיים."], "he-IL") == [["אחת.", "שתיים."]]
    assert delegate.asked == ["en"]
    assert segmenter.name == "hebrew-rules/1+fake/1"


def test_a_model_download_says_what_it_is_waiting_for(monkeypatch: pytest.MonkeyPatch) -> None:
    """A first build on a fresh box stops for minutes while Stanza fetches a few hundred
    megabytes, and until this the page held whatever line it printed before — "Finding
    each word's dictionary form…" — for the whole of it. A line that has not moved in
    four minutes reads as a hang (targum-internal #91, UX review C1).
    """
    import stanza

    from targum.segment import stanza_segmenter

    monkeypatch.setattr(stanza, "download", lambda *args, **kwargs: None)
    said: list[str] = []

    with stanza_segmenter.telling(said.append):
        stanza_segmenter.download("he")

    assert said == ["Fetching the Hebrew language model. This happens once."], (
        "it names the language, and that the wait happens once"
    )


def test_a_model_download_is_silent_when_nobody_is_listening(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI shows Stanza's own progress and needs no line from us, so the announcement
    is something a caller opts into rather than something every path pays for."""
    import stanza

    from targum.segment import stanza_segmenter

    monkeypatch.setattr(stanza, "download", lambda *args, **kwargs: None)
    stanza_segmenter.download("he")  # no telling(), no error, nothing said


def test_the_listener_does_not_outlive_its_block(monkeypatch: pytest.MonkeyPatch) -> None:
    """One reader's progress line has no business arriving in another reader's build."""
    import stanza

    from targum.segment import stanza_segmenter

    monkeypatch.setattr(stanza, "download", lambda *args, **kwargs: None)
    said: list[str] = []

    with stanza_segmenter.telling(said.append):
        stanza_segmenter.download("he")
    stanza_segmenter.download("he")

    assert len(said) == 1, "the second download was outside the block and said nothing"
