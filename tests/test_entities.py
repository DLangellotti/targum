"""A name is what the NER says, not what PROPN says (targum-internal#149).

DICTA's `dictabert-joint` runs a named-entity head on every call, and the annotator threw
its answer away and asked the part of speech instead — which tags רבי PROPN 57% of the
time and the setumah ס every time. These pin the four things the card asks for: a person
or a place the NER named is not vocabulary and not counted; a title keeps its meaning; a
date is said to be one; and a name of several words is one chip.

No model is loaded: `_tokens` is handed what DICTA returns, in DICTA's own shape.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from targum.annotate import UNRATED, Annotator
from targum.annotate.base import (
    LABEL_COLUMN,
    chips,
    kind_of,
    not_vocabulary,
)
from targum.annotate.dicta import FEATURES, MODEL, OUTSIDE, DictaLemmatizer, _tokens
from targum.annotate.gloss import unique_lemmas
from targum.models import (
    Annotation,
    Document,
    Glossary,
    Segment,
    SegmentedDocument,
    Token,
    Translation,
)

# "דוד בן־גוריון, רבי ס בירושלים ביום שני" as DICTA reads it: the index of every word,
# punctuation included, is what an entity's `token_start` and `token_end` count.
WORDS: list[tuple[str, str, str]] = [
    ("דוד", "PROPN", "דוד"),
    ("בן", "NOUN", "בן"),
    ("־", "PUNCT", "־"),
    ("גוריון", "PROPN", "גוריון"),
    (",", "PUNCT", ","),
    ("רבי", "PROPN", "רבי"),
    ("ס", "PROPN", "ס"),
    ("בירושלים", "PROPN", "ירושלים"),
    ("ביום", "NOUN", "יום"),
    ("שני", "ADJ", "שני"),
]
TEXT = "דוד בן־גוריון, רבי ס בירושלים ביום שני"


def said() -> dict[str, Any]:
    tokens, at = [], 0
    for surface, pos, lex in WORDS:
        start = TEXT.index(surface, at)
        at = start + len(surface)
        tokens.append(
            {
                "token": surface,
                "offsets": {"start": start, "end": at},
                "seg": [surface],
                "lex": lex,
                "morph": {"pos": pos, "feats": {}, "suffix": False},
            }
        )
    return {
        "text": TEXT,
        "tokens": tokens,
        "ner_entities": [
            {"label": "PER", "token_start": 0, "token_end": 3},
            {"label": "TTL", "token_start": 5, "token_end": 5},
            {"label": "GPE", "token_start": 7, "token_end": 7},
            {"label": "TIMEX", "token_start": 8, "token_end": 9},
        ],
    }


def test_every_word_carries_what_the_ner_said_of_it() -> None:
    read = _tokens(said())
    assert [(token.surface, token.entity) for token in read] == [
        ("דוד", "B-PER"),
        # A NOUN inside a person's name is part of the name: בן here is not "son".
        ("בן", "I-PER"),
        # The maqaf is skipped, and the word after it still continues the name.
        ("גוריון", "I-PER"),
        ("רבי", "B-TTL"),
        # A PROPN the NER placed in no entity says so, so the tag cannot speak for it.
        ("ס", OUTSIDE),
        ("בירושלים", "B-GPE"),
        ("ביום", "B-TIMEX"),
        ("שני", "I-TIMEX"),
    ]


def test_a_reply_with_no_entities_leaves_the_tag_to_decide_nothing() -> None:
    """An answer without the head's output is still read; only a PROPN is marked."""
    bare = said()
    del bare["ner_entities"]
    read = _tokens(bare)
    assert {token.entity for token in read if token.pos == "PROPN"} == {OUTSIDE}
    assert all(token.entity is None for token in read if token.pos != "PROPN")


def test_the_annotator_is_renamed_once_and_keeps_the_model_it_had() -> None:
    """The rename is what re-reads the library, and the only thing that does: the
    weights are the same `dictabert-joint`, whose NER head was always running."""
    assert MODEL == "dicta-il/dictabert-joint"
    assert "entities" in FEATURES and "+names+" not in FEATURES
    assert FEATURES in DictaLemmatizer(other=_Other()).name


class _Other:
    name = "other/1"


def test_a_person_and_a_place_are_names_and_a_title_and_a_date_are_words() -> None:
    by = {token.surface: token for token in _tokens(said())}
    assert not_vocabulary(by["דוד"].pos, by["דוד"].entity)
    assert not_vocabulary(by["בן"].pos, by["בן"].entity), "בן of בן־גוריון is his name"
    assert not_vocabulary(by["בירושלים"].pos, by["בירושלים"].entity)
    assert not not_vocabulary(by["רבי"].pos, by["רבי"].entity), "a title is a word"
    assert not not_vocabulary(by["ס"].pos, by["ס"].entity), "the NER overrules PROPN"
    assert not not_vocabulary(by["ביום"].pos, by["ביום"].entity), "a date's words are words"
    assert not_vocabulary("NUM", "B-TIMEX"), "a number is still a number"
    # LOC is where DICTA files אירופה and the Negev: a place, as GPE is.
    assert not_vocabulary("PROPN", "B-LOC")
    # Everywhere the NER did not read, the tag still answers, as it always did.
    assert not_vocabulary("PROPN", None) and not not_vocabulary("NOUN", None)
    assert [kind_of(token.pos, token.entity) for token in _tokens(said())] == [
        1,
        1,
        1,
        0,
        0,
        1,
        0,
        0,
    ]


