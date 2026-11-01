"""The news yardstick counted from the feeds themselves (targum-internal#582): counts and
provenance per outlet, never a sentence, never twice, never anything but a followed feed.

Every word here is synthetic: placeholder words, no sentence of any text. The annotator
is a stand-in that files each word under its capital, so no model runs.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from targum import ledger, tables
from targum.chat.sources import Publisher
from targum.models import Token
from targum.tables import news
from targum.tables.registers import NEWS
from targum.tables.store import Store
from targum.tables.words import WORDS
from targum.weekly.feeds import Item


class Stand:
    """Files every word under its capital as a noun; counts what it was handed."""

    name = "stand-in/1"

    def __init__(self, fail_on: str = "") -> None:
        self.read = 0
        self.fail_on = fail_on

    def annotate(self, document: Any) -> Any:
        self.read += 1
        tokens = {}
        for segment in document.segments:
            if self.fail_on and self.fail_on in segment.text:
                raise ValueError(f"could not read {segment.text!r}")
            run, at = [], 0
            for word in segment.text.split():
                run.append(
                    Token(
                        start=at,
                        end=at + len(word),
                        surface=word,
                        lemma=word.upper(),
                        band=0,
                        pos="NOUN",
                    )
                )
                at += len(word) + 1
            tokens[segment.id] = run
        return SimpleNamespace(tokens=tokens)


def _publisher(key: str, feed: str, **kw: Any) -> Publisher:
    return Publisher(key=key, name=key, publisher=key, feed=feed, **kw)


PAPER = _publisher("paper", "https://paper.test/rss")
SECTION = _publisher("paper-sport", "https://paper.test/rss/sport", licence="CC BY 4.0")
PODCAST = _publisher("show", "https://show.test/rss", kind="podcast")
RUSSIAN = _publisher("gazeta", "https://gazeta.test/rss", language="ru")
PUBLISHERS = [PAPER, SECTION, PODCAST, RUSSIAN]

WHEN = datetime(2026, 11, 1, 6, 0, tzinfo=UTC)


def _item(n: int, *, full: str = "", words: str = "") -> Item:
    return Item(
        title=f"t{n}a t{n}b t{n}c",
        link=f"https://paper.test/a/{n}",
        summary=words or f"s{n}a s{n}b s{n}c s{n}d",
        published=WHEN.replace(minute=n % 60),
        full_text=full,
    )


def _kept() -> dict[str, list[Item]]:
    return {
        PAPER.feed: [_item(1), _item(2, full="p2a p2b p2c\n\np2d p2e")],
        # The same story in the section's feed, at the same address.
        SECTION.feed: [_item(2, full="p2a p2b p2c\n\np2d p2e"), _item(3)],
        PODCAST.feed: [_item(4)],
        RUSSIAN.feed: [_item(5)],
        # A feed no publisher lists: a reader's subscription, say. Never counted.
        "https://reader.test/own": [_item(6)],
    }


def test_only_the_followed_hebrew_news_feeds_are_read() -> None:
    items = news.feed_items(_kept(), PUBLISHERS)
    assert [(one.outlet, one.full) for one in items] == [
        ("paper", False),
        ("paper", True),
        ("paper-sport", False),
    ]
    assert all(one.sealed and one.unit.startswith(news.PREFIX) for one in items)
    # The feed's full text where it carries one, else the title and the summary.
    assert items[1].text == "p2a p2b p2c\n\np2d p2e"
    assert items[0].text == "t1a t1b t1c\ns1a s1b s1c s1d"
    assert items[0].licence == f"{news.RESERVED}; {news.COUNTS_ONLY}"
    assert items[2].licence == f"CC BY 4.0; {news.COUNTS_ONLY}"
    # The unit is a hash of the address, as a server sees it, so a fragment or a capital
    # in the host is the same item.
    assert news.unit_of("https://PAPER.test/a/1#top") == items[0].unit
    assert "paper.test" not in items[0].unit


def test_an_item_from_anywhere_else_is_refused(tmp_path: Path) -> None:
    forged = news.FeedItem(
        unit="feed:x", outlet="paper", licence="l", published=0.0, full=False, text="w1"
    )
    with pytest.raises(TypeError):
        news.count_news(Store(tmp_path / "corpus.db"), [forged], annotator=Stand())


def test_items_are_counted_once_with_the_outlet_and_its_licence(tmp_path: Path) -> None:
    store = Store(tmp_path / "corpus.db")
    items = news.feed_items(_kept(), PUBLISHERS)
    first = news.count_news(store, items, annotator=Stand())
    assert (first.counted, first.held, first.full) == (3, 0, 1)
    assert first.tokens == 7 + 5 + 7 == store.total(WORDS, NEWS)
    assert dict(first.outlets) == {"paper": 2, "paper-sport": 1}
    with sqlite3.connect(store.file) as db:
        rows = set(db.execute("SELECT tbl, register, source, licence, tool FROM contribution"))
    assert {row[0] for row in rows} == {"words", "phrases", "roots"}
    assert {row[1:] for row in rows} == {
        (NEWS, "feed:paper", f"{news.RESERVED}; {news.COUNTS_ONLY}", "stand-in/1"),
        (NEWS, "feed:paper-sport", f"CC BY 4.0; {news.COUNTS_ONLY}", "stand-in/1"),
    }
    # One article is one unit, so its phrases are kept whole rather than floored away.
    assert store.top("phrases", NEWS, limit=100)
    again = Stand()
    second = news.count_news(store, items, annotator=again)
    assert (second.counted, second.held, again.read) == (0, 3, 0)
    # Under another annotator too: the text is gone, and an item is never counted twice.
    third = news.count_news(store, items, annotator=SimpleNamespace(name="other/2"))
    assert (third.counted, third.held) == (0, 3)
    assert news.last_round(store)


def test_a_night_stops_at_its_caps_outlet_by_outlet(tmp_path: Path) -> None:
    kept = {
        PAPER.feed: [_item(n) for n in range(1, 11)],
        SECTION.feed: [_item(n) for n in range(11, 14)],
    }
    items = news.feed_items(kept, PUBLISHERS)
    order = news.in_turn(items)
    assert [one.outlet for one in order[:6]] == ["paper", "paper-sport"] * 3
    assert order[0].published >= order[2].published, "each outlet's newest first"
    store = Store(tmp_path / "corpus.db")
    by_items = news.count_news(store, items, annotator=Stand(), most=4)
    assert (by_items.counted, by_items.left) == (4, 9)
    assert "4 items" in by_items.stopped
    # Seven words an item: two fit under fifteen words, a third would not.
    by_words = news.count_news(store, items, annotator=Stand(), words=15)
    assert (by_words.counted, by_words.held, by_words.left) == (2, 4, 7)
    assert "15 words" in by_words.stopped


def test_no_article_text_reaches_a_file_a_row_or_a_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    kept = {
        PAPER.feed: [
            _item(1, words="u1 u2 u3 u4 u5 u6"),
            _item(2, words="v1 v2 v3 v4 v5 v6"),
            _item(3, full="x1 x2 x3 x4 x5\n\nx6 x7 x8 x9"),
        ]
    }
    items = news.feed_items(kept, PUBLISHERS)
    store = Store(tmp_path / "corpus.db")
    result = news.count_news(store, items, annotator=Stand(fail_on="v1"))
    assert (result.counted, result.failed) == (2, 1)
    news.log.info("tables: news %s", result)
    written = sorted(path.name for path in tmp_path.rglob("*") if path.is_file())
    assert all(name.startswith("corpus.db") for name in written), written
    with sqlite3.connect(store.file) as db:
        dump = "\n".join(db.iterdump())
    said = caplog.text + str(result) + repr(items)
    for item in items:
        for line in item.text.splitlines():
            if line:
                assert line not in dump, "no line of an item is stored"
                assert line not in said, "no line of an item is logged"
        # Nor any four words in a row, in either case: a phrase is three lemmas at most.
        words = item.text.split()
        for at in range(len(words) - 3):
            run = " ".join(words[at : at + 4])
            assert run not in dump and run.upper() not in dump
    assert "https://paper.test" not in dump, "an address is a hash"


def test_a_news_build_in_a_readers_home_is_never_counted_here(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The round reads the feeds and no folder: the same article built privately by a
    reader (under `p1/`) adds nothing, while the feed's own item is counted."""
    monkeypatch.setenv("TARGUM_LEDGER", str(tmp_path / "corpus.db"))
    library = tmp_path / "targums"
    private = library / "p1" / "article"
    private.mkdir(parents=True)
    document = {"content_hash": "e" * 64, "source": "https://paper.test/a/1"}
    (private / "document.json").write_text(json.dumps(document), encoding="utf-8")
    annotation = {
        "document_hash": "e" * 64,
        "language": "he",
        "annotator": "dicta/test/1",
        "tokens": {"s0": [{"start": 0, "end": 1, "surface": "q", "lemma": "q9", "pos": "NOUN"}]},
    }
    (private / "annotation.json").write_text(json.dumps(annotation), encoding="utf-8")
    ledger.mirror_text(private, library)
    store = Store(tmp_path / "corpus.db")
    assert tables.public_text(private, library) is None
    result = news.count_news(store, news.feed_items(_kept(), PUBLISHERS), annotator=Stand())
    assert result.counted == 3
    with sqlite3.connect(store.file) as db:
        units = {row[0] for row in db.execute("SELECT unit FROM contribution")}
        keys = {row[0] for row in db.execute("SELECT key FROM tally")}
    assert "e" * 64 not in units
    assert "q9" not in keys and "Q9" not in keys
    assert all(unit.startswith(news.PREFIX) for unit in units)


