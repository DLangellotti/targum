"""Reading somebody else's XML.

Public and tested here rather than beside the private compose loop: parsing a feed is
not content and not a moat, and it is where the encoding bugs live.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from targum.weekly.feeds import MAX_SUMMARY, Item, parse

RSS = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
  <title>מבזקים</title>
  <item>
    <title>ועדה ציבורית תבחן את מחירי הדיור</title>
    <link>https://example.co.il/a</link>
    <description>הוועדה תגיש את מסקנותיה בתוך חצי שנה.</description>
    <pubDate>Mon, 31 Aug 2026 06:00:00 +0300</pubDate>
    <guid isPermaLink="false">a-1</guid>
  </item>
  <item>
    <title>ניצחון חוץ בתוצאה 2:0</title>
    <link>https://example.co.il/b</link>
  </item>
</channel></rss>
"""

ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>מוזיאון פתח תערוכה</title>
    <link rel="edit" href="https://example.org/edit/1"/>
    <link rel="alternate" href="https://example.org/1"/>
    <summary>ציורים מן המאה התשע עשרה.</summary>
    <published>2026-08-30T09:15:00+03:00</published>
    <id>urn:uuid:1</id>
  </entry>
</feed>
"""


def test_rss_gives_the_five_fields_a_digest_needs() -> None:
    first, second = parse(RSS.encode())
    assert first.title == "ועדה ציבורית תבחן את מחירי הדיור"
    assert first.link == "https://example.co.il/a"
    assert first.summary.startswith("הוועדה תגיש")
    assert first.guid == "a-1"
    assert first.published is not None and first.published.year == 2026
    assert second.title.startswith("ניצחון")
    assert second.published is None, "a feed that says nothing is not made to say something"


def test_atom_is_read_by_the_same_parser() -> None:
    """One parser, matching on local names, rather than a namespace map and a guess at
    which kind of document this is."""
    (entry,) = parse(ATOM.encode())
    assert entry.title == "מוזיאון פתח תערוכה"
    assert entry.summary.startswith("ציורים")
    assert entry.guid == "urn:uuid:1"
    assert entry.published is not None and entry.published.tzinfo is not None


def test_atom_takes_the_article_link_not_the_first_one() -> None:
    """Atom may write several, and only one of them is the article."""
    (entry,) = parse(ATOM.encode())
    assert entry.link == "https://example.org/1"


def test_a_declared_encoding_is_honoured() -> None:
    """The reason `Fetched` carries the raw bytes at all.

    A Hebrew feed served as windows-1255 with no charset in the header would be decoded
    as UTF-8 by the HTTP layer and arrive as mojibake. Handed the bytes, the parser
    reads the prolog and gets it right.
    """
    body = (
        '<?xml version="1.0" encoding="windows-1255"?>'
        '<rss version="2.0"><channel><item><title>שלום</title>'
        "<link>https://example.co.il/x</link></item></channel></rss>"
    ).encode("windows-1255")
    (item,) = parse(body)
    assert item.title == "שלום"


def test_a_summary_is_a_hook_and_is_kept_to_one() -> None:
    """A facts-only source gives facts. The shortest way to keep that true is to refuse
    to hold more than a hook of one."""
    long = "מ" * 900
    body = (
        f'<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel><item>'
        f"<title>כותרת</title><description>{long}</description></item></channel></rss>"
    ).encode()
    (item,) = parse(body)
    assert len(item.summary) == MAX_SUMMARY


@pytest.mark.parametrize(
    "body",
    [b"", b"not xml at all", b"<rss><channel></channel></rss>", b"<html><body>hi</body></html>"],
)
def test_nothing_usable_is_no_items_rather_than_a_crash(body: bytes) -> None:
    """A feed that moved, went away, or started answering with a login page should cost
    the run that source, not the whole issue."""
    assert parse(body) == []


def test_an_item_with_no_title_is_not_an_item() -> None:
    body = b'<rss version="2.0"><channel><item><link>https://a.b/c</link></item></channel></rss>'
    assert parse(body) == []


def test_a_bad_date_does_not_lose_the_item() -> None:
    body = (
        '<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel><item>'
        "<title>כותרת</title><pubDate>whenever</pubDate></item></channel></rss>"
    ).encode()
    (item,) = parse(body)
    assert item.published is None
    assert item.title == "כותרת"


def test_dates_come_back_aware_so_they_can_be_compared() -> None:
    """Selection asks whether two outlets carried a story within 48 hours of each other,
    and a naive datetime cannot be subtracted from an aware one."""
    for item in parse(RSS.encode()) + parse(ATOM.encode()):
        if item.published is not None:
            assert item.published.tzinfo is not None
            assert item.published < datetime.now(UTC).replace(year=2100)


def test_an_item_is_hashable_and_comparable() -> None:
    """Dedup puts these in sets."""
    one = Item(title="a", link="b")
    assert one == Item(title="a", link="b")
    assert len({one, Item(title="a", link="b")}) == 1


# -- the Russian publishers (2026-10-06) --------------------------------------------------
#
# Fabricated items in the shapes the nine Russian feeds were measured sending on
# 2026-10-06: markup inside a CDATA description (Meduza, Novaya Gazeta Europe,
# Teplitsa), `&nbsp;` there (OVD-Info), an empty description and namespaced full-text
# fields (TASS, RBC), an ISO date where RFC 822 is expected, an item with no date (BBC),
# and a legacy Cyrillic encoding declared in the prolog.

FEEDS = Path(__file__).parent / "fixtures" / "feeds"


def test_a_summary_written_as_markup_reads_as_words() -> None:
    items = parse((FEEDS / "ru-html-summaries.xml").read_bytes())
    assert [item.title for item in items] == [
        "В парке открыли новую библиотеку",
        "Врач рассказал о новой клинике «Здоровье»",
        "Прямой эфир: день города",
    ]
    first, second, third = items
    assert first.summary == (
        "В городском парке открыли библиотеку под открытым небом. Книги можно брать без записи ."
    )
    assert second.summary == "Врач-невролог рассказал об открытии клиники на окраине города."
    assert third.summary.startswith("Праздник продолжается весь день, программа")
    for item in items:
        assert "<" not in item.summary and "href" not in item.summary
        assert "nbsp" not in item.summary and "\xa0" not in item.summary
    assert first.published == datetime(2026, 10, 6, 18, 34, 6, tzinfo=UTC)
    assert third.published is None, "no date is no date, and the item is kept"


def test_an_agency_feed_with_empty_summaries_and_iso_dates_parses() -> None:
    items = parse((FEEDS / "ru-agency.xml").read_bytes())
    assert [item.link for item in items] == [
        "https://agency.example/sport/1001",
        "https://agency.example/rbcfreenews/1002",
    ]
    assert items[0].summary == ""
    assert items[1].summary == "Вдоль набережной высадили двести молодых каштанов."
    assert items[1].published == datetime(2026, 10, 6, 19, 10, 40, tzinfo=UTC)


def test_a_cyrillic_feed_in_windows_1251_is_read_by_its_prolog() -> None:
    raw = (FEEDS / "ru-windows-1251.xml").read_bytes()
    assert "Мост".encode() not in raw, "the fixture really is in windows-1251"
    (item,) = parse(raw)
    assert item.title == "Мост через реку откроют весной"
    assert item.summary == "Строители закончили опоры моста."
    assert item.published == datetime(2026, 10, 6, 10, 0, tzinfo=UTC)


def test_a_hebrew_summary_with_no_markup_is_untouched() -> None:
    (first, _) = parse(RSS.encode())
    assert first.summary == "הוועדה תגיש את מסקנותיה בתוך חצי שנה."
