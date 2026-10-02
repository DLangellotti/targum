"""How a French word is said in its sentence (targum-internal#266): its reading from
Morphalou, the liaisons every speaker makes, elisions and the final letters nobody says.

Offline: a few rows written in the table's own shape, never rows of the table itself.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from targum.annotate import french_said, morphalou
from targum.models import Token

HEAD = """\
LEMME;;;;;;;;;FLEXION;;;;;;;;
GRAPHIE;ID;CATÉGORIE;SOUS CATÉGORIE;LOCUTION;GENRE;AUTRES LEMMES LIÉS;PHONÉTIQUE;ORIGINES;\
GRAPHIE;ID;NOMBRE;MODE;GENRE;TEMPS;PERSONNE;PHONÉTIQUE;ORIGINES
"""

#: (lemma, category, form, number, mood, gender, tense, person, reading)
ROWS = [
    ("le", "Déterminant", "les", "plural", "-", "invariable", "-", "-", "l e OU l E/"),
    ("le", "Déterminant", "le", "singular", "-", "masculine", "-", "-", "l @"),
    ("le", "Déterminant", "l'", "singular", "-", "invariable", "-", "-", "l"),
    ("un", "Déterminant", "un", "singular", "-", "masculine", "-", "-", "9~"),
    ("un", "Nombre", "un", "singular", "-", "masculine", "-", "-", "y n @"),
    ("quelque", "Déterminant", "quelques", "plural", "-", "masculine", "-", "-", "k E l k @"),
    ("ce", "Pronom", "c'", "singular", "-", "masculine", "-", "thirdPerson", "k"),
    ("ami", "Nom commun", "ami", "singular", "-", "-", "-", "-", "a m i"),
    ("ami", "Nom commun", "amis", "plural", "-", "-", "-", "-", "a m i"),
    ("enfant", "Nom commun", "enfants", "plural", "-", "-", "-", "-", "a~ f a~"),
    ("avoir", "Verbe", "ont", "plural", "indicative", "-", "present", "thirdPerson", "o~"),
    ("avoir", "Verbe", "a", "singular", "indicative", "-", "present", "thirdPerson", "a"),
    ("être", "Verbe", "est", "singular", "indicative", "-", "present", "thirdPerson", "e OU E/"),
    ("est", "Nom commun", "est", "singular", "-", "-", "-", "-", "E s t"),
    ("il", "Pronom", "il", "singular", "-", "masculine", "-", "thirdPerson", "i l"),
    ("il", "Pronom", "ils", "plural", "-", "masculine", "-", "thirdPerson", "i l"),
    ("on", "Pronom", "on", "singular", "-", "invariable", "-", "thirdPerson", "o~"),
    ("nous", "Pronom", "nous", "plural", "-", "-", "-", "firstPerson", "n u"),
    ("en", "Pronom", "en", "-", "-", "-", "-", "-", "a~"),
    ("dire", "Verbe", "dit", "singular", "indicative", "-", "present", "thirdPerson", "d i"),
    ("chez", "Préposition", "chez", "-", "-", "-", "-", "-", "S e"),
    ("aller", "Verbe", "allés", "plural", "participle", "masculine", "past", "-", "a l e"),
    ("être", "Verbe", "sont", "plural", "indicative", "-", "present", "thirdPerson", "s o~"),
    ("petit", "Adjectif qualificatif", "petit", "singular", "-", "masculine", "-", "-", "p @ t i"),
    ("haricot", "Nom commun", "haricots", "plural", "-", "-", "-", "-", "a R i k o"),
    ("et", "Conjonction", "et", "-", "-", "-", "-", "-", "e OU E/"),
    ("femme", "Nom commun", "femmes", "plural", "-", "-", "-", "-", "f a m @"),
    ("corps", "Nom commun", "corps", "invariable", "-", "-", "-", "-", "k O R"),
    (
        "parler",
        "Verbe",
        "parlent",
        "plural",
        "indicative",
        "-",
        "present",
        "thirdPerson",
        "p a R l @",
    ),
    ("temps", "Nom commun", "temps", "invariable", "-", "-", "-", "-", "t a~"),
    ("pouvoir", "Verbe", "peut", "singular", "indicative", "-", "present", "thirdPerson", "p 2"),
    ("être", "Verbe", "être", "-", "infinitive", "-", "-", "-", "E t R @"),
    ("là", "Adverbe", "là", "-", "-", "-", "-", "-", "l a"),
    ("bas", "Adjectif qualificatif", "bas", "invariable", "-", "invariable", "-", "-", "b a"),
    ("oeil", "Nom commun", "yeux", "plural", "-", "-", "-", "-", "j 2"),
    ("couvent", "Nom commun", "couvent", "singular", "-", "-", "-", "-", "k u v a~"),
    (
        "couver",
        "Verbe",
        "couvent",
        "plural",
        "indicative",
        "-",
        "present",
        "thirdPerson",
        "k u v @",
    ),
    ("strange", "Nom commun", "zut", "singular", "-", "-", "-", "-", "z y t Q"),
]


def table() -> str:
    lines = [HEAD.rstrip("\n")]
    for n, (lemma, category, form, number, mood, gender, tense, person, said) in enumerate(ROWS):
        grammar = f"{number};{mood};{gender};{tense};{person}"
        lines.append(f"{lemma};{n};{category};;;-;;;m;{form};{n};{grammar};{said};m")
    return "\n".join(lines)


@pytest.fixture
def lexicon() -> morphalou.Lexicon:
    return morphalou.parse(table().splitlines())


def tagged(text: str, spec: list[tuple[str, str, str]]) -> list[Token]:
    """Words placed in `text` in order, as (surface, lemma, part of speech)."""
    out, cursor = [], 0
    for surface, lemma, pos in spec:
        start = text.index(surface, cursor)
        cursor = start + len(surface)
        out.append(
            Token(
                start=start,
                end=cursor,
                surface=surface,
                lemma=lemma,
                band=0,
                pos=pos,
                feats=f"UPOS={pos}",
            )
        )
    return out


def said(lexicon: morphalou.Lexicon, text: str, spec: list[tuple[str, str, str]]):
    words = tagged(text, spec)
    return words, french_said.sentence(text, words, lexicon)


def test_the_notation_becomes_ipa_and_a_final_schwa_is_left_off() -> None:
    assert french_said.to_ipa("f a m @ OU f a m") == "famə"
    assert french_said.everyday("famə") == "fam", "a dictionary's femme"
    assert french_said.everyday("lə") == "lə", "a word of one syllable keeps its vowel"
    assert french_said.to_ipa("a~ f a~") == "ɑ̃fɑ̃"
    assert french_said.to_ipa("Z 2 R 9 9~ S H J N") == "ʒøʁœœ̃ʃɥɲŋ"
    assert french_said.to_ipa("z y t Q") == "", "a symbol it does not know says nothing"


def test_a_word_is_said_as_its_grammar_chooses_or_not_at_all(
    lexicon: morphalou.Lexicon,
) -> None:
    assert french_said.reading(lexicon, "est", "être", "AUX") == "e"
    assert french_said.reading(lexicon, "est", "est", "NOUN") == "ɛst"
    assert french_said.reading(lexicon, "couvent", pos="VERB") == "kuvə"
    assert french_said.reading(lexicon, "couvent", pos="NOUN") == "kuvɑ̃"
    assert french_said.reading(lexicon, "couvent") == "", "two ways and nothing to choose"
    assert french_said.reading(lexicon, "Seguin", pos="PROPN") == "", "no reading, none shown"


def test_un_never_takes_the_reading_of_une(lexicon: morphalou.Lexicon) -> None:
    """The numeral row reads `y n @`: *une*'s, copied onto the masculine."""
    for pos in ("DET", "NUM", "PRON", ""):
        assert french_said.reading(lexicon, "un", "un", pos) == "œ̃"
        assert french_said.reading(lexicon, "Un", "un", pos) == "œ̃"


