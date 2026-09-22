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


def test_a_rendering_is_in_the_language_its_source_names() -> None:
    """Every rendering on the shelf was English until Onkelos, and a text page's structured
    data said so of all of them (targum-internal#65)."""
    from targum.catalogue import Rendering

    def language(source: str) -> str:
        return Rendering(name="x", source=source).language

    assert language("sefaria:arc:Genesis") == "arc"
    assert language("sefaria:en:Genesis") == "en"
    assert language("siddur:en:shacharit") == "en"
    assert language("wikisource:United States Declaration of Independence") == "en"
    assert language("https://globalvoices.org/2014/07/15/farz") == "en"


def test_a_text_says_every_language_it_can_be_read_in() -> None:
    """2026-09-14: the Aramaic shelf showed nothing, because a row named one language.
    Daniel and Ezra have Aramaic chapters. A Torah book carrying Targum Onkelos beside it
    is not an Aramaic text — filing it there made the Aramaic shelf the Hebrew Torah — and
    an Aramaic targum is Aramaic alone."""
    from dataclasses import replace

    from targum.catalogue import Entry, Kind, Register, Rendering

    def entry(source: str, *renderings: str) -> Entry:
        return Entry(
            id="x",
            title="x",
            author="",
            language="he",
            source=source,
            blurb="",
            words=10,
            tags=frozenset(),
            translations=tuple(Rendering(name="r", source=one) for one in renderings),
            kind=Kind.prose,
            register=Register.biblical,
        )

    assert entry("sefaria:Daniel").languages == ["he", "arc"]
    assert entry("sefaria:Genesis", "sefaria:en:Genesis", "sefaria:arc:Genesis").languages == ["he"]
    onkelos = replace(entry("sefaria:arc:Genesis"), language="arc")
    assert onkelos.languages == ["arc"]
    assert entry("sefaria:Ruth", "sefaria:en:Ruth").languages == ["he"]
    assert entry("sefaria:Ruth").state()["languages"] == ["he"]


def test_every_subject_the_arrival_asks_for_can_be_filed() -> None:
    """`accounts` asks the question and `catalogue` files the texts, and the two grow
    apart silently: a subject with no tag behind it is a door that can never be answered
    however many texts arrive, and a tag no door offers is a shelf nobody is sent to.

    The three matched by `Kind` rather than by tag are named here rather than tagged —
    `dialogue`, `story`/`novel`/`play` and `poetry` are forms the catalogue already
    files by, and a second vocabulary saying the same thing would go out of step with
    the first.
    """
    from targum.accounts import Store
    from targum.catalogue import Tag

    by_kind = {"everyday", "stories", "poetry"}
    # The two the catalogue spells differently, because the tags predate the doors and
    # a rename would re-file every text to no purpose.
    spelled = {"judaism": {"tanakh", "judaica"}, "news": {"journalism"}}

    tags = {tag.value for tag in Tag}
    for subject in Store.INTERESTS:
        if subject in by_kind:
            continue
        wanted = spelled.get(subject, {subject})
        assert wanted <= tags, f"{subject} is asked for and cannot be filed"

    offered = set()
    for subject in Store.INTERESTS:
        offered |= spelled.get(subject, {subject})
    assert tags <= offered, f"filed under a subject nothing offers: {sorted(tags - offered)}"


