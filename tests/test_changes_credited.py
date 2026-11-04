"""A text whose licence asks for changes to be indicated says what we changed (David,
2026-11-03; design.md §12).

CC BY 4.0, CC BY-SA 4.0 and CC BY-NC(-SA) 4.0 ask for an indication of changes, and the
3.0 deeds ask an adaptation to say what it adapted. Every such text carries "Vowel points
and notes added by targum" in its reader's foot and on its Library page. Public domain and
CC0 owe nothing and say nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from targum import catalogue
from targum.catalogue import Entry, Kind
from targum.licensing import changes_owed
from targum.models import Document, SegmentedDocument, Translation
from targum.render import render
from targum.render.builder import edition_credit, text_credit_in, text_page

CHANGED = "Vowel points and notes added by targum"


def row(licence: str) -> Entry:
    return Entry(
        id="berakhot",
        title="ברכות",
        author="Mishnah · Zeraim",
        language="he",
        source="sefaria:Mishnah Berakhot",
        blurb="The blessings.",
        words=5000,
        kind=Kind.prose,
        licence=licence,
        credit="Mishnah, ed. Example, via Sefaria",
    )


@pytest.mark.parametrize(
    "licence",
    [
        "CC BY 4.0",
        "CC-BY-SA 4.0",
        "CC BY-NC 4.0",
        "CC BY-NC-SA 4.0",
        "CC BY 3.0",
        "CC-BY",
        "CC-BY-SA",
        "Creative Commons Attribution 4.0 International",
    ],
)
def test_an_attribution_licence_owes_a_line_saying_we_changed_it(licence: str) -> None:
    assert changes_owed(licence)


@pytest.mark.parametrize(
    "licence",
    [
        "Public Domain",
        "CC0",
        "CC0 1.0",
        "Public Domain Mark 1.0",
        "targum",
        "",
        "CC BY-ND 4.0",
        "State of Israel — free use, attribution required",
    ],
)
def test_public_domain_and_cc0_owe_nothing(licence: str) -> None:
    assert not changes_owed(licence)


def test_the_edition_credit_carries_it_only_where_owed() -> None:
    owed = edition_credit(row("CC BY 4.0"))
    free = edition_credit(row("Public Domain"))
    assert owed is not None and owed.changed
    assert free is not None and not free.changed


def test_a_library_page_says_it_under_a_cc_by_edition(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(catalogue, "CATALOGUE", [row("CC BY 4.0")])
    html = text_page(row("CC BY 4.0"), "https://targum.page")
    edition = html[html.index('class="provenance edition"') :]
    assert CHANGED in edition[: edition.index("</section>")]


@pytest.mark.parametrize("licence", ["Public Domain", "CC0"])
def test_a_library_page_says_nothing_under_a_free_edition(
    monkeypatch: pytest.MonkeyPatch, licence: str
) -> None:
    monkeypatch.setattr(catalogue, "CATALOGUE", [row(licence)])
    assert CHANGED not in text_page(row(licence), "https://targum.page")


def test_the_russian_library_page_says_it_in_russian(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(catalogue, "CATALOGUE", [row("CC BY 4.0")])
    html = text_page(row("CC BY 4.0"), "https://targum.page", "ru")
    assert "Огласовки и пояснения добавлены targum" in html


def _reader(
    tmp_path: Path, segmented: SegmentedDocument, translation: Translation, name: str
) -> str:
    document = Document(
        source="sefaria:Mishnah Berakhot",
        title="ברכות",
        language="he",
        blocks=[],
        content_hash="abc123",
    )
    pages = render(document, segmented, [translation], tmp_path / name)
    html = pages[-1].read_text(encoding="utf-8")
    return html[html.index('id="credits"') :]


@pytest.mark.parametrize(("licence", "said"), [("CC BY 4.0", True), ("Public Domain", False)])
def test_a_readers_foot_says_it_beside_the_edition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    segmented: SegmentedDocument,
    translation: Translation,
    licence: str,
    said: bool,
) -> None:
    monkeypatch.setattr(catalogue, "CATALOGUE", [row(licence)])
    foot = _reader(tmp_path, segmented, translation, "r")
    assert "Hebrew from Mishnah, ed. Example, via Sefaria" in foot
    assert (f" · {CHANGED}</p>" in foot) is said


@pytest.mark.parametrize(("licence", "said"), [("CC BY-SA 4.0", "yes"), ("CC0 1.0", "")])
def test_a_find_that_joined_the_library_says_it_too(
    tmp_path: Path, licence: str, said: str
) -> None:
    (tmp_path / "credit.json").write_text(
        json.dumps({"outlet": "Example", "source": "https://example.org/a", "licence": licence}),
        encoding="utf-8",
    )
    credit = text_credit_in(tmp_path)
    assert credit is not None and credit["changed"] == said