def test_c_is_said_s_by_the_published_correction(lexicon: morphalou.Lexicon) -> None:
    assert french_said.reading(lexicon, "c’", "ce", "PRON") == "s"
    assert french_said.reading(lexicon, "C'", "ce", "PRON") == "s"
    assert french_said.corrections() == {"c'": "s"}, "one row, and only that one"
    text = french_said.CORRECTIONS_FILE.read_text(encoding="utf-8")
    assert "LGPL-LR" in text and "2026-09-28" in text, "the licence and the date of change"


def test_a_compound_is_said_by_its_parts_with_the_liaison_between_them(
    lexicon: morphalou.Lexicon,
) -> None:
    assert french_said.reading(lexicon, "là-bas") == "laba"
    assert french_said.reading(lexicon, "peut-être") == "pøtɛtʁ", "the t is said"
    assert french_said.reading(lexicon, "là-zut") == "", "a part without a reading: none"


def test_a_determiner_and_a_clitic_link_and_the_consonant_is_gruuts(
    lexicon: morphalou.Lexicon,
) -> None:
    words, out = said(
        lexicon,
        "Les enfants ont quelques amis, on en a.",
        [
            ("Les", "le", "DET"),
            ("enfants", "enfant", "NOUN"),
            ("ont", "avoir", "AUX"),
            ("quelques", "quelque", "DET"),
            ("amis", "ami", "NOUN"),
            ("on", "on", "PRON"),
            ("en", "en", "PRON"),
            ("a", "avoir", "AUX"),
        ],
    )
    assert [one.liaison for one in out] == ["z", "", "", "z", "", "n", "n", ""]
    assert out[0].as_said == "lez‿"
    assert out[3].as_said == "kɛlkəz‿", "the schwa before a liaison is said"
    assert out[4].ipa == "ami" and not out[4].liaison, "across a comma, nothing"


