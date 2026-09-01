"""The weekday siddur, assembled from a complex index.

A book of the Tanakh is one address holding chapters of verses. A siddur is a tree of
four hundred and fifty-six named leaves and the API refuses any reference above one of
them, so a service is walked and put back together rather than fetched. Everything here
defends the two things that makes fragile: that the two sides come out identical, and
that a leaf only one of them has is dropped from both.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from targum.align import parallel
from targum.errors import TargumError
from targum.ingest import fetch
from targum.ingest.fetch import siddur
from targum.models import BlockKind

SCHEMA: dict[str, Any] = {
    "nodes": [
        {
            "titles": [
                {"lang": "en", "text": "Weekday", "primary": True},
                {"lang": "he", "text": "חול", "primary": True},
            ],
            "nodes": [
                {
                    "titles": [
                        {"lang": "en", "text": "Minchah", "primary": True},
                        {"lang": "he", "text": "תפילת מנחה", "primary": True},
                    ],
                    "nodes": [
                        {
                            "titles": [
                                {"lang": "en", "text": "Ashrei", "primary": True},
                                {"lang": "he", "text": "אשרי", "primary": True},
                            ],
                            "depth": 1,
                        },
                        {
                            "titles": [
                                {"lang": "en", "text": "Post Amidah", "primary": True},
                                {"lang": "he", "text": "אחרי העמידה", "primary": True},
                            ],
                            "nodes": [
                                {
                                    "titles": [
                                        {"lang": "en", "text": "Tachanun", "primary": True},
                                        {"lang": "he", "text": "תחנון", "primary": True},
                                    ],
                                    "depth": 1,
                                },
                                {
                                    "titles": [
                                        {"lang": "en", "text": "Vidui", "primary": True},
                                        {"lang": "he", "text": "וידוי", "primary": True},
                                    ],
                                    "depth": 1,
                                },
                            ],
                        },
                    ],
                }
            ],
        }
    ]
}

#: What each leaf holds, by reference and language. `Vidui` is in the Hebrew and not the
#: English, which is the shape of the real thing: Metsudah covers 170 of the weekday's
#: 174 leaves and the four it misses are misses on one side only.
TEXTS: dict[tuple[str, str], list[str]] = {
    ("Siddur Ashkenaz, Weekday, Minchah, Ashrei", "he"): ["אַשְׁרֵי", "תְּהִלָּה לְדָוִד"],
    ("Siddur Ashkenaz, Weekday, Minchah, Ashrei", "en"): ["Fortunate", "A psalm of praise"],
    ("Siddur Ashkenaz, Weekday, Minchah, Post Amidah, Tachanun", "he"): ["רַחוּם וְחַנּוּן"],
    ("Siddur Ashkenaz, Weekday, Minchah, Post Amidah, Tachanun", "en"): ["Merciful and gracious"],
    ("Siddur Ashkenaz, Weekday, Minchah, Post Amidah, Vidui", "he"): ["אָשַׁמְנוּ"],
}


def _serve(url: str) -> str:
    if url == siddur.SCHEMA:
        return json.dumps({"schema": SCHEMA})
    from urllib.parse import unquote, urlparse

    parsed = urlparse(url)
    ref = unquote(parsed.path.rsplit("/", 1)[-1])
    language = "he" if "hebrew" in unquote(parsed.query) else "en"
    lines = TEXTS.get((ref, language))
    if lines is None:
        return json.dumps({"versions": []})
    return json.dumps({"versions": [{"license": "CC-BY", "text": lines}]})


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(siddur, "get", _serve)


# -- the identifier -----------------------------------------------------------


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        ("Weekday, Shacharit", ("he", "Weekday, Shacharit")),
        ("en:Weekday, Shacharit", ("en", "Weekday, Shacharit")),
        ("siddur:en:Weekday, Maariv", ("en", "Weekday, Maariv")),
    ],
)
def test_identifiers(identifier: str, expected: tuple[str, str]) -> None:
    assert siddur.split_identifier(identifier) == expected


def test_the_registry_knows_the_scheme() -> None:
    assert fetch.is_identifier("siddur:Weekday, Minchah")
    assert not fetch.is_identifier("siddur:")


def test_only_the_weekday_is_on_offer() -> None:
    """Metsudah is CC-BY on both sides and covers almost none of Shabbat.

    Refused by name rather than attempted, because attempting it is a hundred requests
    that come back with nothing in them.
    """
    with pytest.raises(TargumError, match="does not carry"):
        siddur.SiddurFetcher().load("Shabbat, Shacharit")


# -- what comes out -----------------------------------------------------------


def test_a_service_is_headings_and_the_lines_under_them(offline: None) -> None:
    document = siddur.SiddurFetcher().load("Weekday, Minchah")
    assert document.title == "תפילת מנחה"
    shape = [(block.kind, block.level, block.text) for block in document.blocks]
    assert shape[0] == (BlockKind.heading, 1, "תפילת מנחה")
    assert shape[1] == (BlockKind.heading, 2, "אשרי")
    assert shape[2][0] is BlockKind.verse


def test_a_section_is_written_once_and_not_above_every_prayer_in_it(offline: None) -> None:
    """A service is three levels deep in places and one in others."""
    headings = [
        b.text
        for b in siddur.SiddurFetcher().load("Weekday, Minchah").blocks
        if b.kind is BlockKind.heading
    ]
    assert headings == ["תפילת מנחה", "אשרי", "אחרי העמידה", "תחנון"]


def test_a_line_is_a_verse_so_the_segmenter_never_splits_it(offline: None) -> None:
    """A line of the siddur has to stay whole to pair with the line facing it."""
    document = siddur.SiddurFetcher().load("Weekday, Minchah")
    assert all(b.kind is not BlockKind.paragraph for b in document.blocks)


def test_every_line_carries_its_reference(offline: None) -> None:
    document = siddur.SiddurFetcher().load("Weekday, Minchah")
    verses = [b for b in document.blocks if b.kind is BlockKind.verse]
    assert verses[0].ref == "Siddur Ashkenaz, Weekday, Minchah, Ashrei 1"
    assert verses[1].ref == "Siddur Ashkenaz, Weekday, Minchah, Ashrei 2"
    assert all(b.ref for b in verses)


# -- and the pairing ----------------------------------------------------------


def test_a_leaf_only_one_side_has_is_dropped_from_both(offline: None) -> None:
    """The whole reason both languages are fetched for every leaf.

    Keeping Vidui in the Hebrew because the Hebrew has it would put a heading on one side
    that the other does not have, and `parallel.pair` counts chapters.
    """
    hebrew = siddur.SiddurFetcher().load("Weekday, Minchah")
    assert not any("וידוי" in block.text for block in hebrew.blocks)
    assert not any("אָשַׁמְנוּ" in block.text for block in hebrew.blocks)


def test_the_two_sides_come_out_the_same_shape(offline: None) -> None:
    hebrew = siddur.SiddurFetcher().load("Weekday, Minchah")
    english = siddur.SiddurFetcher().load("en:Weekday, Minchah")
    assert [(b.kind, b.level) for b in hebrew.blocks] == [(b.kind, b.level) for b in english.blocks]
    assert [b.ref for b in hebrew.blocks] == [b.ref for b in english.blocks]


def test_the_two_sides_claim_each_other(offline: None) -> None:
    """`align/parallel.py` reads the `sefaria/` prefix as a promise that the two sides
    are numbered by whoever published them — true here in the strongest form, since the
    same walk of the same tree produces both."""
    hebrew = siddur.SiddurFetcher().load("Weekday, Minchah")
    english = siddur.SiddurFetcher().load("en:Weekday, Minchah")
    assert parallel.parallel_key(hebrew) == parallel.parallel_key(english)
    assert parallel.parallel_key(hebrew) is not None


def test_an_edition_this_shelf_may_not_serve_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    def restricted(url: str) -> str:
        if url == siddur.SCHEMA:
            return json.dumps({"schema": SCHEMA})
        return json.dumps({"versions": [{"license": "CC-BY-NC", "text": ["x"]}]})

    monkeypatch.setattr(siddur, "get", restricted)
    with pytest.raises(TargumError, match="may not serve"):
        siddur.SiddurFetcher().load("Weekday, Minchah")


def test_a_service_with_nothing_in_it_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    def empty(url: str) -> str:
        if url == siddur.SCHEMA:
            return json.dumps({"schema": SCHEMA})
        return json.dumps({"versions": []})

    monkeypatch.setattr(siddur, "get", empty)
    with pytest.raises(TargumError, match="no text"):
        siddur.SiddurFetcher().load("Weekday, Minchah")
