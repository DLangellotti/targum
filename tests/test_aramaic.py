"""The words of a Targum, read without a tagger (targum-internal#64).

What is pinned here is what the measurement decided: the hand table answers, the verse's
names answer, and nothing else does — a word neither knows is a word with nothing on its
card, never a guess from a dictionary that files the spelling under something else.
"""

from __future__ import annotations

import pytest

from targum.annotate import Annotator, aramaic, closed, lemma
from targum.annotate.gloss import from_the_tagging
from targum.models import Segment, SegmentedDocument, Token


def segment(text: str, ref: str = "", language: str | None = None, index: int = 0) -> Segment:
    return Segment(
        id=f"{index:04d}.000-aaaaaa",
        block_id=f"b{index:04d}",
        block_index=index,
        index=0,
        text=text,
        ref=ref,
        language=language,
    )


class Refuses:
    """A fallback that must never be handed a word of Aramaic."""

    name = "refuses/1"

    def __init__(self) -> None:
        self.asked: list[tuple[list[str], str]] = []

    def lemmas(self, segments, language):  # type: ignore[no-untyped-def]
        self.asked.append(([s.text for s in segments], language))
        return {s.id: [] for s in segments}


class Unrated:
    name = "unrated/1"
    method = "frequency"
    note = ""

    def supports(self, language: str) -> bool:
        return False

    def band(self, lemma: str, language: str) -> int:
        return 0


# -- the table ---------------------------------------------------------------------


def test_every_headword_in_the_table_says_what_it_means() -> None:
    headwords = set(closed.TARGUM.values())
    assert headwords <= set(closed.TARGUM_GLOSSES), headwords - set(closed.TARGUM_GLOSSES)
    assert set(closed.TARGUM_GLOSSES) <= headwords, "a gloss nothing is filed under"
    assert all(closed.TARGUM_GLOSSES.values())


def test_no_two_spellings_of_a_form_are_filed_under_different_words() -> None:
    """The table is keyed by the form as written and looked up folded, so a form written
    with a final letter and without one must not disagree."""
    seen: dict[str, str] = {}
    for form, headword in closed.TARGUM.items():
        folded = aramaic.key(form)
        assert seen.setdefault(folded, headword) == headword, form


def test_the_commonest_words_of_onkelos_are_the_ones_a_dictionary_got_wrong() -> None:
    """The four Jastrow answered by spelling as "being, existence", "strong cord",
    "palm-tree" and "bride" (targum-internal#64)."""
    said = {form: aramaic.sense(f"{aramaic.HAND}{closed.TARGUM[form]}") for form in closed.TARGUM}
    assert said["ית"] == "[marks the direct object]"
    assert said["יי"] == "the LORD [the divine name]"
    assert said["די"].startswith("which")
    assert said["כל"].startswith("all")


# -- looking a word up -------------------------------------------------------------


def test_prefixes_come_off_the_front() -> None:
    found = aramaic.look_up("וְיָת")
    assert found == aramaic.Found("יָת", "ו")
    assert aramaic.look_up("דַיְיָ") == aramaic.Found("יְיָ", "ד")
    assert aramaic.look_up("וּבְאַרְעָא") == aramaic.Found("אַרְעָא", "וב")


def test_a_form_the_table_holds_whole_is_not_taken_apart() -> None:
    """`ביתה` is his house. Taken apart it is ב + the object marker, and `כדין`, "thus",
    is כ + "this" — both found by reading every form the table matched only after a letter
    came off."""
    assert aramaic.look_up("בֵּיתֵיהּ") != aramaic.Found("יָת", "ב")
    assert aramaic.look_up("ביתה") == aramaic.Found("בֵּית")
    assert aramaic.look_up("כדין") == aramaic.Found("כְּדֵין")


def test_a_name_of_the_verse_wins_over_a_word_found_by_taking_a_letter_off() -> None:
    """`מדין` is Midian where the verse names Midian — and מ + "this" nowhere."""
    assert aramaic.look_up("מדין", frozenset({aramaic.key("מִדְיָן")})).name
    assert aramaic.look_up("מדין") == aramaic.Found("דֵּין", "מ")
    assert aramaic.look_up("לְאַבְרָם", frozenset({"אברמ"})) == aramaic.Found("", "ל", name=True)


def test_a_word_nothing_knows_is_left_unanswered() -> None:
    assert aramaic.look_up("וְרֵיקַנְיָא") is None
    assert aramaic.look_up("") is None
    assert aramaic.look_up("׃") is None


def test_the_verse_s_names_come_from_the_hebrew_it_translates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from targum.annotate import oshb

    asked: list[str] = []

    def words(ref: str) -> tuple[oshb.Word, ...]:
        asked.append(ref)
        return (
            oshb.Word("וַיֹּאמֶר", ("וַ", "יֹּאמֶר"), ("c", "559"), ("C", "Vqw3ms")),
            oshb.Word("אַבְרָם", ("אַבְרָם",), ("87",), ("Np",)),
        )

    monkeypatch.setattr(oshb, "available", lambda: True)
    monkeypatch.setattr(oshb, "words", words)
    assert aramaic.verse_names("Onkelos Genesis 12:1") == frozenset({"אברמ"})
    assert asked == ["Genesis 12:1"]
    assert aramaic.verse_names("Genesis 12:1") == frozenset(), "the Hebrew itself is not a Targum"


def test_no_tagging_on_disk_means_no_names_rather_than_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from targum.annotate import oshb

    monkeypatch.setattr(oshb, "available", lambda: False)
    assert aramaic.verse_names("Onkelos Genesis 12:1") == frozenset()


# -- tokens ------------------------------------------------------------------------


