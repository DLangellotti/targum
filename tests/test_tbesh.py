"""A Tanakh word's meaning from STEP Bible's brief lexicon (targum-internal#510).

The fixture is the first seven columns of 16 real TBESH rows, kept to a handful because
STEP Bible asks that the file not be redistributed. Every Meaning cell in it is a
sentinel: the Meaning column is the Abridged BDB, © Online Bible, and never enters the
repository or the table. The head-row cases further down carry only the rows that compete
for a head, without the Hebrew. Nothing here touches the network.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from targum.annotate import oshb

FIXTURES = Path(__file__).parent / "fixtures" / "oshb"
TBESH_TEXT = (FIXTURES / "tbesh.txt").read_text(encoding="utf-8")
SENTINEL = "ONLINE-BIBLE-MEANING-SENTINEL"

#: How often each split lexeme occurs across the Tanakh, as the tagging writes it,
#: counted over the 39 books on 2026-10-24. Enough of `_counts()` to pick the variants.
COUNTS = {
    "1254 a": 53,
    "1254 b": 1,
    "3651": 1,
    "3651 a": 22,
    "3651 b": 9,
    "3651 c": 738,
    "6213": 1,
    "6213 a": 2624,
    "6213 b": 3,
    "6635 a": 199,
    "6635 b": 287,
    "7451": 13,
    "7451 a": 242,
    "7451 b": 104,
    "7451 c": 305,
}


@pytest.fixture
def briefs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A model directory holding the brief glosses, written the way `fetch` writes them."""
    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path))
    oshb.forget()
    home = tmp_path / "oshb"
    home.mkdir(parents=True)
    table = oshb.briefs_from(oshb.parse_tbesh(TBESH_TEXT), COUNTS)
    (home / oshb.TBESH_FILE).write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
    yield home
    oshb.forget()


def test_the_fixture_carries_no_online_bible_text() -> None:
    """The fixture is in a public repository, so its Meaning cells are sentinels only."""
    rows = [line.split("\t") for line in TBESH_TEXT.splitlines() if line.startswith("H")]
    assert len(rows) == 16
    assert all(len(row) == 8 and row[7].startswith(SENTINEL) for row in rows)


def test_no_meaning_reaches_the_table(briefs: Path) -> None:
    """The Meaning column is Online Bible's copyright, carved out of STEP Bible's grant.
    It is cut off at the split and never held, stored or shipped."""
    parsed = oshb.parse_tbesh(TBESH_TEXT)
    assert SENTINEL not in repr(parsed), "not even in memory past the split"
    assert all(len(row) == 5 for rows in parsed.values() for row in rows)
    written = (briefs / oshb.TBESH_FILE).read_text(encoding="utf-8")
    assert SENTINEL not in written


def test_a_row_is_a_line_whose_first_field_is_an_estrong() -> None:
    parsed = oshb.parse_tbesh(TBESH_TEXT)
    assert "eStrong#" not in parsed, "the header is prose about the data"
    assert len(parsed) == 12
    assert sum(len(rows) for rows in parsed.values()) == 16


def test_the_tagging_number_is_the_estrong_written_another_way() -> None:
    assert oshb._key("H7225") == "7225"
    assert oshb._key("H1254a") == "1254 a"
    assert oshb._key("H0430") == "430", "zero-padded there, not in the tagging"
    assert oshb._key("G0430") == "" and oshb._key("H123") == ""


def test_the_brief_is_the_head_of_the_head_row() -> None:
    """The row that is the word itself, cut at its first ": ", with "/" as "; "."""
    table = oshb.briefs_from(oshb.parse_tbesh(TBESH_TEXT), COUNTS)
    assert table["1697"] == "word", "H1697G =, not one of its 'a Meaning of' rows"
    assert table["430"] == "God", "no row stands alone, so the first that is not a name"
    assert table["1870"] == "way", "the row its senses point to, cut at ': '"
    assert table["5650"] == "servant; slave"
    assert oshb.shorten("`to come (in)!") == "to come (in)"


def test_a_phrasal_verb_keeps_its_slash() -> None:
    """ "to cut down; off" reads as two meanings, the second not a word."""
    assert oshb.shorten("to cut down/off") == "to cut down/off"
    assert oshb.shorten("to pass on/over/away") == "to pass on/over/away"
    assert oshb.shorten("servant/slave") == "servant; slave"
    assert oshb.shorten("to go up/come") == "to go up; come"


