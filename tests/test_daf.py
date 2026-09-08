"""The Hebrew of a daf from Sefaria: the Mishnah, Rashi and Tosafot (targum-internal#193).

Three texts, one licence rule and one ordering contract. Everything here runs against
saved responses — the shapes Sefaria actually sends for `Mishnah Berakhot` in the Romm
edition and for `Rashi on Berakhot 2a` and `Tosafot on Berakhot 2a` in the Vilna
edition, trimmed — and against the tractate's index, so the network is never asked.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from targum.errors import TargumError
from targum.ingest.fetch import daf, load, sefaria
from targum.models import BlockKind, is_biblical, keeps_its_own_pointing

FIXTURES = Path(__file__).parent / "fixtures" / "sefaria"


def saved(name: str) -> dict[str, Any]:
    body = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return {"edition": body["versions"][0], "body": body, "licence": "Public Domain"}


def index() -> dict[str, Any]:
    return json.loads((FIXTURES / "berakhot-index.json").read_text(encoding="utf-8"))


def answering(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every URL the fetcher asks for, answered from the fixtures by what it names."""
    asked: list[str] = []

    def get(url: str) -> str:
        asked.append(url)
        if "raw/index" in url:
            return json.dumps(index())
        if "Rashi" in url:
            return (FIXTURES / "rashi-berakhot-2a.he.json").read_text(encoding="utf-8")
        if "Tosafot" in url:
            return (FIXTURES / "tosafot-berakhot-2a.he.json").read_text(encoding="utf-8")
        return (FIXTURES / "mishnah-berakhot-romm.he.json").read_text(encoding="utf-8")

    monkeypatch.setattr(daf, "get", get)
    return asked


# -- the Mishnah, in the daf's own edition ----------------------------------------------


def test_the_mishnah_arrives_a_perek_a_heading_and_a_mishnah_a_verse() -> None:
    document = daf.mishnah_document(saved("mishnah-berakhot-romm.he.json"), "Berakhot")
    headings = [b for b in document.blocks if b.kind == BlockKind.heading]
    verses = [b for b in document.blocks if b.kind == BlockKind.verse]
    assert len(headings) == 2 and len(verses) == 5 + 8, "two perakim of the fixture"
    assert headings[0].text.endswith(" א׳") and "ברכות" in headings[0].text
    assert verses[0].ref == "Mishnah Berakhot 1:1"
    assert verses[5].ref == "Mishnah Berakhot 2:1", "the count restarts with the perek"
    assert verses[0].text.startswith("מאימתי קורין את שמע")
    assert document.language == "he" and document.source == "sefaria:daf:Berakhot"
    assert all(block.language is None for block in document.blocks), "Hebrew, the document's"


def test_the_dafs_mishnah_is_not_the_shelfs_mishnah() -> None:
    """Romm, the Vilna printer, so the Mishnah is in the daf's own edition family — not
    Torat Emet, which the Mishnah shelf reads pointed and paired with Kulp's English."""
    assert daf.MISHNAH == "Mishnah, ed. Romm, Vilna 1913"
    assert sefaria.MISHNAH.hebrew != daf.MISHNAH
    assert sefaria.version_for("he", "Mishnah Berakhot") == sefaria.MISHNAH.hebrew


# -- the commentaries, a comment a block with its address -------------------------------


def test_a_commentary_keeps_every_comment_under_its_daf_line_and_number() -> None:
    document = daf.commentary_document(saved("rashi-berakhot-2a.he.json"), "Rashi", "Berakhot")
    headings = [b for b in document.blocks if b.kind == BlockKind.heading]
    comments = [b for b in document.blocks if b.kind == BlockKind.paragraph]
    assert [h.text for h in headings] == ["רש״י ברכות ב."], "one amud, in the printed notation"
    assert comments[0].ref == "Rashi on Berakhot 2a:1:1"
    assert comments[1].ref == "Rashi on Berakhot 2a:1:2", "two comments on the first line"
    assert comments[0].text.startswith("מאימתי קורין את שמע בערבין.")
    # Four of the twelve lines carry no comment; their numbers are still Sefaria's.
    lines = {int(c.ref.split(":")[1]) for c in comments}
    assert max(lines) == 12 and len(lines) == 8
    anchors = [daf.anchor_of(c.ref) for c in comments]
    assert all(anchor and anchor.daf == "2a" for anchor in anchors)
    assert document.source == "sefaria:Rashi on Berakhot" and document.language == "he"


def test_tosafot_reads_the_same_way() -> None:
    document = daf.commentary_document(saved("tosafot-berakhot-2a.he.json"), "Tosafot", "Berakhot")
    comments = [b for b in document.blocks if b.kind == BlockKind.paragraph]
    assert comments and comments[0].ref.startswith("Tosafot on Berakhot 2a:")
    assert document.title.startswith("תוספות")


