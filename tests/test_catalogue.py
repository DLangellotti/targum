"""The catalogue entry's English title: read from the file, sent to the page, never
invented."""

from __future__ import annotations

import json
import os
from pathlib import Path


def test_an_entry_carries_its_english_title() -> None:
    from targum.catalogue import CATALOGUE, by_id

    assert by_id("ruth").english == "Ruth"
    assert by_id("scene-01-nice-to-meet-you").english == "Nice to meet you"
    # Every entry in the fixture has one, as every entry in the live catalogue must after
    # review: there is no fallback, because a blurb where a title goes reads as a title.
    assert all(entry.english for entry in CATALOGUE), [e.id for e in CATALOGUE if not e.english]


def test_the_page_is_sent_the_english_and_an_old_file_still_loads() -> None:
    from targum.catalogue import _entry, by_id

    assert by_id("ruth").state()["english"] == "Ruth"
    # A catalogue written before the field existed loads with it empty rather than failing.
    old = _entry({"id": "x", "title": "ט", "language": "he", "source": "test:x"})
    assert old.english == ""
    assert old.state()["english"] == ""


def test_the_live_catalogue_has_an_english_title_for_every_entry() -> None:
    """The private file the box is deployed from, when this machine has it. Skipped where
    it does not — the fixture is the catalogue under test everywhere else."""
    import pytest

    live = Path(os.path.expanduser("~/.targum/catalogue.json"))
    if not live.is_file():
        pytest.skip("no live catalogue on this machine")
    loaded = json.loads(live.read_text(encoding="utf-8"))
    entries = loaded["entries"] if isinstance(loaded, dict) else loaded
    missing = [e["id"] for e in entries if not str(e.get("english", "")).strip()]
    assert not missing, f"{len(missing)} entries without an English title: {missing[:8]}"


def test_a_scene_knows_its_number_and_nothing_else_has_one() -> None:
    from targum.catalogue import scene_number

    assert scene_number("scene-01-nice-to-meet-you") == 1
    assert scene_number("scene-100-the-same-spot") == 100
    assert scene_number("ruth") == 0
    assert scene_number("") == 0


# -- collections --------------------------------------------------------------


def test_a_collection_only_ever_claims_texts_that_are_there() -> None:
    """The catalogue is data and a member can be removed without the collection knowing.
    What it must never do is open onto a row that is not on the shelf."""
    from targum.catalogue import collections, everything

    have = {entry.id for entry in everything()}
    for group in collections():
        assert set(group.members) <= have, group.id


def test_a_text_belongs_to_one_collection_at_most() -> None:
    """Two rows for one text is the flood this exists to stop, not a way of causing it."""
    from targum.catalogue import collections

    seen: dict[str, str] = {}
    for group in collections():
        for member in group.members:
            assert member not in seen, f"{member} is in {seen.get(member)} and {group.id}"
            seen[member] = group.id


def test_a_collection_of_one_is_not_a_collection() -> None:
    """Folding a single text hides it behind a click and says "1 text" where its own
    name would do."""
    from targum.catalogue import collections

    assert all(len(group.members) > 1 for group in collections())


def test_a_text_can_say_which_collection_it_is_in() -> None:
    from targum.catalogue import collection_of, collections

    group = collections()[0]
    assert collection_of(group.members[0]) == group


# -- the register ---------------------------------------------------------------


def test_the_registers_are_a_ramp_from_oldest_to_newest() -> None:
    """The library shows them in this order and never sorts them: the field is a ramp a
    learner climbs, and Modern above Rabbinic because M precedes R would throw that away.
    """
    from targum.catalogue import Register

    assert [register.value for register in Register] == [
        "biblical",
        "rabbinic",
        "medieval",
        "revival",
        "modern",
        "",
    ]


def test_no_hebrew_text_is_left_without_a_register() -> None:
    """Empty means "not Hebrew, the axis does not apply", and a Hebrew text that says it
    is a Hebrew text nobody has placed."""
    from targum.catalogue import Register, everything

    for entry in everything():
        if entry.language.startswith("he"):
            assert entry.register is not Register.none, entry.id


def test_video_is_asked_of_the_disk_and_only_where_there_is_sound() -> None:
    """The media fact lives beside `spoken`, derived the same way: nothing in the
    catalogue says "video" by hand, and a text cannot be watched that cannot be heard."""
    from targum.catalogue import CATALOGUE

    for entry in CATALOGUE:
        state = entry.state()
        assert "video" in state
        assert not state["video"] or state["spoken"], entry.id


def _labelled(name: str) -> set[str]:
    """The values the library page has a word for, read out of its own list.

    Parsed rather than duplicated here, because a copy of the list in a test is a second
    thing to keep in step and the first one to go stale.
    """
    import re

    assets = Path(__file__).resolve().parents[1] / "src/targum/render/assets"
    text = (assets / "library.js").read_text(encoding="utf-8")
    block = re.search(rf"var {name} = \[(.*?)\];", text, re.S)
    assert block, f"{name} is not a list in library.js any more"
    return set(re.findall(r'\["([a-z]+)",', block.group(1)))


def test_every_kind_and_register_has_a_word_a_reader_would_use() -> None:
    """A value with no label shows as an empty column and no chip, and says nothing.

    `named()` in library.js returns "" for a value it does not know, so adding to either
    enum without adding to the list beside it is silent: the text is on the shelf, its
    kind column is blank, and the filter that would find it is not offered. This is the
    check that makes that loud, added when `Kind.liturgy` went in for the siddur
    (targum-internal#120).
    """
    from targum.catalogue import Kind, Register

    # `Register.none` is the empty string — "anything not in Hebrew, where the axis does
    # not apply" — and there is nothing for a Hebrew library to call it.
    registers = {one.value for one in Register if one.value}

    assert {one.value for one in Kind} <= _labelled("KINDS"), "a kind with no word for it"
    assert registers <= _labelled("REGISTERS"), "a register with no word for it"