def test_the_optional_and_forbidden_liaisons_are_left_alone(
    lexicon: morphalou.Lexicon,
) -> None:
    _, out = said(
        lexicon,
        "Ils sont allés et les haricots, chez nous ont, un petit ami",
        [
            ("Ils", "il", "PRON"),
            ("sont", "être", "AUX"),
            ("allés", "aller", "VERB"),
            ("et", "et", "CCONJ"),
            ("les", "le", "DET"),
            ("haricots", "haricot", "NOUN"),
            ("chez", "chez", "ADP"),
            ("nous", "nous", "PRON"),
            ("ont", "avoir", "AUX"),
            ("un", "un", "DET"),
            ("petit", "petit", "ADJ"),
            ("ami", "ami", "NOUN"),
        ],
    )
    linked = [one.liaison for one in out]
    assert linked[1] == "", "sont‿allés is optional"
    assert linked[3] == "", "never after et"
    assert linked[4] == "", "never before an h aspiré"
    assert linked[7] == "", "a pronoun after a preposition is tonic"
    assert linked[10] == "", "an adjective before its noun is not in the promise"


def test_an_inverted_pronoun_takes_the_liaison_and_gives_none(
    lexicon: morphalou.Lexicon,
) -> None:
    _, out = said(
        lexicon,
        "dit-il, sont-ils allés",
        [
            ("dit", "dire", "VERB"),
            ("il", "il", "PRON"),
            ("sont", "être", "AUX"),
            ("ils", "il", "PRON"),
            ("allés", "aller", "VERB"),
        ],
    )
    assert [one.liaison for one in out] == ["t", "", "t", "", ""]


def test_a_glide_written_with_a_vowel_takes_the_liaison(lexicon: morphalou.Lexicon) -> None:
    _, out = said(lexicon, "les yeux", [("les", "le", "DET"), ("yeux", "œil", "NOUN")])
    assert out[0].liaison == "z"