def test_a_name_has_no_band_and_a_title_has_one() -> None:
    """Through the annotator itself, so the rule reaches the band a word is stored with."""

    class Reads:
        name = "dicta-fake/1"

        def lemmas(self, segments, language):  # type: ignore[no-untyped-def]
            return {segment.id: _tokens(said()) for segment in segments}

    class Bands:
        name = "bands/1"
        method = "curated:test"
        note = ""

        def supports(self, language: str) -> bool:
            return True

        def band(self, lemma: str, language: str) -> int:
            return 5

    document = SegmentedDocument(
        document_hash="h",
        language="he",
        segmenter="t",
        segments=[Segment(id="s", block_id="b", block_index=0, index=0, text=TEXT)],
    )
    annotation = Annotator(lemmatizer=Reads(), bands=Bands()).annotate(document)
    band = {token.surface: token.band for token in annotation.tokens["s"]}
    assert band["דוד"] == band["בן"] == band["בירושלים"] == UNRATED
    assert band["רבי"] == band["ס"] == band["ביום"] == 5


def test_a_name_is_not_bought_a_meaning_and_the_same_spelling_as_a_word_is() -> None:
    """דוד the name is not glossed; דוד the uncle, elsewhere in the text, still is."""
    uncle = Token(start=0, end=3, surface="דוד", lemma="דוד", band=3, pos="NOUN")
    annotation = Annotation(
        document_hash="h",
        language="he",
        annotator="t",
        method="frequency",
        method_note="",
        tokens={"s": _tokens(said())},
    )
    wanted = unique_lemmas(annotation)
    assert "דוד" not in wanted and "ירושלים" not in wanted and "בן" not in wanted
    assert {"רבי", "יום", "ס"} <= set(wanted)
    annotation.tokens["t"] = [uncle]
    assert "דוד" in unique_lemmas(annotation)


def test_the_lemma_count_leaves_out_what_the_ner_named(tmp_path: Path) -> None:
    from targum.coverage import lemmas

    tokens = [
        {"lemma": "דוד", "pos": "PROPN", "entity": "B-PER"},
        {"lemma": "רבי", "pos": "PROPN", "entity": "B-TTL"},
        {"lemma": "ס", "pos": "PROPN", "entity": "O"},
        {"lemma": "אסתר", "pos": "PROPN"},
    ]
    (tmp_path / "annotation.json").write_text(json.dumps({"tokens": {"s": tokens}}))
    assert lemmas(tmp_path) == ["ס", "רבי"]


def test_a_name_of_several_words_is_one_chip() -> None:
    drawn = chips(_tokens(said()))
    assert [token.surface for token in drawn] == [
        "דוד בן גוריון",
        "רבי",
        "ס",
        "בירושלים",
        # A date is two words, each with a meaning: never merged.
        "ביום",
        "שני",
    ]
    whole = drawn[0]
    assert (whole.start, whole.end) == (0, TEXT.index(","))
    assert whole.lemma == "דוד בן גוריון" and whole.entity == "B-PER"


def test_two_names_side_by_side_stay_two() -> None:
    def token(at: int, word: str, entity: str) -> Token:
        return Token(start=at, end=at + len(word), surface=word, lemma=word, band=0, entity=entity)

    # "דוד ושאול" as two people: the second opens with B-, so it is a name of its own.
    drawn = chips([token(0, "דוד", "B-PER"), token(4, "שאול", "B-PER")])
    assert [one.surface for one in drawn] == ["דוד", "שאול"]
    # And a continuation with nothing to continue is a chip of its own, not lost.
    drawn = chips([token(0, "רבי", "B-TTL"), token(4, "יהודה", "I-PER")])
    assert [one.surface for one in drawn] == ["רבי", "יהודה"]


def test_the_page_carries_one_row_for_the_name_and_says_what_each_entity_is(
    tmp_path: Path,
) -> None:
    from targum.render import render

    segment = Segment(id="0000.000-aaaaaa", block_id="b0000", block_index=0, index=0, text=TEXT)
    document = Document(source="m", title="T", language="he", blocks=[], content_hash="h")
    segmented = SegmentedDocument(
        document_hash="h", language="he", segmenter="t", segments=[segment]
    )
    translation = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
        segments={segment.id: "David Ben-Gurion, Rabbi, in Jerusalem on Monday"},
    )
    annotation = Annotation(
        document_hash="h",
        language="he",
        annotator="t",
        method="frequency",
        method_note="",
        tokens={segment.id: _tokens(said())},
    )
    glossary = Glossary(
        source_language="he", target_language="en", provider="p", entries={"רבי": "rabbi"}
    )
    html = render(
        document,
        segmented,
        [translation],
        tmp_path / "r",
        annotation=annotation,
        glossaries={"en": glossary},
    )[0].read_text(encoding="utf-8")
    found = re.search(r'id="targum-data"[^>]*>(.*?)</script>', html, re.S)
    assert found
    data = json.loads(found.group(1))
    rows = data["words"][segment.id]
    lemmas = data["lemmas"]
    assert [lemmas[row[4]] for row in rows] == [
        "דוד בן גוריון",
        "רבי",
        "ס",
        "ירושלים",
        "יום",
        "שני",
    ]
    assert [row[6] for row in rows] == [1, 0, 0, 1, 0, 0], "the kind column"
    labels = [row[9] if len(row) > 9 else 0 for row in rows]
    assert labels == [
        LABEL_COLUMN["PER"],
        0,
        0,
        LABEL_COLUMN["GPE"],
        LABEL_COLUMN["TIMEX"],
        LABEL_COLUMN["TIMEX"],
    ]
    assert len(rows[1]) == 9, "a row with no entity to say is exactly as long as it was"
