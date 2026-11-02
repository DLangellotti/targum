"""What the card knows of a root beyond a verb's, from targum's own root lexicons
(targum-internal#593, #596): a Hebrew noun's root and pattern, a borrowed word, a Russian
word's root morphs and prefixes, and the family line counting them.

The lexicons are private and never in the repository; every row here is made up for the
test, in the shape `scripts/build_roots.py` writes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from targum import occurrences
from targum.annotate import root_card
from targum.models import Annotation, Document, Segment, SegmentedDocument, Token, Translation

HEBREW = {
    "version": "roots/1+prompt/1-test",
    "language": "he",
    "lemmas": {
        "מכתב": {
            "root": "כ־ת־ב",
            "pattern": "מִקְטָל",
            "borrowed": False,
            "meaning": "write",
            "transparent": "yes",
        },
        "חשבון": {
            "root": "ח־ש־ב",
            "pattern": "קֶטְלוֹן",
            "borrowed": False,
            "meaning": "think, count",
            "transparent": "partly",
        },
        "זמן": {
            "root": "ז־מ־נ",
            "pattern": "קְטָל",
            "borrowed": False,
            "meaning": "time",
            "transparent": "yes",
        },
        "ערב": {
            "root": "ע־ר־ב",
            "pattern": "קֶטֶל",
            "borrowed": False,
            "meaning": "evening",
            "transparent": "yes",
        },
        "ערבות": {
            "root": "ע־ר־ב",
            "pattern": "קַטְלוּת",
            "borrowed": False,
            "meaning": "guarantee",
            "transparent": "yes",
        },
        "ערב2": {
            "root": "ע־ר־ב",
            "pattern": "פעל",
            "borrowed": False,
            "meaning": "guarantee, vouch",
            "transparent": "yes",
        },
        "טלפון": {
            "root": None,
            "pattern": None,
            "borrowed": True,
            "meaning": None,
            "transparent": None,
        },
        "כתב": {
            "root": "כ־ת־ב",
            "pattern": "פעל",
            "borrowed": False,
            "meaning": "write",
            "transparent": "yes",
        },
        # Denied by `verb_roots.WRONG` for this lemma: never shown, whatever says so.
        "נשמה": {
            "root": "ש־מ־ה",
            "pattern": "קְטָלָה",
            "borrowed": False,
            "meaning": "breath",
            "transparent": "yes",
        },
        "נזיר": {
            "root": "נ־ז־ר",
            "pattern": "קָטִיל",
            "borrowed": False,
            "meaning": "abstain",
            "transparent": "yes",
        },
        "בית": {
            "root": None,
            "pattern": None,
            "borrowed": False,
            "meaning": None,
            "transparent": None,
        },
    },
}

RUSSIAN = {
    "version": "ru-roots/1+prompt/1-test",
    "language": "ru",
    "lemmas": {
        "приходить": {
            "roots": [{"morph": "ход", "variants": ["хож", "ш"], "sense": "go"}],
            "prefixes": ["при"],
            "suffixes": ["и"],
            "transparency": "transparent",
            "borrowed": False,
        },
        "выход": {
            "roots": [{"morph": "ход", "variants": [], "sense": "go"}],
            "prefixes": ["вы"],
            "suffixes": [],
            "transparency": "transparent",
            "borrowed": False,
        },
        "пароход": {
            "roots": [
                {"morph": "пар", "variants": [], "sense": "steam"},
                {"morph": "ход", "variants": [], "sense": "go"},
            ],
            "prefixes": [],
            "suffixes": [],
            "transparency": "transparent",
            "borrowed": False,
        },
        "летать": {
            "roots": [{"morph": "лет", "variants": ["леч"], "sense": "fly"}],
            "prefixes": [],
            "suffixes": ["а"],
            "transparency": "transparent",
            "borrowed": False,
        },
        "летний": {
            "roots": [{"morph": "лет", "variants": [], "sense": "summer"}],
            "prefixes": [],
            "suffixes": ["н"],
            "transparency": "transparent",
            "borrowed": False,
        },
        "самолёт": {
            "roots": [
                {"morph": "сам", "variants": [], "sense": "self"},
                {"morph": "лёт", "variants": ["лет"], "sense": "fly, flight"},
            ],
            "prefixes": [],
            "suffixes": [],
            "transparency": "partial",
            "borrowed": False,
        },
    },
}


@pytest.fixture()
def lexicons(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for language, body in (("he", HEBREW), ("ru", RUSSIAN)):
        file = tmp_path / f"roots-{language}.json"
        file.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setenv(root_card.ENV[language], str(file))


def test_no_lexicon_says_nothing() -> None:
    """The suite's own default (conftest): a named path that is not there."""
    assert root_card.lexicon("he") is None
    assert root_card.hebrew_shape("מכתב", "NOUN", "") == 0
    assert root_card.russian_shape("выход", "NOUN") == 0
    assert root_card.family_root("מכתב", "NOUN", "", "he") == ""