def test_the_final_letters_nobody_says_are_found_and_a_liaison_keeps_its_own(
    lexicon: morphalou.Lexicon,
) -> None:
    text = "les corps, les femmes parlent, le temps est petit, les amis"
    words, out = said(
        lexicon,
        text,
        [
            ("les", "le", "DET"),
            ("corps", "corps", "NOUN"),
            ("les", "le", "DET"),
            ("femmes", "femme", "NOUN"),
            ("parlent", "parler", "VERB"),
            ("le", "le", "DET"),
            ("temps", "temps", "NOUN"),
            ("est", "être", "AUX"),
            ("petit", "petit", "ADJ"),
            ("les", "le", "DET"),
            ("amis", "ami", "NOUN"),
        ],
    )
    quiet = [text[one.silent[0] : one.silent[1]] if one.silent else "" for one in out]
    assert quiet == ["s", "ps", "s", "s", "nt", "", "ps", "st", "t", "", "s"]


def test_the_marks_are_the_tie_the_apostrophe_and_the_silent_letters(
    lexicon: morphalou.Lexicon,
) -> None:
    text = "C’est les amis"
    words, out = said(
        lexicon,
        text,
        [
            ("C’", "ce", "PRON"),
            ("est", "être", "AUX"),
            ("les", "le", "DET"),
            ("amis", "ami", "NOUN"),
        ],
    )
    marks = french_said.marks(text, words, out)
    assert marks == [
        (1, 2, french_said.ELIDED, ""),
        (3, 5, french_said.SILENT, ""),
        (9, 10, french_said.TIE, "z"),
        (13, 14, french_said.SILENT, ""),
    ]
    assert [text[a:b] for a, b, _, _ in marks] == ["’", "st", " ", "s"], "no letter is added"


def test_the_switch_is_off_unless_it_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(french_said.FLAG, raising=False)
    assert not french_said.is_on()
    monkeypatch.setenv(french_said.FLAG, "1")
    assert french_said.is_on()


# --- the page -----------------------------------------------------------------------

LINES = [
    "Les enfants ont quelques amis.",
    "C’est petit, et les haricots parlent.",
]
WORDS = [
    [
        ("Les", "le", "DET"),
        ("enfants", "enfant", "NOUN"),
        ("ont", "avoir", "AUX"),
        ("quelques", "quelque", "DET"),
        ("amis", "ami", "NOUN"),
    ],
    [
        ("C’", "ce", "PRON"),
        ("est", "être", "AUX"),
        ("petit", "petit", "ADJ"),
        ("et", "et", "CCONJ"),
        ("les", "le", "DET"),
        ("haricots", "haricot", "NOUN"),
        ("parlent", "parler", "VERB"),
    ],
]


def french_page(out: Path, monkeypatch: pytest.MonkeyPatch, *, on: bool, fetched: bool = True):
    """A French reader, written with the switch on or off, on a machine that has the table
    (a few rows of its shape) or has not."""
    from targum.models import (
        Annotation,
        Block,
        BlockKind,
        Document,
        Segment,
        SegmentedDocument,
        Translation,
    )
    from targum.render import render

    if on:
        monkeypatch.setenv(french_said.FLAG, "1")
    else:
        monkeypatch.delenv(french_said.FLAG, raising=False)
    parsed = morphalou.parse(table().splitlines())
    monkeypatch.setattr(morphalou, "lexicon", lambda: parsed if fetched else None)
    segments, tokens = [], {}
    for n, (text, spec) in enumerate(zip(LINES, WORDS, strict=True)):
        segment = Segment(
            id=f"{n:04d}.000-aaaaaa", block_id=f"b{n:04d}", block_index=n, index=n, text=text
        )
        segments.append(segment)
        tokens[segment.id] = [token.model_copy(update={"band": 1}) for token in tagged(text, spec)]
    document = Document(
        source="memory",
        title="Les amis",
        language="fr",
        blocks=[Block(id="b0000", kind=BlockKind.paragraph, text=LINES[0])],
        content_hash="s",
    )
    segmented = SegmentedDocument(
        document_hash="s", language="fr", segmenter="test/1", segments=segments
    )
    translation = Translation(
        name="English",
        document_hash="s",
        source_language="fr",
        target_language="en",
        provider="null",
        segments={s.id: f"A line ({s.id})." for s in segments},
    )
    annotation = Annotation(
        document_hash="s",
        language="fr",
        annotator="test/1",
        method="frequency",
        method_note="a test",
        tokens=tokens,
    )
    return render(document, segmented, [translation], out, annotation=annotation)[0]