def test_a_name_variant_sits_out_the_count(briefs: Path) -> None:
    """צָבָא: 6635b "Hosts", the name in "LORD of Hosts", has more tokens (287) than 6635a
    "army" (199). The card is the word."""
    assert oshb.brief("6635") == "army"
    table = json.loads((briefs / oshb.TBESH_FILE).read_text(encoding="utf-8"))
    assert table["6635 b"] == "Hosts", "the lettered key still says what its row says"


def test_a_name_is_a_capitalised_gloss_and_a_gentilic_is_not() -> None:
    row = oshb.TbeshRow
    assert oshb.is_name(row("H1870", "H1870H =", "H1870H", "H:N-M", "Way"))
    assert oshb.is_name(row("H6635b", "H6635B = a Name of", "H3068G", "N:N-M-T", "Hosts"))
    assert oshb.is_name(row("H5483b", "H5483B =", "H5483B", "H:N-M", "(Gate of the) Horse"))
    assert not oshb.is_name(row("H2975", "H2975H =", "H2975H", "N:N--L", "stream"))
    assert not oshb.is_name(row("H3669a", "H3669A =", "H3667A", "N:N--LG", "Canaanite"))


def test_a_split_number_says_what_it_means_most_often(briefs: Path) -> None:
    """The card is filed under the bare number, so עָשָׂה takes 6213a's gloss (2,624
    tokens) and never 6213b's (3), whichever row the file or a text has first."""
    assert oshb.brief("6213") == "to make"
    assert oshb.brief("6213 b") == "to make", "the letter is dropped, as `glossed_as` drops it"
    assert oshb.brief("1254 b") == "to create"
    table = json.loads((briefs / oshb.TBESH_FILE).read_text(encoding="utf-8"))
    assert table["6213 b"] == "to press", "the lettered keys are kept for a later card"
    assert table["1254 b"] == "to fatten"


def test_with_no_counts_a_split_number_falls_to_its_first_letter() -> None:
    table = oshb.briefs_from(oshb.parse_tbesh(TBESH_TEXT), {})
    assert table["1254"] == "to create"
    assert table["6213"] == "to make"


def test_targums_changes_win(briefs: Path) -> None:
    """רָעָה is tagged 7451c, so the count gives "distress"; the card is רע."""
    table = json.loads((briefs / oshb.TBESH_FILE).read_text(encoding="utf-8"))
    assert table["7451"] == "distress"
    assert oshb.brief("7451") == "bad"
    assert oshb.brief("3651") == "so"


def test_the_change_note_names_every_rule_and_every_fix() -> None:
    """The licence asks for a note of changes those who use the data can see. The note
    is the file the fixes are read from, so the two cannot drift apart."""
    note = oshb.TBESH_CHANGES.read_text(encoding="utf-8")
    assert "CC BY 4.0" in note and "48b7cfbda441adb6445ea565b4ed23dd98dfdf2e" in note
    for rule in (
        'first ": "',
        '"/" is written "; "',
        "phrasal verb",
        "closing",
        "most",
        "capitalised",
        '"a Meaning of" rows point to',
        "sits the count out",
    ):
        assert rule in note
    rows = [line.split("\t") for line in note.splitlines() if line and not line.startswith("#")]
    assert all(len(row) == 4 and all(cell.strip() for cell in row) for row in rows)
    assert oshb.changes() == {
        "7451": "bad",
        "3651": "so",
        "6310": "mouth",
        "2896": "good",
        "5945": "upper; Most High",
        "6924": "east; of old",
    }


def test_the_reviewers_fixes_win(briefs: Path) -> None:
    """פֶּה is "lip" in TBESH and "mouth" to a learner; טוֹב "pleasant" and "good"."""
    assert oshb.brief("6310") == "mouth"
    assert oshb.brief("2896") == "good"
    assert oshb.brief("5945 b") == "upper; Most High", "עֶלְיוֹן is both, and the name sits out"
    assert oshb.brief("6924") == "east; of old"


