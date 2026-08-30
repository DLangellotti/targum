"""Gathering a week, where the gatherer is on this machine.

`facts.py` and `sources.py` are the private half and do not ship, so these skip on a
checkout that has not got them. What has to hold whatever is or is not installed lives
on the public model instead and is tested in `test_weekly_verify.py` — chiefly that a
facts-only story cannot carry an excerpt at all.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from targum.weekly.feeds import Item
from targum.weekly.models import Part

facts = pytest.importorskip("targum.weekly.facts", reason="the private half is not installed")
sources = pytest.importorskip("targum.weekly.sources", reason="the private half is not installed")

NOW = datetime.now(UTC)


def item(title: str, link: str = "", summary: str = "", hours: int = 0) -> Item:
    return Item(title=title, link=link, summary=summary, published=NOW - timedelta(hours=hours))


def paired(title: str, key: str, **kwargs: object) -> tuple[Item, object]:
    source = sources.by_key(key)
    assert source is not None
    return item(title, **kwargs), source  # type: ignore[arg-type]


# -- the licence boundary is a property of the registry -------------------------------


def test_only_a_licensed_source_may_have_its_page_fetched() -> None:
    """The single rule that keeps the boundary mechanical rather than remembered: a
    facts-only source is reached at its feed and at no other address, ever."""
    for source in sources.SOURCES:
        if source.article:
            assert source.tier is sources.Tier.open, source.key


def test_every_licensed_source_names_the_licence_it_relies_on() -> None:
    for source in sources.SOURCES:
        if source.tier is sources.Tier.open:
            assert source.licence, source.key


def test_the_registry_refuses_to_hold_a_contradiction() -> None:
    with pytest.raises(ValueError, match="licensed"):
        sources.Source(
            key="bad",
            name="x",
            publisher="y",
            feed="https://example.org/rss",
            tier=sources.Tier.facts,
            section=Part.israel,
            article=True,
        )


def test_every_section_has_somewhere_to_get_its_news() -> None:
    for part in Part:
        assert sources.for_section(part), part.value


def test_a_source_serves_exactly_one_section() -> None:
    """It was a tuple once, and a feed mapped to three sections put every item into all
    three — so the world filled up with Israeli domestic politics, and the count of how
    many outlets carried a story counted the same outlet repeatedly."""
    for source in sources.SOURCES:
        assert isinstance(source.section, Part), source.key


# -- one article, one address ---------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "wanted"),
    [
        ("https://a.co.il/x/?utm_source=tw&id=3#top", "https://a.co.il/x?id=3"),
        ("https://a.co.il/x?fbclid=zz", "https://a.co.il/x"),
        ("https://a.co.il/x/", "https://a.co.il/x"),
        ("", ""),
    ],
)
def test_tracking_parameters_belong_to_whoever_sent_you(given: str, wanted: str) -> None:
    assert facts.canonical(given) == wanted


# -- what is one story ----------------------------------------------------------------


def test_two_outlets_on_one_event_are_one_story() -> None:
    one = paired("ועדה ציבורית תבחן את מחירי הדיור בישראל", "ynet-news", link="https://y/1")
    two = paired("ועדה תבחן את מחירי הדיור בישראל השבוע", "walla-news", link="https://k/1")
    assert facts.same_story(one, two)


def test_two_events_are_two_stories() -> None:
    one = paired("ועדה ציבורית תבחן את מחירי הדיור בישראל", "ynet-news")
    two = paired("נבחרת ישראל ניצחה את קרואטיה בכדורגל", "ynet-news")
    assert not facts.same_story(one, two)


def test_a_number_counts_toward_telling_two_stories_apart() -> None:
    """It counts, and on its own it is not enough — which is the honest claim.

    Two headlines sharing a subject and a verb and differing only in a figure still
    measure similar, and no threshold that separates those keeps the pairs worth
    merging. The date and the link do that work. What the digits buy is that they are
    in the comparison at all, so a headline whose numbers are most of its content is
    not reduced to the handful of ordinary words around them.
    """
    source = sources.by_key("ynet-sport")
    assert source is not None
    scored = facts._bag(item("מכבי חיפה ניצחה 2:0"), source)
    assert {"2", "0"} <= scored, "the figures are part of what the headline is about"
    assert facts._bag(item("מכבי חיפה ניצחה 3:1"), source) != scored


def test_the_same_words_a_week_apart_are_two_stories() -> None:
    """Two outlets writing inside two days are covering one event. A week apart they
    are covering two."""
    one = paired("ועדה תבחן את מחירי הדיור בישראל", "ynet-news")
    two = paired("ועדה תבחן את מחירי הדיור בישראל", "walla-news", hours=24 * 7)
    assert not facts.same_story(one, two)


def test_the_same_link_is_the_same_story_whatever_the_headline_says() -> None:
    one = paired("כותרת אחת", "ynet-news", link="https://a.co.il/x?utm_source=tw")
    two = paired("כותרת אחרת לגמרי בלי מילים משותפות", "walla-news", link="https://a.co.il/x")
    assert facts.same_story(one, two)


# -- what an issue is made of ---------------------------------------------------------


def test_a_licensed_source_leads_its_group_and_is_the_only_one_quoted() -> None:
    """The lead decides what the story may carry, so it has to be the member whose
    wording is usable where there is one."""
    licensed = paired(
        "ועדה ציבורית תבחן את מחירי הדיור בישראל",
        "gov",
        link="https://gov/1",
        summary="הוועדה תגיש את מסקנותיה בתוך חצי שנה.",
    )
    other = paired("ועדה תבחן את מחירי הדיור בישראל", "ynet-news", link="https://y/1")

    brief = facts.choose({Part.israel: [other, licensed]}, "2026-w36")
    (story,) = brief.stories
    assert story.tier == 1
    assert story.excerpt, "a licensed lead may be drawn on"
    assert set(story.outlets) == {"gov.il", "ynet"}


def test_an_unlicensed_group_carries_no_wording_to_draw_on() -> None:
    group = [
        paired("נבחרת ישראל ניצחה את קרואטיה בכדורגל", "ynet-sport", summary="שער בדקה ה-90."),
        paired("נבחרת ישראל ניצחה את קרואטיה אמש", "walla-sport", summary="שער מאוחר הכריע."),
    ]
    (story,) = facts.choose({Part.sport: group}, "2026-w36").stories
    assert story.tier == 2
    assert story.excerpt == ""
    assert story.facts, "the hooks are kept as facts, which is what they are"


def test_a_section_takes_only_what_it_has_room_for() -> None:
    headlines = [
        "נבחרת ישראל ניצחה את קרואטיה בכדורגל",
        "מכבי חיפה עלתה לגמר גביע המדינה",
        "שחיינית ישראלית קבעה שיא לאומי חדש",
        "אליפות הכדורסל תיפתח בחודש הבא",
        "רץ מרתון מירושלים סיים במקום השלישי",
    ]
    many = [paired(title, "ynet-sport", link=f"https://y/{n}") for n, title in enumerate(headlines)]
    brief = facts.choose({Part.sport: many}, "2026-w36")
    assert len(brief.stories) == facts.SHAPE[Part.sport]


def test_the_story_more_outlets_carried_wins_the_place() -> None:
    """How many independent outlets ran it is an importance signal that costs nothing."""
    widely = [
        paired("ועדה ציבורית תבחן את מחירי הדיור בישראל", key, link=f"https://{key}/1")
        for key in ("ynet-news", "walla-news", "gov")
    ]
    alone = [paired("ידיעה אחרת לגמרי על נושא שונה", "ynet-news", link="https://y/9")]
    brief = facts.choose({Part.israel: widely + alone}, "2026-w36")
    assert len(brief.stories[0].outlets) == 3


def test_a_brief_can_be_audited_back_to_what_it_was_written_from() -> None:
    group = [paired("נבחרת ישראל ניצחה את קרואטיה", "ynet-sport", link="https://y/1")]
    brief = facts.choose({Part.sport: group}, "2026-w36", made=1756600000)
    assert brief.week == "2026-w36"
    assert brief.made
    assert brief.section(Part.sport)
    assert brief.facts_only, "every tier-2 story is listed for the lift check"
    assert brief.stories[0].links == ["https://y/1"]


# -- the command line ------------------------------------------------------------------


def test_the_command_says_plainly_when_the_gatherer_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A checkout without the proprietary half installs, serves, and reads an issue
    somebody else published. It simply cannot make one, and should say so rather than
    failing with an import error."""
    import sys

    import targum.weekly
    from targum.cli import _gatherer
    from targum.errors import TargumError

    # A None in sys.modules is how the import machinery is told a module is not there,
    # without having to move the file out from under a running test.
    monkeypatch.setitem(sys.modules, "targum.weekly.facts", None)
    monkeypatch.delattr(targum.weekly, "facts", raising=False)

    with pytest.raises(TargumError, match="not installed") as raised:
        _gatherer()
    # The hint is where a person is told what to do about it, and it has to name why
    # the file is missing rather than leaving them looking for a bug.
    assert raised.value.hint is not None
    assert "proprietary" in raised.value.hint