DATA = re.compile(r'(<script type="application/json" id="targum-data">)(.*?)(</script>)', re.S)


def test_off_the_page_is_what_it_was_with_the_table_or_without(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Off, a page written on a machine with Morphalou is the page one without it writes,
    and on a machine without it the switch changes nothing: nothing is shown that the
    table did not say."""
    plain = french_page(tmp_path / "a", monkeypatch, on=False, fetched=False).read_bytes()
    assert french_page(tmp_path / "b", monkeypatch, on=False).read_bytes() == plain
    assert french_page(tmp_path / "c", monkeypatch, on=True, fetched=False).read_bytes() == plain
    html = plain.decode("utf-8")
    assert "data-said-toggle" not in html and "Morphalou" not in html and "said-on" not in html


def test_on_the_switch_adds_its_pieces_and_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the switch on, take out what it adds — its style, its switch, its key, its
    notice, its script and its data — and what is left is the page it was, byte for byte."""
    off = french_page(tmp_path / "off", monkeypatch, on=False).read_text(encoding="utf-8")
    on = french_page(tmp_path / "on", monkeypatch, on=True).read_text(encoding="utf-8")
    assert on != off
    data_on = json.loads(DATA.search(on).group(2))
    data_off = json.loads(DATA.search(off).group(2))
    marks = data_on.pop("said")
    sounds = data_on.pop("sounds")
    # The one column that changes on a word's row is the index of its reading; the offsets
    # and everything else on it are the same.
    heard = {sid: [row[5] for row in rows] for sid, rows in data_on["words"].items()}
    for rows in data_on["words"].values():
        for row in rows:
            row[5] = 0
    assert data_on == data_off, "only the marks and the readings are new"
    assert [sounds[at] for at in heard["0000.000-aaaaaa"]] == [
        "lez‿",
        "ɑ̃fɑ̃",
        "ɔ̃",
        "kɛlkəz‿",
        "ami",
    ]
    assert "sounds" not in data_off
    assert "lez‿" in sounds and "s" in sounds, "les as said before a vowel, c' as /s/"
    assert [3, 4, french_said.TIE, "z"] in marks["0000.000-aaaaaa"]
    assert [1, 2, french_said.ELIDED] in marks["0001.000-aaaaaa"]

    stripped = DATA.sub(lambda m: m.group(1) + m.group(3), on)
    for piece in (
        r"<style>(?:(?!</style>).)*said-tie(?:(?!</style>).)*</style>",
        r'<div class="group" data-what="As said">.*?</div>\n',
        r"<dt>n</dt><dd>the French as said</dd>",
        r'<aside class="credits".*?</aside>\n',
        r"<script>(?:(?!</script>).)*targum:said(?:(?!</script>).)*</script>",
    ):
        stripped, found = re.subn(piece, "", stripped, count=1, flags=re.S)
        assert found == 1, piece
    assert stripped == DATA.sub(lambda m: m.group(1) + m.group(3), off)
    assert "Morphalou 3.1" in on and "LGPL-LR" in on, "the notice the licence decision asks"


def test_the_notice_links_only_where_the_allowlist_says(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_render import OUTBOUND

    html = french_page(tmp_path / "on", monkeypatch, on=True).read_text(encoding="utf-8")
    for match in re.finditer(r"https?://[^\s\"'\\)]+", html):
        assert match.group(0).startswith(OUTBOUND), match.group(0)