def test_without_the_file_strongs_stays(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from targum.annotate.gloss import from_the_tagging
    from targum.models import Annotation, Token

    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path))
    oshb.forget()
    (tmp_path / "oshb").mkdir()
    (tmp_path / "oshb" / oshb.SENSES_FILE).write_text(
        json.dumps({"4430": "a king"}), encoding="utf-8"
    )
    assert oshb.brief("4430") == ""
    king = Token(start=0, end=5, surface="מלכא", lemma="מלך", band=0, pos="NOUN", lexeme="4430")
    annotation = Annotation(
        document_hash="h",
        language="he",
        annotator="oshb/7",
        method="frequency",
        method_note="note",
        tokens={"s1": [king]},
    )
    assert from_the_tagging(annotation)["מלך"].gloss == "a king"
    oshb.forget()


def test_every_asah_is_to_make_whichever_comes_first(briefs: Path) -> None:
    """A text whose first עָשָׂה is 6213b used to lend "to press" to all of them, because
    `from_the_tagging` takes the first token per key and the key has no letter."""
    from targum.annotate.gloss import from_the_tagging
    from targum.models import Annotation, Token

    pressed = Token(start=0, end=3, surface="עשו", lemma="עשה", band=1, pos="VERB", lexeme="6213 b")
    made = Token(start=0, end=3, surface="עשה", lemma="עשה", band=1, pos="VERB", lexeme="6213 a")
    annotation = Annotation(
        document_hash="h",
        language="he",
        annotator="oshb/7",
        method="frequency",
        method_note="note",
        tokens={"s1": [pressed], "s2": [made]},
    )
    found = from_the_tagging(annotation)
    assert [sense.gloss for sense in found.values()] == ["to make"]
    assert all("press" not in sense.gloss for sense in found.values())


def test_the_credit_keys_on_a_gloss_the_glossary_actually_shows(briefs: Path) -> None:
    from targum.annotate.gloss import from_step_bible
    from targum.models import Annotation, Token

    made = Token(start=0, end=3, surface="עשה", lemma="עשה", band=1, pos="VERB", lexeme="6213 a")
    annotation = Annotation(
        document_hash="h",
        language="he",
        annotator="oshb/7",
        method="frequency",
        method_note="note",
        tokens={"s1": [made]},
    )
    assert from_step_bible(annotation, {made.glossed_as: "to make"})
    assert not from_step_bible(annotation, {made.glossed_as: "to do; to make"}), "bought"
    assert not from_step_bible(annotation, {})
    assert not from_step_bible(None, {made.glossed_as: "to make"})