def test_the_brief_command_writes_where_the_issue_will_live(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`brief` is a command of its own so the fact base can be read by eye before a
    word is written from it — and so it can be checked afterwards."""
    import json

    from targum.cli import weekly_brief
    from targum.weekly import index

    monkeypatch.setattr(
        facts,
        "gather",
        lambda **_: {
            Part.sport: [
                paired("נבחרת ישראל ניצחה את קרואטיה בכדורגל", "ynet-sport", link="https://y/1")
            ]
        },
    )
    weekly_brief("2026-w40", out=None, limit=5)

    written = index.root() / "2026-w40" / "brief.json"
    assert written.is_file()
    saved = json.loads(written.read_text(encoding="utf-8"))
    assert saved["week"] == "2026-w40"
    assert saved["stories"][0]["tier"] == 2
    assert saved["stories"][0]["excerpt"] == "", "a facts-only story carries no wording"


def test_exactly_one_story_is_the_week_s_lead() -> None:
    """The top level writes it at length while the rest stay brief, so an advanced
    reader gets something to sink into without the three editions covering different
    news. Chosen by the same signal that orders each section: how many outlets ran it."""
    widely = [
        paired("ועדה ציבורית תבחן את מחירי הדיור בישראל", key, link=f"https://{key}/1")
        for key in ("ynet-news", "walla-news", "maariv-news", "mako-news")
    ]
    alone = [paired("נבחרת ישראל ניצחה את קרואטיה בכדורגל", "ynet-sport", link="https://y/9")]

    brief = facts.choose({Part.israel: widely, Part.sport: alone}, "2026-w36")
    leads = [story for story in brief.stories if story.lead]
    assert len(leads) == 1
    assert leads[0].section is Part.israel, "the story four outlets carried, not the one"


def test_a_brief_with_one_story_names_no_lead() -> None:
    """A lead only means something against the rest of the issue."""
    one = [paired("ידיעה יחידה", "ynet-sport", link="https://y/1")]
    brief = facts.choose({Part.sport: one}, "2026-w36")
    assert not any(story.lead for story in brief.stories)


def test_every_section_has_more_than_one_outlet_where_it_can() -> None:
    """A section with one feed can never corroborate a story, so `outlets` is always 1
    and the importance signal that orders the section does nothing. World had exactly
    one feed and every story came back uncorroborated."""
    thin = [part for part in Part if len(sources.for_section(part)) < 2]
    assert not thin, f"only one feed for: {[part.value for part in thin]}"
