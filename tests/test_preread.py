"""The words to know before a chapter (targum-internal#97), behind `TARGUM_PREREAD`.

Three things: which words and in what order (`render/preread.py`, on the printed page's
rule); that a page written with the switch off is byte for byte the page it was; and that
the page's script takes off what the reader already knows (`assets/preread.js`).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from test_print import VERSE_1, VERSE_2, _folder
from test_render import OUTBOUND

from targum.models import (
    Annotation,
    BlockKind,
    Document,
    Glossary,
    SegmentedDocument,
    Token,
    Translation,
    Vocalization,
    glossaries_in,
    read_artifact,
)
from targum.render import preread as preread_module
from targum.render import render
from targum.render.preread import CARRIED, SHOWN, chapter_words

HARNESS = Path(__file__).resolve().parent / "js" / "preread.js"


def _token(lemma: str, band: int, pos: str = "NOUN") -> Token:
    return Token(start=0, end=1, surface=lemma, lemma=lemma, band=band, pos=pos)


def _english(tokens: dict[str, list[Token]], entries: dict[str, str]) -> list[Any]:
    """The words `chapter_words` gives for these tokens against an English glossary."""
    translation = Translation(
        name="t",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="fake",
        segments={},
    )
    annotation = Annotation(
        document_hash="h",
        language="he",
        annotator="fake/1",
        method="frequency",
        method_note="",
        tokens=tokens,
    )
    glossary = Glossary(
        source_language="he", target_language="en", provider="fake", entries=entries
    )
    return chapter_words(list(tokens), annotation, {"en": glossary}, translation, [translation])


def test_the_commonest_hard_word_comes_first_and_a_tie_keeps_the_chapters_order() -> None:
    words = _english(
        {
            "a": [_token("ים", 5), _token("עץ", 4), _token("בית", 1)],
            "b": [_token("עץ", 4), _token("ספר", 6), _token("עץ", 4), _token("ים", 5)],
        },
        {"ים": "sea", "עץ": "tree; wood", "ספר": "book", "בית": "house"},
    )
    assert [(w.lemma, w.meaning, w.count) for w in words] == [
        ("עץ", "tree", 3),
        ("ים", "sea", 2),
        ("ספר", "book", 1),
    ]


def test_a_name_a_word_with_no_meaning_and_an_easy_word_are_not_on_it() -> None:
    words = _english(
        {"a": [_token("דוד", 6, pos="PROPN"), _token("נחל", 5), _token("אב", 2)]},
        {"דוד": "David", "אב": "father"},
    )
    assert words == []


def test_it_carries_a_bounded_number() -> None:
    lemmas = [f"מילה{n}" for n in range(CARRIED + 20)]
    words = _english({"a": [_token(lemma, 5) for lemma in lemmas]}, dict.fromkeys(lemmas, "a"))
    assert len(words) == CARRIED
    assert SHOWN < CARRIED


def test_no_annotation_or_no_meanings_is_no_list() -> None:
    translation = Translation(
        name="t",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="fake",
        segments={},
    )
    assert chapter_words(["a"], None, {}, translation, [translation]) == []


# -- the page ------------------------------------------------------------------------


def _reader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, on: bool) -> dict[str, str]:
    """Jonah 1–2 written as a reader, with the switch as asked; each file's HTML."""
    if on:
        monkeypatch.setenv(preread_module.ENV, "1")
    else:
        monkeypatch.delenv(preread_module.ENV, raising=False)
    where = tmp_path / ("on" if on else "off")
    folder = _folder(
        where,
        [
            ("יונה א׳", "Jonah 1", BlockKind.heading, ""),
            (VERSE_1, "Now the word", BlockKind.verse, "Jonah 1:1"),
            (VERSE_2, "Arise", BlockKind.verse, "Jonah 1:2"),
            ("יונה ב׳", "Jonah 2", BlockKind.heading, ""),
            (VERSE_1, "Again", BlockKind.verse, "Jonah 2:1"),
        ],
        scripture=True,
    )
    document = read_artifact(Document, folder / "document.json")
    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    assert document is not None and segmented is not None
    translations = [
        found
        for path in sorted((folder / "translations").glob("*.json"))
        if (found := read_artifact(Translation, path)) is not None
    ]
    written = render(
        document,
        segmented,
        translations,
        where / "reader",
        annotation=read_artifact(Annotation, folder / "annotation.json"),
        glossaries=glossaries_in(folder),
        vocalization=read_artifact(Vocalization, folder / "vocalization.json"),
    )
    return {path.name: path.read_text(encoding="utf-8") for path in written}


