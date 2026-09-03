"""The Hebrew Bible read rather than predicted.

The fixture is three verses of the real Open Scriptures file, kept verbatim, so what these
tests read is what a fetch would have written. Nothing here touches the network.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import pytest

from targum.annotate import oshb

FIXTURES = Path(__file__).parent / "fixtures" / "oshb"


@pytest.fixture
def tagged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A model directory holding Genesis, converted the way `fetch` converts it."""
    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path))
    oshb.forget()
    home = tmp_path / "oshb"
    home.mkdir(parents=True)
    verses = oshb.parse((FIXTURES / "Gen.xml").read_text(encoding="utf-8"))
    (home / "Gen.json").write_text(json.dumps(verses, ensure_ascii=False), encoding="utf-8")
    yield home
    oshb.forget()


def test_a_reference_becomes_the_name_the_morphology_uses(tagged: Path) -> None:
    assert oshb.osis("Genesis 1:1") == "Gen.1.1"
    assert oshb.osis("I Samuel 3:4") == "1Sam.3.4"
    assert oshb.osis("Song of Songs 2:1") == "Song.2.1"


def test_everything_that_is_not_the_hebrew_bible_is_simply_not_ours(tagged: Path) -> None:
    """The ordinary answer for most of the shelf, and not a failure. The Mishnah is
    rabbinic Hebrew, which is a different register with different resources."""
    assert oshb.osis("Mishnah Berakhot 1:1") is None
    assert oshb.osis("Pirkei Avot 1:1") is None
    assert oshb.osis("not a reference at all") is None
    assert oshb.words("Mishnah Shabbat 2:1") is None


def test_a_verse_comes_back_word_by_word(tagged: Path) -> None:
    got = oshb.words("Genesis 1:1")
    assert got is not None
    assert len(got) == 7, "seven words in the first verse of the Bible"
    assert [word.text for word in got][:3] == [
        unicodedata.normalize("NFC", w) for w in ("בְּרֵאשִׁ֖ית", "בָּרָ֣א", "אֱלֹהִ֑ים")
    ]


def test_the_prefix_division_is_the_one_a_person_made(tagged: Path) -> None:
    """The whole reason for this module. `בְּרֵאשִׁית` is a preposition and a noun, and where
    they divide was decided by an editor rather than guessed by a model — which is what
    the current annotator does, and gets wrong once every four words."""
    first = oshb.words("Genesis 1:1")[0]  # type: ignore[index]
    assert first.pieces == tuple(unicodedata.normalize("NFC", w) for w in ("בְּ", "רֵאשִׁ֖ית"))
    assert first.lexemes == ("b", "7225"), "the prefix, and a lexeme number for the noun"
    assert first.morph == ("R", "Ncfsa"), "preposition, then common feminine singular absolute"


def test_a_word_with_no_prefix_is_one_piece(tagged: Path) -> None:
    """Most of them are, and the shape has to be the same either way so a caller never
    branches on how many pieces there happen to be."""
    created = oshb.words("Genesis 1:1")[1]  # type: ignore[index]
    assert created.pieces == (unicodedata.normalize("NFC", "בָּרָ֣א"),)
    assert created.lexemes == ("1254 a",)
    assert created.morph == ("Vqp3ms",), "qal perfect third masculine singular"


def test_the_content_piece_is_the_last_one(tagged: Path) -> None:
    """A claim about Hebrew rather than about this file: the language builds a word by
    putting function letters in front of it, so what is left at the end is the word."""
    first = oshb.words("Genesis 1:1")[0]  # type: ignore[index]
    assert first.pieces[first.content] == unicodedata.normalize("NFC", "רֵאשִׁ֖ית")
    assert first.lexemes[first.content] == "7225"

    created = oshb.words("Genesis 1:1")[1]  # type: ignore[index]
    assert created.pieces[created.content] == unicodedata.normalize("NFC", "בָּרָ֣א"), (
        "a one-piece word is its own content"
    )


def test_the_lexeme_number_says_which_word_this_is(tagged: Path) -> None:
    """What no spelling can. A number distinguishes the senses a bare string collapses,
    and it is the only sense information in the pipeline that is not guessed."""
    for word in oshb.words("Genesis 1:3"):  # type: ignore[union-attr]
        assert word.lexemes[word.content], "every content piece carries one"


def test_the_language_letter_is_not_part_of_the_morphology(tagged: Path) -> None:
    """`H` leads every Hebrew code and `A` the Aramaic of Daniel and Ezra. It is a fact
    about the verse, not about the word, and leaving it on would put it in every code."""
    for word in oshb.words("Genesis 1:1"):  # type: ignore[union-attr]
        for code in word.morph:
            assert not code.startswith(("H", "A")) or code == "A", code


def test_a_book_that_was_never_fetched_answers_nothing(tagged: Path) -> None:
    """A missing book is a book targum does not have. The caller falls back to annotating
    rather than failing a build over a file it can simply fetch again."""
    assert oshb.words("Isaiah 53:1") is None


def test_a_half_written_book_is_treated_as_absent(tagged: Path) -> None:
    """Interrupt a fetch and the file on disk is not JSON. That is a book to re-fetch,
    not a build to lose."""
    (tagged / "Isa.json").write_text("{ this is not json", encoding="utf-8")
    oshb.forget()
    assert oshb.words("Isaiah 53:1") is None


def test_the_qere_wins_and_the_ketiv_is_kept_beside_it(tagged: Path) -> None:
    """Where the Masoretes wrote one word and read another, this file writes the *written*
    form as an ordinary word and hides the *read* form in a note beside it. Taking the
    direct children alone therefore yields the ketiv — unpointed, and not what is on the
    page — which puts the whole verse out by a word.

    Genesis 8:17 is one: `הוצא` written, `הַיְצֵא` read. The shelf carries the read form,
    so that is the one this returns, and a printed Tanakh makes the same choice.
    """
    got = oshb.words("Genesis 8:17")
    assert got is not None
    written = [word for word in got if word.ketiv]
    assert len(written) == 1, "one word in this verse is read differently from how it is written"
    only = written[0]
    assert only.ketiv == "הוצא", "what was written, unpointed as this file leaves it"
    assert only.text.startswith("הַ"), "and what is returned is what is read, and pointed"
    assert only.lexemes[only.content] == "3318", "the lexeme is the same either way"


def test_a_word_read_as_it_is_written_carries_no_ketiv(tagged: Path) -> None:
    """Which is almost all of them, so the field is empty almost always and a caller can
    treat a non-empty one as the exception it is."""
    for word in oshb.words("Genesis 1:1"):  # type: ignore[union-attr]
        assert word.ketiv == ""


def test_the_lexicon_says_which_spellings_are_shared(tagged: Path) -> None:
    """אלה is five headwords; בית is one. A meaning filed under the bare spelling alone is
    filed under the wrong word for the first and the right one for the second, and this
    is how the scripture path tells them apart."""
    (tagged / oshb.LEXICON_FILE).write_text(
        json.dumps(
            {"423": "אָלָה", "428": "אֵלֶּה", "1004": "בַּיִת", "1035": "בֵּית לֶחֶם"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    oshb.forget()
    assert oshb.contested("אלה")
    assert oshb.contested("אָלָה"), "asked with points or without, the answer is the same"
    assert not oshb.contested("בית")
    assert not oshb.contested("בית לחם"), "a two-word headword is its own spelling"
    assert not oshb.contested(""), "nothing is not a shared spelling"
