"""The licence on a catalogue row comes from what the source says, family by family, and
a source that says nothing is left empty rather than assumed (targum-internal#115)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from targum.licensing import Standing, verdict


@pytest.fixture(scope="module")
def backfill():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "backfill_licences", Path(__file__).parent.parent / "scripts" / "backfill_licences.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before it runs: a dataclass under `from __future__ import annotations`
    # looks its module up in `sys.modules` to resolve the strings.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_targums_own_writing_owes_nobody_anything() -> None:
    """The dialogues are written for targum. Not public domain, and nothing travels
    with them: `free` is the standing that says so, and empty would say unknown."""
    call = verdict("targum")
    assert call.standing is Standing.free and call.exportable and not call.attribution
    assert verdict("targum (own work)").standing is Standing.free
    assert verdict("targumim press").standing is Standing.unknown, "a name is not the word"


def test_a_news_page_is_read_off_its_own_footer(backfill) -> None:  # type: ignore[no-untyped-def]
    html = '<a href="https://creativecommons.org/licenses/by/4.0/">CC</a>'
    terms = backfill.from_page("https://he.wikinews.org/wiki/x", html)
    assert terms.licence == "CC BY 4.0" and terms.credit == "Wikinews"
    assert terms.licence_url == "https://creativecommons.org/licenses/by/4.0/"
    assert (
        backfill.from_page(
            "https://he.globalvoices.org/x", "by-sa/3.0 creativecommons.org/licenses/by-sa/3.0/"
        )
        is not None
    )
    assert backfill.from_page("https://he.wikinews.org/wiki/x", "<p>no licence here</p>") is None


def test_a_sefaria_edition_is_read_off_the_api_field_the_fetcher_refuses_on(backfill) -> None:  # type: ignore[no-untyped-def]
    asked: list[str] = []

    def fetch(url: str) -> str:
        asked.append(url)
        return json.dumps(
            {
                "versions": [
                    {
                        "versionTitle": "Tanach with Ta'amei Hamikra",
                        "license": "Public Domain",
                        "versionSource": "http://www.tanach.us/Tanach.xml",
                    }
                ]
            }
        )

    terms = backfill.terms_for("sefaria:Ruth", fetch, Path("/nowhere"))
    assert terms.licence == "Public Domain" and terms.rule == "sefaria"
    assert terms.credit == "Tanach with Ta'amei Hamikra, via Sefaria"
    assert terms.licence_url == "http://www.tanach.us/Tanach.xml"
    assert len(asked) == 1 and "Ruth%201%3A1" in asked[0] and "hebrew|Tanach" in asked[0]


def test_one_verse_is_asked_whatever_shape_the_reference_takes(backfill) -> None:  # type: ignore[no-untyped-def]
    """The parasha rows are verse ranges and Bikkurim is a chapter range; a range is not
    a reference the texts API answers, and one verse is enough to read the licence."""
    assert backfill.first_verse("Ruth") == "Ruth 1:1"
    assert backfill.first_verse("Song of Songs") == "Song of Songs 1:1"
    assert backfill.first_verse("Mishnah Bikkurim 1-3") == "Mishnah Bikkurim 1:1"
    assert backfill.first_verse("Genesis 6:9-11:32") == "Genesis 6:9"
    assert backfill.first_verse("Genesis 37:1-40:23; Numbers 7:1-17") == "Genesis 37:1"
    assert backfill.first_verse("Exodus 21:1-24:18, 30:11-16") == "Exodus 21:1"
    assert backfill.first_verse("Mishneh Torah, Repentance") == "Mishneh Torah, Repentance 1:1"


def test_a_video_carries_its_curation_record_and_a_dialogue_is_targums_own(  # type: ignore[no-untyped-def]
    backfill, tmp_path: Path
) -> None:
    (tmp_path / "abc").mkdir()
    (tmp_path / "abc" / "video.json").write_text(
        json.dumps({"credit": "Khan Academy Hebrew", "licence": "CC BY 3.0", "licence_url": "u"}),
        encoding="utf-8",
    )
    never = lambda url: pytest.fail(f"fetched {url}")  # noqa: E731
    video = backfill.terms_for("video:abc", never, tmp_path)
    assert (video.licence, video.credit, video.licence_url) == (
        "CC BY 3.0",
        "Khan Academy Hebrew",
        "u",
    )
    assert backfill.terms_for("video:missing", never, tmp_path) is None
    own = backfill.terms_for("dialogue:01-nice-to-meet-you", never, tmp_path)
    assert own.licence == "targum" and verdict(own.licence).standing is Standing.free
    ben = backfill.terms_for("https://benyehuda.org/read/123", never, tmp_path)
    assert ben.licence == "Public Domain" and ben.credit == "Project Ben-Yehuda"


def test_a_wikisource_page_that_says_nothing_is_left_empty(backfill) -> None:  # type: ignore[no-untyped-def]
    """Seven pages on the shelf carry no licence template. `promote.py` calls the whole
    fetcher public domain by selection; this refuses to write that down as the page's
    own claim."""
    assert backfill.wikisource_terms("{{כוזרי כותרת}} {{טקסט מנוקד}} אָמַר") is None
    assert backfill.wikisource_terms("{{נחלת הכלל}} text").licence == "Public Domain"
    assert backfill.wikisource_terms("{{CC-BY-SA-3.0}} text").licence == "CC BY-SA 3.0"

    def fetch(url: str) -> str:
        assert "wikisource.org/w/api.php" in url
        return json.dumps(
            {"query": {"pages": [{"revisions": [{"slots": {"main": {"content": "plain"}}}]}]}}
        )

    assert backfill.terms_for("wikisource:he:מגילת העצמאות", fetch, Path("/nowhere")) is None


def test_an_unknown_family_is_none_rather_than_guessed(backfill) -> None:  # type: ignore[no-untyped-def]
    never = lambda url: pytest.fail(f"fetched {url}")  # noqa: E731
    assert backfill.terms_for("https://example.org/article", never, Path("/nowhere")) is None
    assert backfill.terms_for("weekly:2026-w35", never, Path("/nowhere")) is None


def test_the_weekly_says_it_is_targums_own() -> None:
    """Three issues stood as unknown beside the seven Wikisource pages, and unlike those
    seven nobody has to check: targum wrote them."""
    from targum.weekly.entries import entries_for
    from targum.weekly.models import Edition, Issue, Level

    issue = Issue(
        id="2026-w35",
        dated="2026-08-28",
        title="t",
        editions=[
            Edition(level=Level.aleph, entry_id="weekly-2026-w35-aleph", folder="f", words=1)
        ],
    )
    (entry,) = entries_for(issue)
    assert entry.licence == "targum" and verdict(entry.licence).standing is Standing.free
