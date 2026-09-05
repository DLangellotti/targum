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


def test_the_content_piece_is_the_one_with_a_number(tagged: Path) -> None:
    """A claim about the tagging rather than about this file: a piece that is a word gets
    a lexeme number and a piece that is stuck to one gets a letter, so the numbers say
    which piece the word is."""
    first = oshb.words("Genesis 1:1")[0]  # type: ignore[index]
    assert first.pieces[first.content] == unicodedata.normalize("NFC", "רֵאשִׁ֖ית")
    assert first.lexemes[first.content] == "7225"

    created = oshb.words("Genesis 1:1")[1]  # type: ignore[index]
    assert created.pieces[created.content] == unicodedata.normalize("NFC", "בָּרָ֣א"), (
        "a one-piece word is its own content"
    )


def test_an_aramaic_noun_is_not_its_own_article() -> None:
    """Aramaic marks a definite noun by adding א to the end of it rather than ה to the
    front, and the tagging cuts that א off as a piece of its own — so under the old
    "last piece" rule `מַלְכָּא`, one of the commonest words in Daniel, was the article and
    not the king (targum-internal#64, #195).

    The word here is Daniel 2:4 as the tagging holds it, written out rather than read
    from a fixture, because the fixture is Genesis and this claim is about Aramaic.
    """
    king = oshb.Word(
        text="מַלְכָּא֙",
        pieces=("מַלְכָּ", "א֙"),
        lexemes=("4430",),
        morph=("Ncmsd", "Td"),
    )
    assert king.content == 0, "the piece with a lexeme number is the word"
    assert king.pieces[king.content] == "מַלְכָּ"
    assert king.lexeme == "4430", "the Aramaic king, not the Hebrew 4428"
    assert king.code == "Ncmsd", "a noun, where it used to answer with the article's code"


def test_a_trailing_particle_that_is_the_word_stays_the_word() -> None:
    """A particle at the end of a word is often the word itself, carrying a conjunction
    on its front. Nothing about its position says otherwise; what decides is that the
    particle is the piece holding the lexeme number.
    """
    for code in ("To", "Tn", "Tm", "Ti", "Tr", "Ta"):
        word = oshb.Word(text="ונא", pieces=("וְ", "נָא"), lexemes=("c", "4994"), morph=("C", code))
        assert word.content == 1, f"{code} trailing carries the number, so it is the word"


def test_a_hebrew_noun_is_not_its_own_pronoun_suffix() -> None:
    """The same rule at the other end of the word. `זַרְעוֹ` is `זַרְע` + `וֹ`, "his seed",
    and the last piece is the suffix — so a noun came back a `PRON`. 17.2% of the words
    in Genesis carry a pronominal suffix (targum-internal#64)."""
    seed = oshb.Word(text="זַרְעוֹ", pieces=("זַרְע", "וֹ"), lexemes=("2233",), morph=("Ncmsc", "Sp3ms"))
    assert seed.content == 0
    assert seed.lexeme == "2233"
    assert seed.code == "Ncmsc", "a noun, where it used to answer with the suffix's code"


def test_where_no_piece_is_numbered_the_last_one_is_the_word() -> None:
    """`בּוֹ` is a preposition and a suffix with no noun between them, and there the
    suffix really is the word."""
    in_it = oshb.Word(text="בּוֹ", pieces=("בְּ", "וֹ"), lexemes=("b",), morph=("R", "Sp3ms"))
    assert in_it.content == 1


def test_a_word_with_no_pieces_to_spare_keeps_its_only_one() -> None:
    """A one-piece word cannot give its content away to the piece before it."""
    alone = oshb.Word(text="א", pieces=("א",), lexemes=("4430",), morph=("Td",))
    assert alone.content == 0


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


#: Three entries in the real file's shape, including the inline `<def>` markup the prose
#: has to be read through and an entry whose meaning is empty.
LEXICON_XML = """<?xml version="1.0" encoding="utf-8"?>
<lexicon xmlns="http://openscriptures.github.com/morphhb/namespace">
  <entry id="H4430">
    <w pos="n-m" xlit="melek" xml:lang="arc">מֶלֶךְ</w>
    <source>(Aramaic) corresponding to <w src="H4428">4428</w>;</source>
    <meaning>a <def>king</def></meaning>
    <usage>king, royal.</usage>
  </entry>
  <entry id="H2418">
    <w xml:lang="arc">חֲיָא</w>
    <meaning>to <def>live</def></meaning>
    <usage>live, keep alive.</usage>
  </entry>
  <entry id="H4481">
    <w xml:lang="arc">מִן</w>
    <meaning></meaning>
    <usage>according, after, because, before.</usage>
  </entry>
</lexicon>
"""


def test_a_lexeme_number_carries_what_the_word_means() -> None:
    """The definition was in the lexicon all along and was being dropped on the floor:
    `parse_lexicon` kept the headword and threw the rest away. Same file, same download,
    same public-domain licence (targum-internal#64)."""
    senses = oshb.parse_senses(LEXICON_XML)
    assert senses["4430"] == "a king", "read through the inline <def> markup"
    assert senses["2418"] == "to live"


def test_where_there_is_no_meaning_the_usage_stands_in() -> None:
    """Strong's leaves `meaning` empty on some function words — `מִן` is one, and it is
    the third commonest word in Daniel's Aramaic. The King James translators' word list
    is a poorer gloss than a definition and a better one than nothing."""
    assert oshb.parse_senses(LEXICON_XML)["4481"] == "according, after, because, before."


def test_a_sense_is_found_however_the_number_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The morphology writes `4430`, and a reference may write `H4430` or `1254 a` where
    a lexeme was split into senses after Strong numbered it."""
    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path))
    oshb.forget()
    home = tmp_path / "oshb"
    home.mkdir(parents=True)
    (home / oshb.SENSES_FILE).write_text(
        json.dumps(oshb.parse_senses(LEXICON_XML), ensure_ascii=False), encoding="utf-8"
    )
    assert oshb.sense("4430") == "a king"
    assert oshb.sense("H4430") == "a king", "the H prefix is not part of the number"
    assert oshb.sense("4430 a") == "a king", "nor is the sense letter"
    assert oshb.sense("9999") == "", "a number with no entry says nothing"
    assert oshb.sense("") == "" and oshb.sense("b") == "", "and neither does a prefix"
    oshb.forget()


def test_a_box_that_fetched_before_senses_existed_simply_has_none(
    tagged: Path,
) -> None:
    """`tagged` writes no senses file, which is the shape of every box that fetched
    before this existed. Nothing is broken by their absence: the words still come back
    with their pieces, their lexeme numbers and their morphology, and only the meaning
    is missing."""
    assert oshb.sense("4430") == ""
    words = oshb.words("Genesis 1:1")
    assert words and words[0].lexemes[words[0].content] == "7225", "the tagging still reads"