def test_a_lexicon_of_another_version_or_language_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = tmp_path / "roots-he.json"
    file.write_text(json.dumps({**HEBREW, "version": "roots/9"}), encoding="utf-8")
    monkeypatch.setenv("TARGUM_ROOTS_HE", str(file))
    assert root_card.lexicon("he") is None
    file.write_text(json.dumps({**HEBREW, "language": "ru"}), encoding="utf-8")
    assert root_card.lexicon("he") is None


@pytest.mark.usefixtures("lexicons")
def test_a_noun_gets_its_root_and_mishkal_in_the_annotations_shape() -> None:
    assert root_card.hebrew_shape("מכתב", "NOUN", "") == ["כתב", "מִקְטָל", "write", 0, 1]
    # The last letter final, as the annotation writes a verb's root: ז־מ־נ is זמן.
    assert root_card.hebrew_shape("זמן", "NOUN", "")[0] == "זמן"
    assert root_card.as_drawn("ז־מ־נ") == "זמן"
    # A root graded partly transparent is shown, and said so.
    assert root_card.hebrew_shape("חשבון", "NOUN", "") == ["חשב", "קֶטְלוֹן", "think, count", 0, 0]


@pytest.mark.usefixtures("lexicons")
def test_a_borrowed_word_says_so_and_a_primary_noun_says_nothing() -> None:
    assert root_card.hebrew_shape("טלפון", "NOUN", "") == ["", "", "", 1, 0]
    assert root_card.hebrew_shape("בית", "NOUN", "") == 0
    assert root_card.hebrew_shape("לא-בלקסיקון", "NOUN", "") == 0


@pytest.mark.usefixtures("lexicons")
def test_a_denied_root_is_never_shown() -> None:
    """`verb_roots.denied` stays authoritative: WRONG for this lemma, and the nif'al-like
    adjective whose root the deny list files under it."""
    assert root_card.noun_root("נשמה", "NOUN") == ""
    assert root_card.hebrew_shape("נשמה", "NOUN", "") == 0
    assert root_card.family_root("נשמה", "NOUN", "", "he") == ""
    # נזיר's deny is זיר; the lexicon's נ־ז־ר is the right one and is kept.
    assert root_card.noun_root("נזיר", "NOUN") == "נזר"


@pytest.mark.usefixtures("lexicons")
def test_a_verb_keeps_its_own_root_and_is_given_only_the_meaning() -> None:
    assert root_card.hebrew_shape("כתב", "VERB", "כתב") == ["", "", "write", 0, 0]
    assert root_card.hebrew_shape("כתב", "VERB", "") == 0
    assert root_card.hebrew_shape("כתב", "VERB", "רשם") == 0, "another root: no meaning"
    assert root_card.noun_root("כתב", "VERB") == ""
    # A name is no noun, and nothing is looked up for it.
    assert root_card.hebrew_shape("מכתב", "PROPN", "") == 0


@pytest.mark.usefixtures("lexicons")
def test_only_a_transparent_noun_joins_a_family() -> None:
    assert root_card.family_root("מכתב", "NOUN", "", "he") == "כתב"
    assert root_card.family_root("חשבון", "NOUN", "", "he") == "", "not under think"
    # A verb is counted as it was, under the page's root.
    assert root_card.family_root("כתב", "VERB", "כתב", "he") == "כתב"


@pytest.mark.usefixtures("lexicons")
def test_a_root_with_two_meanings_keeps_a_family_to_one() -> None:
    assert not root_card.same_sense("he", "ערבות", "ערב", "ערב")
    assert root_card.same_sense("he", "ערבות", "ערב2", "ערב"), "guarantee, vouch shares a word"
    assert root_card.same_sense("he", "ערבות", "לא-בלקסיקון", "ערב"), "unknown is not against"
    assert not root_card.same_sense("ru", "летать", "летний", "лет")


@pytest.mark.usefixtures("lexicons")
def test_a_russian_word_carries_its_root_variants_and_prefixes() -> None:
    assert root_card.russian_shape("приходить", "VERB") == [
        [["ход", ["хож", "ш"], "go"]],
        ["при"],
        0,
        1,
    ]
    # ё folded: the lexicon's самолёт is found from самолет, and its лёт is лет.
    shape = root_card.russian_shape("самолет", "NOUN")
    assert shape and shape[0][1][0] == "лет"
    assert root_card.russian_shape("приходить", "PROPN") == 0
    assert root_card.family_root("пароход", "NOUN", "", "ru") == "пар ход"
    assert root_card.family_root("самолёт", "NOUN", "", "ru") == "", "partial is not counted"


