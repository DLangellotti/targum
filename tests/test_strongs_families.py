"""Tanakh root families from Strong's (targum-internal#591).

Strong's says which entry each word is built from; following the links to "a primitive
root" gives every word of the Tanakh its family, across parts of speech. The lexicon here
is made up: invented numbers, a handful of entries written the way the real file writes
them, and no text of any verse.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from targum.annotate import oshb, scripture
from targum.render import builder
from targum.tables import bible
from targum.tables.store import Store

NS = "http://openscriptures.github.com/morphhb/namespace"

#: Two roots spelled alike (9001, 9002), a family on each, a name, an Aramaic word, a
#: guessed derivation, a chain of two links, a loop and a preposition.
ENTRIES = (
    ("9001", "v", "heb", "שָׁמַר", "a primitive root;"),
    ("9002", "v", "heb", "שָׁמַר", "a primitive root;"),
    ("9003", "n-m", "heb", "מִשְׁמָר", 'from <w src="H9001">9001</w>;'),
    ("9004", "n-f", "heb", "שִׁמְרָה", 'feminine of <w src="H9003">9003</w>;'),
    ("9005", "a", "heb", "שָׁמוּר", 'passive participle of <w src="H9001">9001</w>;'),
    ("9006", "n-m", "heb", "שֶׁמֶר", 'from <w src="H9002">9002</w>;'),
    ("9007", "n-pr-m", "heb", "שִׁמְרִי", 'from <w src="H9001">9001</w>;'),
    ("9008", "n-m", "arc", "שְׁמָר", 'from <w src="H9001">9001</w>;'),
    ("9009", "n-m", "heb", "שְׁמִירָה", 'probably from <w src="H9001">9001</w>;'),
    ("9010", "v", "heb", "כָּתַב", "a primitive root;"),
    ("9011", "n-m", "heb", "כֶּתֶב", 'from <w src="H9012">9012</w>;'),
    ("9012", "n-m", "heb", "כְּתָב", 'from <w src="H9011">9011</w>;'),
    ("9013", "prep", "heb", "שֶׁם", 'from <w src="H9001">9001</w>;'),
)


def lexicon_xml() -> str:
    rows = "".join(
        f'<entry id="H{number}"><w pos="{pos}" xml:lang="{lang}">{word}</w>'
        f"<source>{source}</source><meaning>a word</meaning></entry>"
        for number, pos, lang, word, source in ENTRIES
    )
    return f'<?xml version="1.0" encoding="utf-8"?><lexicon xmlns="{NS}">{rows}</lexicon>'


@pytest.fixture
def lexicon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A model directory holding the made-up lexicon, as `fetch` would have written it."""
    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path))
    oshb.forget()
    home = tmp_path / "oshb"
    home.mkdir(parents=True)
    xml = lexicon_xml()
    counts = {"9003 a": 40, "9003 b": 5, "9004": 60, "9005": 3, "9006": 7, "9001": 90}
    (home / oshb.LEXICON_FILE).write_text(
        json.dumps(oshb.parse_lexicon(xml), ensure_ascii=False), encoding="utf-8"
    )
    (home / oshb.DERIVATIONS_FILE).write_text(
        json.dumps(oshb.parse_derivations(xml, counts), ensure_ascii=False), encoding="utf-8"
    )
    yield home
    oshb.forget()


def test_each_entry_says_what_it_is_built_from() -> None:
    links = oshb.parse_derivations(lexicon_xml(), {"9003 a": 40, "9003 b": 5})
    assert links["9001"] == ["v", "heb", oshb.PRIMITIVE, 0]
    assert links["9003"] == ["n-m", "heb", "9001", 45], "senses of one number are summed"
    assert links["9004"][2] == "9003" and links["9005"][2] == "9001"
    assert links["9009"][2] == "", "a lexicographer's guess is not followed"
    assert links["9008"][1] == "arc"


def test_a_family_runs_across_parts_of_speech_root_first(lexicon: Path) -> None:
    assert oshb.family_root("9004") == "9001", "two links, to the root"
    assert oshb.family("9004") == ("9001", "9003", "9005")
    assert [oshb.kind(one) for one in ("9001", "9003", "9004", "9005")] == [
        "VERB",
        "NOUN",
        "NOUN",
        "ADJ",
    ]
    assert oshb.family("9001") == ("9004", "9003", "9005"), "then the most used first"


def test_two_roots_spelled_alike_are_never_one_family(lexicon: Path) -> None:
    assert oshb.family_root("9006") == "9002"
    assert "9006" not in oshb.family("9003") and "9003" not in oshb.family("9006")
    assert oshb.family("9006") == ("9002",)
    assert oshb.root_name("9001") == "שמר (H9001)"
    assert oshb.root_name("9002") == "שמר (H9002)"
    assert oshb.root_name("9010") == "כתב", "a root spelled once needs no number"