def test_a_whole_commentary_is_amudim_of_lines_of_comments() -> None:
    body = json.loads((FIXTURES / "rashi-berakhot-2a.he.json").read_text(encoding="utf-8"))
    lines = body["versions"][0]["text"]
    # As the whole of `Rashi on Berakhot` arrives: 127 amudim counted from 1a, so the
    # first two are empty — 1a as one line with nothing on it, 1b as nothing at all —
    # then 2a's lines, then 2b. Neither empty amud gets a heading.
    body["versions"][0]["text"] = [[[]], [], lines, [["דיבור על ב:"]]]
    body["sections"] = []
    payload = {"edition": body["versions"][0], "body": body, "licence": "Public Domain"}
    document = daf.commentary_document(payload, "Rashi", "Berakhot")
    headings = [b.text for b in document.blocks if b.kind == BlockKind.heading]
    assert headings == ["רש״י ברכות ב.", "רש״י ברכות ב:"], (
        "an empty amud is skipped, its number is not"
    )
    last = [b for b in document.blocks if b.kind == BlockKind.paragraph][-1]
    assert last.ref == "Rashi on Berakhot 2b:1:1"


# -- the licence: public domain or nothing ----------------------------------------------


def test_the_licence_is_asserted_at_fetch_and_only_public_domain_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stricter than the shelf: `sefaria.USABLE` admits CC-BY and CC0, and a daf does
    not, because a daf is one object and a commentary under a licence that travels would
    carry it onto the whole page. The same rule `test_sharealike_stays_refused` pins for
    the shelf, pinned here for the daf."""
    body = json.loads((FIXTURES / "rashi-berakhot-2a.he.json").read_text(encoding="utf-8"))
    for licence in ("CC-BY", "CC0", "CC-BY-SA", "CC-BY-NC", ""):
        body["versions"][0]["license"] = licence
        monkeypatch.setattr(daf, "get", lambda url, body=body: json.dumps(body))
        with pytest.raises(TargumError, match="public domain or nothing"):
            load("sefaria:Rashi on Berakhot")
    for licence in ("Public Domain", "PD"):
        body["versions"][0]["license"] = licence
        monkeypatch.setattr(daf, "get", lambda url, body=body: json.dumps(body))
        assert load("sefaria:Rashi on Berakhot").blocks


def test_fill_in_missing_segments_is_never_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    """The API's own answer to a patchy version fills its gaps from other versions and
    reports the licence you asked for; the check cannot see it. So the gaps stay."""
    asked = answering(monkeypatch)
    load("sefaria:daf:Berakhot")
    load("sefaria:Rashi on Berakhot")
    load("sefaria:Tosafot on Berakhot")
    assert asked and all("fill_in_missing_segments" not in url for url in asked)
    assert any("Mishnah%20Berakhot" in url and "Romm" in url for url in asked)
    assert any("Rashi%20on%20Berakhot" in url and "Vilna%20Edition" in url for url in asked)


def test_a_shape_this_does_not_read_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    body = json.loads((FIXTURES / "rashi-berakhot-2a.he.json").read_text(encoding="utf-8"))
    body["textDepth"] = 2
    monkeypatch.setattr(daf, "get", lambda url: json.dumps(body))
    with pytest.raises(TargumError, match="not shaped"):
        load("sefaria:Rashi on Berakhot")


def test_the_daf_texts_go_through_the_hebrew_pipeline_and_are_not_scripture() -> None:
    """All blocks tagged `he`, banded against modern Hebrew rather than the Tanakh, and
    pointed by the pipeline: Romm and Vilna print no vowels, so an edition that "keeps
    its own pointing" would keep none."""
    sources = ("sefaria:daf:Berakhot", "sefaria:Rashi on Berakhot", "sefaria:Tosafot on Berakhot")
    for source in sources:
        assert not is_biblical(source), source
        assert not keeps_its_own_pointing(source), source
    assert is_biblical("sefaria:Ruth") and keeps_its_own_pointing("sefaria:Ruth")
    assert keeps_its_own_pointing("sefaria:Mishnah Berakhot"), "the shelf's Mishnah is pointed"


# -- anchors, and the order of a daf ----------------------------------------------------


