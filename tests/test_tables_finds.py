"""Public finds count into the matching yardstick registers as counts only (David,
2026-11-01; design.md §12, "Public finds count into the yardsticks, as counts").

Every word here is synthetic: placeholder lemmas, no sentence of any text.
"""

from __future__ import annotations

import json
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from test_tables_news import Stand, _publisher
from typer.testing import CliRunner

from targum.accounts import Store as AccountStore
from targum.cli import app
from targum.finds import pool, score
from targum.tables import finds, news
from targum.tables.registers import NEWS, SOCIAL, VIDEO
from targum.tables.store import Contribution, Store
from targum.tables.words import WORDS
from targum.weekly.feeds import Item

#: Stands for the words of a find: in the pool's title, and in no row the tables hold.
TITLE = "zz-a-finds-own-title-zz"


@pytest.fixture
def accounts(tmp_path: Path) -> AccountStore:
    return AccountStore(tmp_path / "targum.db")


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Store:
    file = tmp_path / "corpus.db"
    monkeypatch.setenv("TARGUM_LEDGER", str(file))
    return Store(file)


def keep(accounts: AccountStore, source: str, url: str, bag: dict[str, int], **more: Any) -> int:
    return pool.add(
        accounts,
        language=more.pop("language", "he"),
        source=source,
        url=url,
        bag=bag,
        tokens=sum(bag.values()),
        unresolved=0,
        rung=3,
        title=TITLE,
        host=more.pop("host", "www.example.co.il"),
        **more,
    )


def words(store: Store, register: str) -> dict[str, int]:
    return dict(store.top(WORDS, register, limit=100, weighed=False))


def test_the_tool_is_the_scorers_map() -> None:
    assert finds.TOOL == score.VERSION


def test_a_video_find_counts_into_video_as_counts_and_nothing_else(
    accounts: AccountStore, store: Store
) -> None:
    url = "https://www.youtube.com/watch?v=abc123"
    keep(accounts, "youtube", url, {"w1": 4, "w2": 1}, host="www.youtube.com", medium="video")
    found = finds.fold_finds(store, finds.public_finds(accounts))
    assert found.counted == 1 and found.by_register == {VIDEO: 1}
    assert words(store, VIDEO) == {"w1": 4, "w2": 1}
    assert store.total("phrases") == 0 and store.total("roots") == 0, "a bag has no order"
    unit = finds.unit_of(url)
    with closing(store._connect()) as db:
        row = db.execute(
            "SELECT unit, source, licence, tool FROM contribution WHERE register = ?", (VIDEO,)
        ).fetchone()
    assert tuple(row) == (unit, "finds:youtube", "counts only; text never stored", "forms/1")
    held = store.file.read_bytes()
    for leak in (TITLE, "youtube.com", "abc123"):
        assert leak.encode() not in held, f"{leak} reached the tables"


def test_a_second_night_counts_nothing_twice_and_the_counts_outlive_the_find(
    accounts: AccountStore, store: Store
) -> None:
    then = pool.now_ms() - 8 * pool.DAY_MS
    keep(accounts, "news", "https://www.example.co.il/a", {"w1": 3}, at=then)
    assert finds.fold_finds(store, finds.public_finds(accounts)).counted == 1
    again = finds.fold_finds(store, finds.public_finds(accounts))
    assert (again.counted, again.held) == (0, 1)
    assert pool.expire(accounts) == 1, "a week of news"
    assert finds.fold_finds(store, finds.public_finds(accounts)).counted == 0
    assert words(store, NEWS) == {"w1": 3}, "the count persists like a corpus's"


def test_web_finds_are_sorted_by_host_as_imports_are(accounts: AccountStore, store: Store) -> None:
    keep(accounts, "web", "https://www.youtube.com/watch?v=v1", {"vid": 1})
    keep(accounts, "web", "https://www.instagram.com/p/xyz/", {"soc": 1})
    keep(accounts, "web", "https://www.paper.co.il/story", {"new": 1})
    keep(accounts, "web", "https://blog.example.org/post", {"none": 1})
    found = finds.fold_finds(store, finds.public_finds(accounts, news={"paper.co.il"}))
    assert found.by_register == {VIDEO: 1, SOCIAL: 1, NEWS: 1}
    assert words(store, VIDEO) == {"vid": 1}
    assert words(store, SOCIAL) == {"soc": 1}
    assert words(store, NEWS) == {"new": 1}
    assert "none" not in json.dumps(store.registers(WORDS)) and store.total(WORDS) == 3