def test_the_fetch_brings_the_glosses_to_a_box_that_has_the_lexicon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gated on its own file: a box with `strongs.json` would otherwise never get it.
    Pinned to the commit, and what is written holds the Gloss column alone."""
    import httpx

    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path))
    oshb.forget()
    home = tmp_path / "oshb"
    home.mkdir()
    verses = oshb.parse((FIXTURES / "Gen.xml").read_text(encoding="utf-8"))
    for code in set(oshb.BOOKS.values()):
        (home / f"{code}.json").write_text(json.dumps(verses if code == "Gen" else {}))
    (home / oshb.LEXICON_FILE).write_text("{}")
    asked: list[str] = []

    def get(url: str, **_: object) -> httpx.Response:
        asked.append(url)
        return httpx.Response(200, text=TBESH_TEXT, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get)
    oshb.fetch()
    assert asked == [oshb.TBESH]
    assert "/48b7cfbda441adb6445ea565b4ed23dd98dfdf2e/Lexicons/TBESH" in oshb.TBESH
    written = (home / oshb.TBESH_FILE).read_text(encoding="utf-8")
    assert SENTINEL not in written
    assert oshb.brief("1254") == "to create"
    oshb.fetch()
    assert asked == [oshb.TBESH], "idempotent: the file is there"
    oshb.forget()


#: The rules on rows made for the purpose: the patterns ling-he's review found, with
#: none of TBESH's own rows copied in (STEP Bible asks that the file not be passed on).
def _row(dstrong: str, morph: str, gloss: str, ustrong: str = "") -> oshb.TbeshRow:
    left = dstrong.split("=")[0].strip()
    return oshb.TbeshRow("H0001", dstrong, ustrong or left, morph, gloss)


def test_the_row_the_senses_point_to_is_the_head() -> None:
    rows = [
        _row("H0001G = a Meaning of", "H:N-M", "word: one", "H0001K"),
        _row("H0001H =", "H:N-M", "Word"),
        _row("H0001J =", "H:N-M", "other"),
        _row("H0001K =", "H:N-M", "word: two"),
    ]
    assert oshb._head(rows).gloss == "word: two", "not the name, not the first lowercase row"


def test_a_name_row_never_beats_the_word() -> None:
    rows = [_row("H0001G =", "H:N-M", "Thing (Gate)"), _row("H0001H =", "H:N-M", "thing")]
    assert oshb._head(rows).gloss == "thing"
    rows = [_row("H0001G =", "N:N--L", "Place"), _row("H0001H =", "N:N--L", "stream")]
    assert oshb._head(rows).gloss == "stream", "a lowercase gloss is a word, whatever its morph"


def test_where_every_row_is_a_name_the_first_own_row_stands() -> None:
    rows = [
        _row("H0001G = a Name of", "N:N-M-P", "Other", "H0002"),
        _row("H0001H =", "N:N-M-P", "Person"),
    ]
    assert oshb._head(rows).gloss == "Person"
    rows = [_row("H0001G = a Name of", "H:N-M", "Deity", "H0002")]
    assert oshb._head(rows).gloss == "Deity", "how אֱלֹהִים stays God"


#: For a run with the real file to hand: `TARGUM_TBESH_TXT=<path to the TBESH file>`.
#: Skipped everywhere else, CI included, because the file is not in the repository.
REAL = os.environ.get("TARGUM_TBESH_TXT", "")


#: ling-he's 20-word table on the card (targum-internal#510), as the card reads it.
SAID = {
    "1254 a": "to create",
    "1254 b": "to fatten",
    "7225": "first",
    "776": "land",
    "8064": "heaven",
    "430": "God",
    "559": "to say",
    "1697": "word",
    "1004 b": "house",
    "3045": "to know",
    "7200": "to see",
    "1980": "to go",
    "5414": "to give",
    "3027": "hand",
    "6440": "face",
    "5650": "servant; slave",
    "1121 a": "son",
    "7307": "spirit",
    "8199": "to judge",
    "4325": "water",
}


#: Every entry ling-he's review found reading a name where TBESH has the common word
#: (2026-10-24), and what each reads now.
WORDS = {
    "H0329": "bramble",
    "H0410": "god",
    "H0830": "refuse",
    "H1389": "hill",
    "H1516": "valley",
    "H1588": "garden",
    "H1709": "fish",
    "H1870": "way",
    "H1902": "meditation",
    "H2132": "olive",
    "H2319": "new",
    "H2793": "wood",
    "H2975": "stream",
    "H3247": "foundation",
    "H3277": "goat",
    "H3452": "wilderness",
    "H3465": "old",
    "H3526": "to wash",
    "H3603": "talent",
    "H3685": "constellation",
    "H3723": "village",
    "H4026": "tower",
    "H4217": "east",
    "H4307": "guardhouse",
    "H4417": "salt",
    "H4436": "queen",
    "H4629": "gap",
    "H4662": "appointment",
    "H4740": "corner",
    "H4932": "second",
    "H5483b": "horse",
    "H5488": "reed",
    "H5869b": "spring",
    "H6010": "valley",
    "H6112": "spear",
    "H6160": "plain",
    "H6438": "corner",
    "H6924a": "front",
    "H7342": "broad",
    "H7620": "week",
    "H7845": "pit",
    "H8577b": "serpent",
}


@pytest.mark.skipif(not REAL, reason="needs the TBESH file, which is not in the repository")
def test_against_the_real_file() -> None:
    rows = oshb.parse_tbesh(Path(REAL).read_text(encoding="utf-8"))
    table = oshb.briefs_from(rows, COUNTS)
    assert {lexeme: table[lexeme] for lexeme in SAID if " " in lexeme} == {
        lexeme: said for lexeme, said in SAID.items() if " " in lexeme
    }
    assert {lexeme: table[lexeme] for lexeme in SAID if " " not in lexeme} == {
        lexeme: said for lexeme, said in SAID.items() if " " not in lexeme
    }
    assert {estrong: oshb.shorten(oshb._head(rows[estrong]).gloss) for estrong in WORDS} == WORDS
    assert SENTINEL not in json.dumps(table)