def test_names_aramaic_guesses_and_loops_have_no_family(lexicon: Path) -> None:
    assert "9007" not in oshb.family("9001"), "a name is not a word to learn from"
    assert "9008" not in oshb.family("9001") and oshb.family("9008") == ()
    assert oshb.family_root("9009") == "" and oshb.family("9009") == ()
    assert oshb.family_root("9011") == "", "a loop reaches no root"
    assert oshb.family("9010") == (), "a root with nothing built on it"
    assert oshb.family("9013") == () and "9013" not in oshb.family("9001"), (
        "a preposition Strong's derives from a verb is etymology, not family"
    )


def test_a_machine_without_the_families_draws_what_it_drew(lexicon: Path) -> None:
    (lexicon / oshb.DERIVATIONS_FILE).unlink()
    oshb.forget()
    assert oshb.family("9004") == () and oshb.family_root("9004") == ""


# --- the card -------------------------------------------------------------------------


def _token(**said: str) -> SimpleNamespace:
    return SimpleNamespace(**{"lemma": "", "binyan": "", "pos": "", "lexeme": "", **said})


def test_a_tanakh_word_carries_its_family_with_parts_of_speech(lexicon: Path) -> None:
    families: list[list[list[str]]] = [[]]
    family_at: dict[str, int] = {"": 0}
    at = builder._family_at(_token(lemma="שמרה", pos="NOUN", lexeme="9004"), families, family_at)
    assert at == 1
    assert families[1] == [["שָׁמַר", "VERB"], ["מִשְׁמָר", "NOUN"], ["שָׁמוּר", "ADJ"]]
    again = builder._family_at(_token(lemma="שמרה", lexeme="9004"), families, family_at)
    assert again == 1 and len(families) == 2, "one family a word, drawn once"


def test_a_word_strongs_gives_no_family_keeps_the_verb_family(
    lexicon: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum.annotate import paradigms

    monkeypatch.setattr(paradigms, "family_of", lambda lemma, binyan: (("הִכְתִּיב", "הפעיל"),))
    families: list[list[list[str]]] = [[]]
    family_at: dict[str, int] = {"": 0}
    token = _token(lemma="כָּתַב", pos="VERB", binyan="פעל", lexeme="9010")
    assert builder._family_at(token, families, family_at) == 1
    assert families[1] == [["הִכְתִּיב", "הפעיל"]]


def test_the_family_is_capped(lexicon: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from targum.annotate import paradigms

    monkeypatch.setattr(paradigms, "SIBLINGS", 2)
    families: list[list[list[str]]] = [[]]
    builder._family_at(_token(lexeme="9001"), families, {"": 0})
    assert len(families[1]) == 2


# --- the roots table's bible register ---------------------------------------------------


def _word(lexeme: str, code: str) -> oshb.Word:
    return oshb.Word("w", ("w",), (lexeme,), (code,))


def test_the_bible_register_counts_roots_across_parts_of_speech(lexicon: Path) -> None:
    verses = [
        ("Gen.1.1", (_word("9004", "Ncfsa"), _word("9003", "Ncmsa"), _word("9006", "Ncmsa"))),
        ("Gen.1.2", (_word("9001", "Vqp3ms"), _word("9007", "Npm"), _word("9009", "Ncfsa"))),
        ("Dan.2.4", (_word("9005", "Aamsa"),)),
    ]
    counted = bible.count_roots(verses)
    assert counted == {
        ("שמר (H9001)", "NOUN"): 2,
        ("שמר (H9001)", "VERB"): 1,
        ("שמר (H9002)", "NOUN"): 1,
        ("שמר (H9001)", bible.ARAMAIC): 1,
    }


def test_the_roots_pass_writes_every_book(
    lexicon: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.util

    script = Path(__file__).resolve().parent.parent / "scripts" / "count_tanakh.py"
    spec = importlib.util.spec_from_file_location("count_tanakh", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(oshb, "verses", lambda code: [(f"{code}.1.1", (_word("9004", "Ncfsa"),))])
    # The real check asks for a real number; here the made-up lexicon stands in for it.
    monkeypatch.setattr(
        oshb,
        "family_root",
        lambda lexeme, real=oshb.family_root: real("9004" if lexeme == "4428" else lexeme),
    )
    said: list[str] = []
    ledger = tmp_path / "corpus.db"
    assert module.roots(ledger, said.append) == 0
    store = Store(ledger)
    books = len(set(oshb.BOOKS.values()))
    assert store.registers(bible.ROOTS) == {"bible": books}
    assert store.total(bible.ROOTS, "bible") == books
    with sqlite3.connect(ledger) as db:
        tools = {row[0] for row in db.execute("SELECT tool FROM contribution WHERE tbl = 'roots'")}
    assert tools == {oshb.FAMILIES}
    assert any("roots:" in line for line in said)


def test_the_roots_pass_stops_without_the_families(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.util

    script = Path(__file__).resolve().parent.parent / "scripts" / "count_tanakh.py"
    spec = importlib.util.spec_from_file_location("count_tanakh", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path))
    oshb.forget()
    said: list[str] = []
    try:
        assert module.roots(tmp_path / "corpus.db", said.append) == 1
    finally:
        oshb.forget()
    assert any("models fetch scripture" in line for line in said)


def test_scripture_is_still_filed_as_it_was() -> None:
    """Nothing here changes what an annotation says: no rename, no schema bump."""
    assert scripture.LEXEME_ALIASES == {"3212": "1980"}
