"""The record forming: a turn's Hebrew read as a text is read, with no model loaded.

`chat/record.py` does three things a test can hold without DICTA: it maps the words the
lemmatizer found in the bare text back onto the pointed line, it asks the glossary cache
and never buys, and it measures what share of a turn lay outside the words the model was
given. The lemmatizer here is a stub that reads words by whitespace.
"""

from __future__ import annotations

from targum.chat import record
from targum.models import Segment, Token

#: What the stub calls each word's dictionary form, where it differs from the word.
FORMS = {"במצפה": "מצפה", "הייתָ": "היה", "הייתָ?": "היה", "היית": "היה"}
NAMES = {"רמון"}


class Spaces:
    """A lemmatizer that calls every run of letters a word."""

    name = "spaces"

    def lemmas(self, segments: list[Segment], language: str) -> dict[str, list[Token]]:
        out: dict[str, list[Token]] = {}
        for segment in segments:
            tokens = []
            at = 0
            for piece in segment.text.split(" "):
                start = segment.text.index(piece, at)
                at = start + len(piece)
                word = piece.strip("?.,!")
                if not word:
                    continue
                end = start + len(word)
                tokens.append(
                    Token(
                        start=start,
                        end=end,
                        surface=word,
                        lemma=FORMS.get(word, word),
                        band=0,
                        pos="PROPN" if word in NAMES else "NOUN",
                    )
                )
            out[segment.id] = tokens
        return out


class Bands:
    name = "stub"
    method = "stub"
    note = ""

    def supports(self, language: str) -> bool:
        return True

    def band(self, lemma: str, language: str) -> int:
        return 2 if len(lemma) <= 3 else 5


def recorder(held: dict[str, str] | None = None) -> record.Recorder:
    kept = held or {}
    return record.Recorder(
        lemmatizer=Spaces(),
        glosses=lambda lemma, source, target: kept.get(lemma, ""),
        bands=Bands(),
    )


def test_words_are_found_in_the_bare_text_and_placed_in_the_pointed_line() -> None:
    line = "הָיִיתָ בְּמִצְפֵּה רָמוֹן?"
    (words,) = recorder({"מצפה": "lookout"}).annotate([line])
    assert [w["surface"] for w in words] == ["הָיִיתָ", "בְּמִצְפֵּה", "רָמוֹן"], (
        "each word spans exactly its own pointed text, marks and all"
    )
    assert [line[w["start"] : w["end"]] for w in words] == [w["surface"] for w in words]
    by = {w["lemma"]: w for w in words}
    assert by["מצפה"]["meaning"] == "lookout", "the meaning held for the dictionary form"
    assert by["רמון"]["pos"] == "PROPN" and by["רמון"]["band"] == 0, "a name is not rated"
    assert by["רמון"]["meaning"] == ""


def test_a_held_meaning_rides_with_the_word_and_nothing_is_bought() -> None:
    asked: list[str] = []

    def glosses(lemma: str, source: str, target: str) -> str:
        asked.append(lemma)
        return {"חם": "hot"}.get(lemma, "")

    reader = record.Recorder(lemmatizer=Spaces(), glosses=glosses, bands=Bands())
    (words,) = reader.annotate(["הָיָה חַם מְאוֹד."])
    by = {w["lemma"]: w for w in words}
    assert by["חם"]["meaning"] == "hot" and by["מאוד"]["meaning"] == ""
    assert sorted(asked) == ["היה", "חם", "מאוד"], "asked once per dictionary form"
    assert by["חם"]["band"] == 2 and by["מאוד"]["band"] == 5


def test_the_share_outside_the_ledger_leaves_names_out() -> None:
    lines = recorder().annotate(["הָיִיתָ בְּמִצְפֵּה רָמוֹן?", "כֵּן, חַם."])
    lemmas = [w["lemma"] for words in lines for w in words if w["pos"] != "PROPN"]
    assert len(lemmas) == 4, "four words of vocabulary; רמון is a name"
    assert record.outside_share(lines, set(lemmas)) == 0.0
    assert record.outside_share(lines, {"כן"}) == 3 / 4
    assert record.outside_share([], set()) == 0.0


def test_nothing_to_read_reads_nothing() -> None:
    assert recorder().annotate([]) == []


def test_a_word_after_an_emoji_is_placed_where_the_browser_counts() -> None:
    """chat.js slices the line by these offsets, and JavaScript counts an emoji as two
    units where Python counts one. Measured in Python, every word after a calendar
    glyph landed one unit early."""
    line = "📅 שחרית בשעה"
    (words,) = recorder().annotate([line])
    assert [w["surface"] for w in words] == ["שחרית", "בשעה"]
    units = line.encode("utf-16-le")
    for word in words:
        cut = units[word["start"] * 2 : word["end"] * 2].decode("utf-16-le")
        assert cut == word["surface"], (word, cut)