def test_every_ref_reads_back_as_its_anchor() -> None:
    mishnah = daf.anchor_of("Mishnah Berakhot 2:3")
    assert mishnah == daf.Anchor("mishnah", "Berakhot", perek=2, mishnah=3)
    comment = daf.anchor_of("Tosafot on Berakhot 13a:4:2")
    assert comment == daf.Anchor("comment", "Berakhot", who="Tosafot", daf="13a", line=4, comment=2)
    gemara = daf.anchor_of("Berakhot 13a:16")
    assert gemara == daf.Anchor("gemara", "Berakhot", daf="13a", line=16)
    assert daf.anchor_of("Berakhot 13a:16/1") == daf.Anchor(
        "gemara", "Berakhot", daf="13a", line=16, mishnah=1
    )
    assert daf.anchor_of("Ruth 1:1") is None and daf.anchor_of("") is None


def test_the_perek_table_comes_from_the_index() -> None:
    perakim = daf.perakim_from_index(index(), "Berakhot")
    assert len(perakim.ranges) == 9
    assert perakim.perek_of("2a", 1) == 1
    assert perakim.perek_of("13a", 15) == 1 and perakim.perek_of("13a", 16) == 2, (
        "a perek ends mid-daf, where the index says"
    )
    assert perakim.perek_of("64a", 15) == 9 and perakim.perek_of("64b", 1) == 9


def test_a_mishnah_stands_before_the_gemara_on_it_and_a_perek_boundary_holds() -> None:
    """The ordering contract with #192. A perek's last line of Gemara sorts before the
    next perek's first mishnah, which sorts before that perek's first line of Gemara,
    though both lines are on the same daf; and a comment sits beside its line."""
    perakim = daf.perakim_from_index(index(), "Berakhot")
    refs = [
        "Berakhot 13a:16",
        "Mishnah Berakhot 2:1",
        "Rashi on Berakhot 13a:15:1",
        "Berakhot 13a:15",
        "Mishnah Berakhot 1:5",
        "Berakhot 2a:1",
        "Mishnah Berakhot 1:1",
        "Berakhot 12b:3/5",
    ]
    anchors = [daf.anchor_of(ref) for ref in refs]
    assert all(anchors)
    ordered = sorted(refs, key=lambda ref: daf.reading_key(daf.anchor_of(ref), perakim))  # type: ignore[arg-type]
    assert ordered == [
        "Mishnah Berakhot 1:1",
        "Berakhot 2a:1",
        "Berakhot 13a:15",
        "Rashi on Berakhot 13a:15:1",
        "Mishnah Berakhot 1:5",
        "Berakhot 12b:3/5",
        "Mishnah Berakhot 2:1",
        "Berakhot 13a:16",
    ]


def test_daf_notation() -> None:
    assert daf.daf_index("2a") == 3 and daf.daf_index("2b") == 4 and daf.daf_index("13a") == 25
    assert daf.hebrew_daf("2a") == "ב." and daf.hebrew_daf("2b") == "ב:"
    assert daf.hebrew_daf("13a") == "יג."
    with pytest.raises(TargumError):
        daf.daf_index("two")


def test_the_registry_reaches_all_three_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    answering(monkeypatch)
    assert load("sefaria:daf:Berakhot").source == "sefaria:daf:Berakhot"
    assert load("sefaria:Rashi on Berakhot").title.startswith("רש״י")
    assert load("sefaria:Tosafot on Berakhot").title.startswith("תוספות")
    with pytest.raises(TargumError, match="No tractate"):
        load("sefaria:daf:")


def test_a_commentary_on_the_tanakh_is_not_a_commentary_on_a_daf() -> None:
    """Rashi wrote on the Chumash too, and `<Who> on <Name>` claimed that as well.

    It sent `Rashi on Genesis` here, where the pinned edition is the Vilna — which
    exists for tractates and not for the Chumash — and the reader was told "Sefaria has
    no 'Vilna Edition' of Rashi on Genesis". True, and about the wrong thing: what is
    missing is a reader for a commentary numbered by chapter and verse, where a verse
    carries several comments (targum-internal#200).
    """
    assert daf.commentary_of("Rashi on Berakhot") == ("Rashi", "Berakhot")
    assert daf.commentary_of("Tosafot on Bava Metzia") == ("Tosafot", "Bava Metzia")
    for book in ("Genesis", "Song of Songs", "Isaiah"):
        assert daf.commentary_of(f"Rashi on {book}") is None, book


def test_a_commentary_on_the_tanakh_is_refused_in_its_own_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """And not for a missing edition of a book that has several."""

    def never(url: str) -> str:
        raise AssertionError(f"asked Sefaria about a commentary it cannot read: {url}")

    monkeypatch.setattr(sefaria, "get", never)
    with pytest.raises(TargumError, match="does not read Rashi on the Tanakh yet") as refused:
        sefaria.SefariaFetcher().load("Rashi on Genesis")
    assert "Rashi on Berakhot" in (refused.value.hint or ""), "it says what it does read"