# --- The page ------------------------------------------------------------------------------


def _segment() -> Segment:
    return Segment(id="0000.000-aaaaaa", block_id="b0000", block_index=0, index=0, text="x")


def _page(tmp_path: Path, language: str, tokens: list[Token]) -> dict[str, object]:
    from targum.render import render

    segment = _segment().model_copy(update={"text": " ".join(t.surface for t in tokens)})
    segmented = SegmentedDocument(
        document_hash="h", language=language, segmenter="fake/1", segments=[segment]
    )
    document = Document(source="m", title="T", language=language, blocks=[], content_hash="h")
    translation = Translation(
        name="English",
        document_hash="h",
        source_language=language,
        target_language="en",
        provider="null",
        segments={segment.id: "tr"},
    )
    annotation = Annotation(
        document_hash="h",
        language=language,
        annotator="t",
        method="frequency",
        method_note="note",
        tokens={segment.id: tokens},
    )
    html = render(document, segmented, [translation], tmp_path / "r", annotation=annotation)[
        0
    ].read_text(encoding="utf-8")
    found = re.search(r'id="targum-data"[^>]*>(.*?)</script>', html, re.S)
    assert found
    data = json.loads(found.group(1))
    assert isinstance(data, dict)
    return data


def _hebrew_tokens() -> list[Token]:
    return [
        Token(start=0, end=4, surface="מכתב", lemma="מכתב", band=2, pos="NOUN"),
        Token(start=5, end=10, surface="טלפון", lemma="טלפון", band=2, pos="NOUN"),
        Token(
            start=11,
            end=14,
            surface="כתב",
            lemma="כתב",
            band=2,
            pos="VERB",
            root="כתב",
            binyan="פעל",
        ),
        Token(start=15, end=18, surface="בית", lemma="בית", band=1, pos="NOUN"),
    ]


def test_a_page_with_no_lexicon_is_the_page_it_was(tmp_path: Path) -> None:
    data = _page(tmp_path, "he", _hebrew_tokens())
    extensions = data["extensions"]
    assert isinstance(extensions, dict)
    assert "shapes" not in extensions and "morphemes" not in extensions
    assert extensions["roots"] == ["", "", "כתב", ""], "a noun still has no root of its own"


@pytest.mark.usefixtures("lexicons")
def test_a_hebrew_page_carries_the_rows_of_its_own_words(tmp_path: Path) -> None:
    data = _page(tmp_path, "he", _hebrew_tokens())
    extensions = data["extensions"]
    assert isinstance(extensions, dict)
    assert data["lemmas"] == ["מכתב", "טלפון", "כתב", "בית"]
    assert extensions["shapes"] == [
        ["כתב", "מִקְטָל", "write", 0, 1],
        ["", "", "", 1, 0],
        ["", "", "write", 0, 0],
        0,
    ]
    # The roots the card already draws are a verb's alone, until the card is built.
    assert extensions["roots"] == ["", "", "כתב", ""]
    assert "morphemes" not in extensions
    # Only the words on the page: no row of the lexicon's other words rides along.
    page = json.dumps(data, ensure_ascii=False)
    assert "קֶטְלוֹן" not in page and "guarantee" not in page


@pytest.mark.usefixtures("lexicons")
def test_a_russian_page_carries_its_words_morphemes(tmp_path: Path) -> None:
    data = _page(
        tmp_path,
        "ru",
        [
            Token(start=0, end=5, surface="выход", lemma="выход", band=2, pos="NOUN"),
            Token(start=6, end=9, surface="дом", lemma="дом", band=1, pos="NOUN"),
        ],
    )
    extensions = data["extensions"]
    assert isinstance(extensions, dict)
    assert extensions["morphemes"] == [[[["ход", [], "go"]], ["вы"], 0, 1], 0]
    assert "shapes" not in extensions


# --- The family line -------------------------------------------------------------------------


def _text(folder: Path, tokens: list[dict[str, object]], language: str = "he") -> Path:
    folder.mkdir(parents=True)
    segment = _segment()
    segment = segment.model_copy(update={"text": " ".join(str(t["surface"]) for t in tokens)})
    document = SegmentedDocument(
        document_hash="doc", language=language, segmenter="test", segments=[segment]
    )
    (folder / "segments.json").write_text(document.model_dump_json(), encoding="utf-8")
    (folder / "annotation.json").write_text(
        json.dumps({"tokens": {segment.id: tokens}}), encoding="utf-8"
    )
    (folder / "document.json").write_text(
        json.dumps({"source": "test:doc", "content_hash": "doc", "language": language}),
        encoding="utf-8",
    )
    (folder / "reader").mkdir()
    (folder / "reader" / "sec-0001.html").write_text("", encoding="utf-8")
    return folder