def test_a_row_arriving_in_the_catalogue_is_dated_and_an_old_one_keeps_its_date(
    tmp_path,
) -> None:
    """The one door the catalogue grows through, so "what is new" is a question about
    when a text arrived and not about how it got here (targum-internal#315)."""
    import datetime
    import json
    import os

    from targum import catalogue as catalogue_module
    from targum.promote import merge_into_catalogue

    path = tmp_path / "catalogue.json"
    whole = {"language": "he", "source": "x:y", "words": 10}
    was_here = {"id": "old-one", "title": "ישן", "added": "2020-02-02", **whole}
    path.write_text(json.dumps({"entries": [was_here]}), encoding="utf-8")

    # Not `monkeypatch`: `reload()` fills a module-level cache from the environment, and
    # monkeypatch puts the environment back at teardown without telling the cache — so
    # the catalogue stayed pointed at this two-row temporary file for the rest of the
    # session. 85 tests failed across `test_serve`, `test_render` and `test_public`, none
    # of them about the code they named. The env is put back and the cache reloaded here,
    # in that order, where the order can be seen.
    was = os.environ.get("TARGUM_CATALOGUE")
    os.environ["TARGUM_CATALOGUE"] = str(path)
    catalogue_module.reload()
    try:
        merge_into_catalogue({"id": "new-one", "title": "חדש", **whole})
        merge_into_catalogue({"id": "old-one", "title": "ישן שונה", **whole})

        rows = {row["id"]: row for row in json.loads(path.read_text(encoding="utf-8"))["entries"]}
        assert rows["new-one"]["added"] == datetime.date.today().isoformat()
        assert rows["old-one"]["added"] == "2020-02-02", "accepting it again is not it arriving"
        assert rows["old-one"]["title"] == "ישן שונה", "and the merge still merges"
    finally:
        if was is None:
            os.environ.pop("TARGUM_CATALOGUE", None)
        else:
            os.environ["TARGUM_CATALOGUE"] = was
        catalogue_module.reload()


# -- a collection is named in the reader's language too (targum-internal#289) -----------


def test_a_collection_carries_its_other_languages_the_way_an_entry_does() -> None:
    """The rows learned their own language in targum#280 and the collections they fold
    into did not, so a shelf could read "Тора" over a group still called "Torah"."""
    from targum.catalogue import Collection

    group = Collection(
        id="torah",
        title="תורה",
        english="Torah",
        blurb="The five books.",
        named={"ru": "Тора"},
        blurbs={"ru": "Пять книг."},
    )
    assert group.name_in("ru") == "Тора"
    assert group.name_in("ru-RU") == "Тора", "a regional tag is the language"
    assert group.name_in("en") == "Torah"
    assert group.blurb_in("ru") == "Пять книг."

    bare = Collection(id="x", title="ת", english="Torah", blurb="The five books.")
    assert bare.name_in("ru") == "Torah", "English is the fallback, never wrong only foreign"
    assert bare.blurb_in("ru") == "The five books."

    # And the page is handed them, or the shelf cannot draw what it was given.
    said = group.state()
    assert said["named"] == {"ru": "Тора"} and said["blurbs"] == {"ru": "Пять книг."}
    assert said["english"] == "Torah", "English stays where it was"


def test_a_collection_written_before_this_still_reads() -> None:
    """Every catalogue on disk predates these two fields."""
    from targum.catalogue import _collection

    made = _collection({"id": "x", "title": "ת", "english": "Torah", "members": ["a"]})
    assert made.named == {} and made.blurbs == {}
    assert made.name_in("ru") == "Torah"


# -- a rendering says where its licence was read (targum-internal#355) -------------------


def test_a_rendering_records_where_its_licence_was_read() -> None:
    """LICENSING.md asks for the licence *and* the URL it was read at, and says why: the
    URL is kept verbatim "precisely so it can be re-checked against the page rather than
    against somebody's summary of it". A `Rendering` carried only the first half until
    2026-09-22, so 246 of the 251 on the shelf recorded a claim nobody could re-check.
    """
    from targum.catalogue import _entry

    made = _entry(
        {
            "id": "x",
            "title": "ת",
            "source": "s",
            "language": "he",
            "translations": [
                {
                    "name": "A rendering",
                    "source": "published:ru:Genesis",
                    "licence": "Public Domain",
                    "licence_url": "https://rusneb.ru/catalog/000199_000009_009682814/",
                }
            ],
        }
    )
    (beside,) = made.translations
    assert beside.licence == "Public Domain"
    assert beside.licence_url == "https://rusneb.ru/catalog/000199_000009_009682814/"


def test_a_rendering_written_before_this_still_reads() -> None:
    """Every catalogue on disk predates the field, so it is optional and empty — and the
    emptiness is reported by `targum licences` rather than passed off as a checked
    licence."""
    from targum.catalogue import _entry

    made = _entry(
        {
            "id": "x",
            "title": "ת",
            "source": "s",
            "language": "he",
            "translations": [{"name": "A rendering", "source": "s2", "licence": "CC-BY"}],
        }
    )
    (beside,) = made.translations
    assert beside.licence == "CC-BY" and beside.licence_url == ""