def test_a_dropped_row_another_language_or_an_empty_bag_is_never_counted(
    accounts: AccountStore, store: Store
) -> None:
    pool.drop(accounts, language="he", source="news", url="https://x.co.il/d", reason="words")
    keep(accounts, "news", "https://x.co.il/ru", {"w1": 1}, language="ru")
    keep(accounts, "news", "https://x.co.il/e", {"w1": 0})
    assert finds.public_finds(accounts) == []


def test_an_item_the_feeds_counted_is_not_counted_again(
    accounts: AccountStore, store: Store
) -> None:
    link = "https://paper.test/a/1"
    paper = _publisher("paper", "https://paper.test/rss")
    item = Item(
        title="t1",
        link=link,
        summary="s1 s2",
        published=datetime(2026, 11, 1, tzinfo=UTC),
        full_text="",
    )
    news.count_news(store, news.feed_items({paper.feed: [item]}, [paper]), annotator=Stand())
    before = words(store, NEWS)
    keep(accounts, "news", link + "#top", {"other": 9}, host="paper.test")
    found = finds.fold_finds(store, finds.public_finds(accounts))
    assert (found.counted, found.in_feeds) == (0, 1)
    assert words(store, NEWS) == before


def test_a_find_counted_before_the_feeds_is_retired_when_they_count_it(
    accounts: AccountStore, store: Store
) -> None:
    link = "https://paper.test/a/2"
    keep(accounts, "news", link, {"other": 9}, host="paper.test")
    assert finds.fold_finds(store, finds.public_finds(accounts)).counted == 1
    paper = _publisher("paper", "https://paper.test/rss")
    item = Item(
        title="t2",
        link=link,
        summary="s1",
        published=datetime(2026, 11, 1, tzinfo=UTC),
        full_text="",
    )
    news.count_news(store, news.feed_items({paper.feed: [item]}, [paper]), annotator=Stand())
    found = finds.fold_finds(store, finds.public_finds(accounts))
    assert (found.retired, found.in_feeds, found.counted) == (1, 1, 0)
    assert "other" not in words(store, NEWS), "the feed's count stands alone"
    assert set(words(store, NEWS)) == {"T2", "S1"}


def test_a_part_of_speech_is_borrowed_from_the_shelf(accounts: AccountStore, store: Store) -> None:
    shelf = Contribution(WORDS, "literature", "doc1", "s", "l", "dicta/1", "words/1")
    store.write(shelf, {("glue", "ADP"): 50, ("glue", "NOUN"): 1, ("thing", "NOUN"): 5})
    keep(accounts, "youtube", "https://www.youtube.com/watch?v=x", {"glue": 7, "thing": 2})
    finds.fold_finds(store, finds.public_finds(accounts))
    assert words(store, VIDEO) == {"glue": 7, "thing": 2}
    assert dict(store.top(WORDS, VIDEO)) == {"thing": 2}, "a closed class is not weighed"


def test_only_a_sealed_find_is_folded(store: Store) -> None:
    forged = finds.PublicFind(unit="finds:x", kind="web", register=NEWS, bag={"w": 1})
    with pytest.raises(TypeError):
        finds.fold_finds(store, [forged])


def test_a_readers_private_build_of_a_find_is_never_counted(
    tmp_path: Path, accounts: AccountStore, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Watch builds a find as the reader's own import, in their home. The finds fold
    reads the pool's bag and nothing of the home, and with the imports switch off the
    home is never read at all."""
    monkeypatch.delenv("TARGUM_IMPORT_COUNTS", raising=False)
    url = "https://www.youtube.com/watch?v=mine"
    keep(accounts, "youtube", url, {"w1": 2})
    library = tmp_path / "targums"
    folder = library / "p7" / "mine"
    folder.mkdir(parents=True)
    document_hash = "ab" * 32
    (folder / "document.json").write_text(
        json.dumps({"content_hash": document_hash, "source": url, "ingester": "youtube/1"}),
        encoding="utf-8",
    )
    token = {"start": 0, "end": 1, "surface": "x", "lemma": "private", "pos": "NOUN"}
    (folder / "annotation.json").write_text(
        json.dumps(
            {
                "document_hash": document_hash,
                "language": "he",
                "annotator": "dicta/test/1",
                "tokens": {"s0": [token]},
            }
        ),
        encoding="utf-8",
    )
    ran = CliRunner().invoke(
        app,
        ["tables", "sweep", "--library", str(library), "--store", str(accounts.path)],
    )
    assert ran.exit_code == 0, ran.output
    assert "Counted 1 finds" in ran.output
    assert words(store, VIDEO) == {"w1": 2}
    assert store.variants(WORDS, ["private"]) == {}, "nothing of the home"