#: The three pieces the switch adds to a page, and nothing else.
ADDED = (
    re.compile(r"<style>\.preread \{.*?</style>\n?", re.S),
    re.compile(r'<details class="preread".*?</details>\n?', re.S),
    re.compile(r'<script>\(function \(\) \{\n  "use strict";\n  var box = .*?</script>\n?', re.S),
)


def test_with_the_switch_off_a_page_carries_none_of_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, html in _reader(tmp_path, monkeypatch, on=False).items():
        assert "preread" not in html, name
        assert "Words to know first" not in html, name


def test_the_switch_adds_the_list_its_style_and_its_script_and_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Off is the page as it was: take the three pieces out of a page written with the
    switch on, and what is left is the page written with it off, byte for byte."""
    off = _reader(tmp_path, monkeypatch, on=False)
    on = _reader(tmp_path, monkeypatch, on=True)
    assert off.keys() == on.keys()
    changed = 0
    for name, html in on.items():
        rest = html
        for piece in ADDED:
            rest, n = piece.subn("", rest, count=1)
            changed += n
        assert rest == off[name], name
    # The first chapter's page carries all three; the second has no annotated words and
    # the contents page no words at all, so neither carries anything.
    assert changed == 3
    assert "preread" not in on["sec-0002.html"] and "preread" not in on["index.html"]


def test_the_list_is_the_chapters_hard_words_with_what_they_mean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    html = _reader(tmp_path, monkeypatch, on=True)["sec-0001.html"]
    block = re.search(r'<details class="preread".*?</details>', html, re.S)
    assert block is not None
    rows = re.findall(
        r'<li data-lemma="([^"]+)"( hidden)?><span class="preread-form" lang="he" dir="rtl">'
        r'([^<]+)</span><span class="preread-meaning" lang="en" dir="ltr">([^<]+)</span>'
        r'<span class="preread-times" dir="ltr">([^<]*)</span></li>',
        block.group(0),
    )
    # דבר twice, then קום under its citation form; the verb היה is too easy and the name
    # יונה is a name.
    assert rows == [("דבר", "", "דָּבָר", "word", "2×"), ("קום", "", "לָקוּם", "to rise", "")]
    assert f'data-shown="{SHOWN}"' in block.group(0)
    assert re.search(r'id="preread-total">2</b>', block.group(0))
    # Folded: a reader opens it.
    assert '<details class="preread" id="preread" open' not in html
    # Before the text, not after it.
    assert html.index('id="preread"') < html.index('class="pair')


def test_a_page_with_the_list_still_fetches_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    html = _reader(tmp_path, monkeypatch, on=True)["sec-0001.html"]
    for position in (r'src\s*=\s*["\']', r"url\(", r'<link[^>]+href\s*=\s*["\']'):
        assert not re.search(position + r"(https?:)?//", html, re.I)
    for match in re.finditer(r"https?://[^\s\"'\\)]+", html):
        assert match.group(0).startswith(OUTBOUND), match.group(0)
    script = (Path(preread_module.__file__).parent / "assets" / "preread.js").read_text()
    assert "fetch(" not in script and "XMLHttpRequest" not in script


# -- the script ----------------------------------------------------------------------

KNOWN = 9


def run(**payload: Any) -> dict[str, Any]:
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    where = Path(subprocess.run(["mktemp"], capture_output=True, text=True).stdout.strip())
    where.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    try:
        done = subprocess.run(
            ["node", str(HARNESS), str(where)], capture_output=True, text=True, timeout=60
        )
    finally:
        where.unlink(missing_ok=True)
    assert done.returncode == 0, done.stderr
    answer: dict[str, Any] = json.loads(done.stdout)
    return answer


def test_a_word_the_reader_knows_comes_off_and_the_next_comes_up() -> None:
    seen = run(
        rows=["ים", "עץ", "ספר", "נחל"],
        shown=2,
        vocab={"ים": {"status": KNOWN}, "עץ": {"status": 2}},
    )["before"]
    # Still learning is still on it; known is not; the third word takes the place.
    assert seen == {"on": ["עץ", "ספר"], "total": "2", "drawn": True}


def test_a_word_put_aside_comes_off_too() -> None:
    seen = run(rows=["ים", "עץ"], shown=40, vocab={"עץ": {"status": 0}})["before"]
    assert seen["on"] == ["ים"] and seen["total"] == "1"


def test_nothing_left_is_nothing_drawn() -> None:
    seen = run(rows=["ים"], vocab={"ים": {"status": KNOWN}})["before"]
    assert seen == {"on": [], "total": "0", "drawn": False}


def test_words_the_account_hands_over_are_taken_off_as_they_arrive() -> None:
    answer = run(rows=["ים", "עץ"], vocab={}, synced={"ים": {"status": KNOWN}})
    assert answer["before"]["on"] == ["ים", "עץ"]
    assert answer["after"] == {"on": ["עץ"], "total": "1", "drawn": True}