def _word(lemma: str, pos: str, root: str = "") -> dict[str, object]:
    return {"start": 0, "end": 1, "surface": lemma, "lemma": lemma, "pos": pos, "root": root}


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    occurrences._cached.cache_clear()


@pytest.mark.usefixtures("lexicons")
def test_the_family_line_counts_nouns_too(tmp_path: Path) -> None:
    folder = _text(
        tmp_path / "t",
        [
            _word("כתב", "VERB", "כתב"),
            _word("מכתב", "NOUN"),
            _word("חשבון", "NOUN"),
            _word("ערב", "NOUN"),
            _word("ערבות", "NOUN"),
        ],
    )

    def folder_for(document: str) -> tuple[Path, str] | None:
        return (folder, "he") if document == "doc" else None

    finished = [("doc", "1", 10)]
    assert occurrences.family("כתב", finished, folder_for, "he") == ["כתב", "מכתב"]
    assert occurrences.family("חשב", finished, folder_for, "he") == [], "partly is not counted"
    # One root string, two meanings: the card asking for ערבות meets no evening.
    assert occurrences.family("ערב", finished, folder_for, "he", "ערבות") == ["ערבות"]
    assert occurrences.family("ערב", finished, folder_for, "he") == ["ערב", "ערבות"]


def test_a_lexicon_arriving_is_a_cache_miss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _text(tmp_path / "t", [_word("מכתב", "NOUN")])
    before = occurrences.text_occurrences(folder)
    assert before is not None and before.roots == {}
    file = tmp_path / "roots-he.json"
    file.write_text(json.dumps(HEBREW, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("TARGUM_ROOTS_HE", str(file))
    after = occurrences.text_occurrences(folder)
    assert after is not None and after.roots == {"מכתב": "כתב"}


@pytest.mark.usefixtures("lexicons")
def test_a_russian_family_is_counted_by_root_morph(tmp_path: Path) -> None:
    folder = _text(
        tmp_path / "t",
        [
            _word("приходить", "VERB"),
            _word("пароход", "NOUN"),
            _word("летать", "VERB"),
            _word("летний", "ADJ"),
        ],
        language="ru",
    )

    def folder_for(document: str) -> tuple[Path, str] | None:
        return (folder, "ru") if document == "doc" else None

    finished = [("doc", "1", 10)]
    assert occurrences.family("ход", finished, folder_for, "ru", "выход") == [
        "приходить",
        "пароход",
    ]
    assert occurrences.family("лет", finished, folder_for, "ru", "летать") == ["летать"]


# --- The Mishkal list's counts (design.md §12, 2026-11-02) -----------------------------------


@pytest.mark.usefixtures("lexicons")
def test_a_nouns_mishkal_on_the_reviewed_list_is_counted_where_it_was_met(
    tmp_path: Path,
) -> None:
    """The pattern the card is given (`hebrew_shape`), kept in the occurrences cache: a
    pattern off the list (קֶטְלוֹן) and a verb's binyan are not counted, nor is a word the
    annotation gave a root of its own."""
    folder = _text(
        tmp_path / "t",
        [
            _word("מכתב", "NOUN"),
            _word("מכתב", "NOUN"),
            _word("ערבות", "NOUN"),
            _word("חשבון", "NOUN"),
            _word("נזיר", "NOUN", "נזל"),
            _word("כתב", "VERB", "כתב"),
        ],
    )
    counted = occurrences.text_occurrences(folder)
    assert counted is not None
    assert set(counted.mishkalim) == {"miqtal|מכתב", "qatlut|ערבות"}
    occurrences._cached.cache_clear()
    assert occurrences.text_occurrences(folder) == counted, "read back from the cache"

    def folder_for(document: str) -> tuple[Path, str] | None:
        return (folder, "he") if document == "doc" else None

    assert occurrences.mishkal_forms([("doc", "1", 10)], folder_for, "he") == {
        "miqtal": {"מכתב": 2},
        "qatlut": {"ערבות": 1},
    }
    assert occurrences.mishkal_forms([("doc", "9", 10)], folder_for, "he") == {}


def test_with_no_lexicon_no_mishkal_is_counted(tmp_path: Path) -> None:
    folder = _text(tmp_path / "t", [_word("מכתב", "NOUN")])
    counted = occurrences.text_occurrences(folder)
    assert counted is not None and counted.mishkalim == {}