def test_every_word_is_a_token_and_only_known_words_carry_a_meaning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(aramaic, "verse_names", lambda ref: frozenset({"אברמ"}))
    text = "וַאֲמַר יְיָ לְאַבְרָם וְרֵיקַנְיָא׃"
    tokens = aramaic.tokens(segment(text, "Onkelos Genesis 12:1"))
    bare = aramaic.bare(text)
    assert [bare[t.start : t.end] for t in tokens] == ["ואמר", "יי", "לאברם", "וריקניא"]

    said, name, divine, unknown = tokens[0], tokens[2], tokens[1], tokens[3]
    assert (said.lemma, said.headword, said.lexeme) == ("אמר", "אֲמַר", "targum:אֲמַר")
    assert said.split and said.built == "ו + אמר"
    assert divine.lexeme == "targum:יְיָ" and not divine.split and divine.built is None
    assert (name.pos, name.lemma, name.built, name.lexeme) == ("PROPN", "אברם", "ל + אברם", None)
    assert (unknown.lemma, unknown.headword, unknown.lexeme, unknown.pos) == (
        "וריקניא",
        None,
        None,
        None,
    )
    assert all(t.band == 0 and t.root is None and t.binyan is None for t in tokens)


def test_a_known_word_s_meaning_is_free() -> None:
    """The table is a sense as well as a headword, so an English reader of Onkelos needs
    no model call for the words it holds."""
    annotation_tokens = aramaic.tokens(segment("וְיָת אַרְעָא"))
    from targum.models import Annotation

    annotation = Annotation(
        document_hash="h",
        language="arc",
        annotator="aramaic/1",
        method="none",
        method_note="",
        tokens={"0000.000-aaaaaa": annotation_tokens},
    )
    found = from_the_tagging(annotation)
    assert found["יָת"].gloss == "[marks the direct object]"
    assert found["אַרְעָא"].gloss == "land; earth; ground"


# -- the lemmatizer ----------------------------------------------------------------


def test_aramaic_is_read_here_and_everything_else_by_what_it_wraps() -> None:
    fallback = Refuses()
    reader = aramaic.AramaicLemmatizer(fallback)
    hebrew = segment("בראשית ברא", index=0)
    targum = segment("בְּקַדְמִין בְּרָא יְיָ", language="arc", index=1)
    out = reader.lemmas([hebrew, targum], "he")
    assert fallback.asked == [(["בראשית ברא"], "he")]
    assert [t.lexeme for t in out[targum.id]][-1] == "targum:יְיָ"

    fallback.asked.clear()
    whole = reader.lemmas([segment("יָת שְׁמַיָּא", index=2)], "arc")
    assert fallback.asked == [], "a document in Aramaic hands its words to nobody"
    assert [t.headword for t in next(iter(whole.values()))] == ["יָת", "שְׁמַיָּא"]


def test_it_reads_an_aramaic_block_and_asks_what_it_wraps_about_the_rest() -> None:
    class ReadsDaniel(Refuses):
        def reads(self, segment: Segment) -> bool:
            return segment.ref == "Daniel 2:4"

    reader = aramaic.AramaicLemmatizer(ReadsDaniel())
    assert reader.reads(segment("יָת", language="arc"))
    assert not reader.reads(segment("בראשית"))
    assert reader.name == "aramaic/1+refuses/1"


def test_a_document_in_aramaic_is_annotated_rather_than_refused() -> None:
    """Onkelos as a text of its own. Before this, no word of it could be read and the
    build said so; now its words are answered where they are known and left plain where
    they are not, with no band claimed for any of them."""
    onkelos = SegmentedDocument(
        document_hash="h",
        language="arc",
        segmenter="t/1",
        segments=[segment("בְּקַדְמִין בְּרָא יְיָ יָת שְׁמַיָּא וְיָת אַרְעָא׃")],
    )
    annotation = Annotator(
        lemmatizer=aramaic.AramaicLemmatizer(Refuses()), bands=Unrated()
    ).annotate(onkelos)
    words = next(iter(annotation.tokens.values()))
    assert [w.surface for w in words][-3:] == ["שְׁמַיָּא", "וְיָת", "אַרְעָא"]
    assert annotation.method == "none"
    assert {w.band for w in words} == {0}


# -- wrapping, and what it must not rename ------------------------------------------


def test_only_a_text_written_in_aramaic_is_wrapped() -> None:
    class Plain:
        name = "plain/1"

        def lemmas(self, segments, language):  # type: ignore[no-untyped-def]
            return {}

    base = Plain()
    assert lemma.for_language(base, "he") is base
    assert lemma.for_language(base, None) is base
    wrapped = lemma.for_language(base, "arc")
    assert isinstance(wrapped, aramaic.AramaicLemmatizer)
    assert lemma.for_language(wrapped, "arc") is wrapped, "wrapped once, not twice"


def test_no_hebrew_text_on_the_shelf_changes_its_annotator_name() -> None:
    """The annotator's name is the cache key, and on the box a rename is a two-hour
    re-annotation (CLAUDE.md). Aramaic is wrapped by language, so a Hebrew text — Daniel
    and Ezra included, which carry Aramaic blocks — is named exactly as it was."""
    for source in ("sefaria:Genesis", "sefaria:Daniel", "wikisource:he:x", "memory"):
        before = lemma.for_source(source, auto_download=False).name
        assert lemma.for_source(source, auto_download=False, language="he").name == before
    assert lemma.for_source(
        "sefaria:arc:Genesis", auto_download=False, language="arc"
    ).name.startswith("aramaic/1+")


def test_a_token_is_what_the_reader_already_knows_how_to_draw() -> None:
    """No new field: headword, lexeme, split and built are the scripture path's, so the
    card needs nothing to show an Aramaic word."""
    fields = set(Token.model_fields)
    assert {"headword", "lexeme", "split", "built", "pos"} <= fields
