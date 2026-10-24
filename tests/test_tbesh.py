"""A Tanakh word's meaning from STEP Bible's brief lexicon (targum-internal#510).

The fixture is the first seven columns of 117 real TBESH rows. Every Meaning cell in it is
a sentinel: the Meaning column is the Abridged BDB, © Online Bible, and never enters the
repository or the table. Nothing here touches the network.
"""

from __future__ import annotations

import json
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
    "1004 a": 3,
    "1004 b": 2049,
    "1121 a": 4930,
    "1121 b": 2,
    "1254 a": 53,
    "1254 b": 1,
    "3651": 1,
    "3651 a": 22,
    "3651 b": 9,
    "3651 c": 738,
    "6213": 1,
    "6213 a": 2624,
    "6213 b": 3,
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
    assert len(rows) == 117
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
    assert len(parsed) == 30
    assert sum(len(rows) for rows in parsed.values()) == 117


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
    assert table["1980"] == "to go", "'to go: walk' keeps its head"
    assert table["5650"] == "servant; slave"
    assert oshb.shorten("`to come (in)!") == "to come (in)"


def test_a_split_number_says_what_it_means_most_often(briefs: Path) -> None:
    """The card is filed under the bare number, so עָשָׂה takes 6213a's gloss (2,624
    tokens) and never 6213b's (3), whichever row the file or a text has first."""
    assert oshb.brief("6213") == "to make"
    assert oshb.brief("6213 b") == "to make", "the letter is dropped, as `glossed_as` drops it"
    assert oshb.brief("1004 a") == "house"
    assert oshb.brief("1121") == "son"
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
    for rule in ('first ": "', '"/" is written "; "', "closing", "most"):
        assert rule in note
    rows = [line.split("\t") for line in note.splitlines() if line and not line.startswith("#")]
    assert all(len(row) == 4 and all(cell.strip() for cell in row) for row in rows)
    assert oshb.changes() == {"7451": "bad", "3651": "so"}


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


#: ling-he's comparison on the card (targum-internal#510): the lexeme as the tagging
#: writes it, Strong's text before (the start of it), and the brief gloss the card says now.
SAMPLES = [
    ("1254 a", "(absolutely) to create", "to create"),
    ("1254 b", "(absolutely) to create", "to create"),
    ("7225", "the first, in place, time", "first"),
    ("776", "the earth (at large", "land"),
    ("8064", "the sky (as aloft", "heaven"),
    ("430", "gods in the ordinary sense", "God"),
    ("559", "to say (used with great latitude)", "to say"),
    ("1697", "a word; by implication", "word"),
    ("1004 b", "a house (in the greatest variation", "house"),
    ("3045", "to know (properly, to ascertain", "to know"),
    ("7200", "to see, literally or figuratively", "to see"),
    ("1980", "to walk (in a great variety", "to go"),
    ("5414", "to give, used with greatest latitude", "to give"),
    ("3027", "a hand (the open one", "hand"),
    ("6440", "the face (as the part that turns)", "face"),
    ("5650", "a servant", "servant; slave"),
    ("1121 a", "a son (as a builder of the family name)", "son"),
    ("7307", "wind; by resemblance breath", "spirit"),
    ("8199", "to judge, i.e. pronounce sentence", "to judge"),
    ("4325", "water; figuratively, juice", "water"),
]


@pytest.mark.parametrize(("lexeme", "strongs", "ours"), SAMPLES)
def test_ling_hes_twenty_words(briefs: Path, lexeme: str, strongs: str, ours: str) -> None:
    assert oshb.brief(lexeme) == ours
    assert not ours.startswith(strongs), "and it is not the Strong's text it replaces"