def test_the_round_is_due_once_a_night_after_its_hour() -> None:
    early = datetime(2026, 11, 2, 1, 0, tzinfo=UTC)
    late = datetime(2026, 11, 2, 1, 45, tzinfo=UTC)
    assert not news.due("", early)
    assert news.due("", late)
    assert news.due("2026-11-01T01:40:00+00:00", late)
    assert not news.due("2026-11-02T01:31:00+00:00", late)
    assert not news.due("2026-11-02T01:31:00+00:00", late.replace(hour=23))


def test_the_thread_returns_at_once_where_the_ledger_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TARGUM_LEDGER", raising=False)
    monkeypatch.setattr(news, "FIRST_S", 60.0)
    news.keep_counting()  # would wait a minute before it looked, were the ledger on


def test_the_round_reads_the_servers_feeds_and_pulls_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum.chat import sources as sources_module
    from targum.chat import tools as tools_module

    monkeypatch.setattr(tools_module.FEEDS, "kept", _kept)
    monkeypatch.setattr(sources_module, "load", lambda: PUBLISHERS)

    def refuse(*_: Any, **__: Any) -> Any:
        raise AssertionError("the round pulls nothing")

    monkeypatch.setattr(tools_module.FEEDS, "pull", refuse)
    result = news.run_round(Store(tmp_path / "corpus.db"), annotator=Stand())
    assert result.counted == 3
    assert result.memory.get("after", 0) >= 0
