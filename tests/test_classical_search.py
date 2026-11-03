"""Finding and naming the classical shelf (beta review 2026-11-03, part 2).

The Mishneh Torah is found by the names people call it (AS-20); a search for the Talmud
is told it is not carried (AS-08); a tractate's contents page says "Tractate", not
"Book" (AS-10); and a classical text's headings are labels, not words (AS-23).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from test_contents_page import built, manifest_of

from targum import catalogue
from targum.catalogue import Entry, Kind
from targum.models import (
    Annotation,
    BlockKind,
    Document,
    Segment,
    SegmentedDocument,
    Token,
    Translation,
)
from targum.render import render
from targum.render.builder import contents_page
from targum.search import Matcher, asks_for_talmud

YESODEI = Entry(
    id="mt-yesodei-hatorah",
    title="הלכות יסודי התורה",
    author="משה בן מימון, 1180 · ספר המדע",
    language="he",
    source="sefaria:Mishneh Torah, Foundations of the Torah",
    blurb="Where the code begins.",
    words=7676,
    english="Laws of the Foundations of the Torah",
    kind=Kind.prose,
)


@pytest.mark.parametrize("query", ["Rambam", "Maimonides", "Mishneh Torah", "רמב״ם", "משנה תורה"])
def test_the_mishneh_torah_is_found_by_its_names(query: str) -> None:
    match = Matcher.of(query)
    assert match.score(
        YESODEI.title, YESODEI.english, YESODEI.author, YESODEI.blurb, YESODEI.also_called
    )


@pytest.mark.parametrize(
    "line", ["Talmud", "Bava Kamma 2a", "berakhot 2b", "Gemara", "ברכות ב.", "דף יומי", "תלמוד"]
)
def test_a_search_for_the_talmud_is_known(line: str) -> None:
    assert asks_for_talmud(line)


@pytest.mark.parametrize("line", ["Berakhot", "Psalm 23", "Genesis 1", "שלום", "Toy Story 2"])
def test_other_searches_are_not_the_talmud(line: str) -> None:
    assert not asks_for_talmud(line)


def test_a_tractates_contents_page_says_tractate(tmp_path: Path) -> None:
    manifest = manifest_of(built(tmp_path / "book-he"))
    manifest["source"] = "sefaria:Mishnah Berakhot"
    page = contents_page(manifest, {})
    assert "Tractate" in page and ">Book<" not in page


def test_a_classical_heading_is_no_word(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(catalogue, "CATALOGUE", [])
    heading = Segment(
        id="h1",
        block_id="h1",
        block_index=0,
        index=0,
        kind=BlockKind.heading,
        level=1,
        text="משנה ברכות א׳",
    )
    verse = Segment(id="s1", block_id="b1", block_index=1, index=0, text="מאימתי קורין")
    segmented = SegmentedDocument(
        document_hash="d", language="he", segmenter="t/1", segments=[heading, verse]
    )
    translation = Translation(
        name="English",
        document_hash="d",
        source_language="he",
        target_language="en",
        provider="null",
        segments={"h1": "Mishnah Berakhot 1", "s1": "From when"},
    )

    texts = {"h1": heading.text, "s1": verse.text}

    def token(sid: str, start: int, end: int, lemma: str, pos: str) -> Token:
        return Token(
            start=start, end=end, lemma=lemma, pos=pos, surface=texts[sid][start:end], band=3
        )

    annotation = Annotation(
        document_hash="d",
        language="he",
        annotator="t/1",
        method="test",
        method_note="",
        tokens={
            "h1": [token("h1", 0, 4, "שנה", "VERB"), token("h1", 5, 10, "ברכה", "NOUN")],
            "s1": [token("s1", 0, 7, "מאימתי", "ADV"), token("s1", 8, 12, "קרא", "VERB")],
        },
    )

    def rows(source: str) -> dict[str, list[list[int]]]:
        document = Document(
            source=source, title="ברכות", language="he", blocks=[], content_hash="d"
        )
        out = tmp_path / source.replace(":", "-")
        page = render(document, segmented, [translation], out, annotation=annotation)[0]
        html = page.read_text(encoding="utf-8")
        found = re.search(r'"h1": (\[\[.*?\]\])', html)
        return {"h1": json.loads(found.group(1)) if found else []}

    assert rows("sefaria:Mishnah Berakhot")["h1"] == []
    assert rows("memory")["h1"], "a heading elsewhere keeps its words"
