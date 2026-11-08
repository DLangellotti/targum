"""Hebrew Wikipedia and Wikivoyage, nightly, through the MediaWiki API (targum-internal#622;
David, 2026-11-05; design.md §12, "Hebrew Wikipedia and Wikivoyage come back through their
own API").

Offline: the API, robots.txt and the network are fixtures. Every word is synthetic.
"""

from __future__ import annotations

import io
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from typer.testing import CliRunner

from targum import promote
from targum.accounts import Store
from targum.cli import app
from targum.finds import chips, pool, robots, score, screen, web, wiki
from targum.licensing import changes_owed
from targum.render.builder import text_credit_in

LETTERS = "אבגדהזחטלמנסעפקרשת"


def general(n: int) -> str:
    return "מילה" + LETTERS[n // len(LETTERS)] + LETTERS[n % len(LETTERS)]


G1, G2 = general(1), general(2)


def article(n: int) -> str:
    """A long enough page, each one different so none is pooled as another's copy."""
    return " ".join(["ביצה"] * 6 + [G1] * (90 + n) + [G2] * 4)


AT = int(datetime(2026, 11, 30, 0, 12, tzinfo=UTC).timestamp() * 1000)
WP = "he.wikipedia.org"
WV = "he.wikivoyage.org"


def forms() -> score.Forms:
    words = ["ביצה", G1, G2]
    return score.Forms(
        language="he",
        forms={word: word for word in words},
        ranks={word: at + 1 for at, word in enumerate(words)},
    )


@pytest.fixture(autouse=True)
def clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(wiki.FLAG, raising=False)
    monkeypatch.delenv(web.FLAG, raising=False)
    monkeypatch.delenv(pool.BUDGET_ENV, raising=False)


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "targum.db")


def url_of(host: str, title: str) -> str:
    return f"https://{host}/wiki/{title}"


class Api:
    """Both wikis' APIs: every phrase finds `per` pages titled after it, unless
    `answers` says otherwise; every page has a long enough text."""

    def __init__(
        self,
        per: int = 3,
        answers: dict[tuple[str, str], list[dict[str, Any]]] | None = None,
        texts: dict[str, str] | None = None,
    ) -> None:
        self.per = per
        self.answers = answers or {}
        self.texts = texts or {}
        self.searched: list[tuple[str, str]] = []
        self.read: list[tuple[str, str]] = []
        self.urls: list[str] = []

    def __call__(self, url: str) -> Any:
        self.urls.append(url)
        parsed = urlparse(url)
        host = parsed.hostname or ""
        asked = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        assert parsed.path == "/w/api.php" and asked["format"] == "json"
        if asked.get("generator") == "search":
            phrase = asked["gsrsearch"]
            self.searched.append((host, phrase))
            rows = self.answers.get((host, phrase))
            if rows is None:
                rows = [
                    {
                        "ns": 0,
                        "title": f"{phrase} {n}",
                        "index": n + 1,
                        "canonicalurl": url_of(host, f"{phrase.replace(' ', '_')}_{n}"),
                    }
                    for n in range(self.per)
                ]
            return {"query": {"pages": rows}}
        title = asked["titles"]
        self.read.append((host, title))
        text = self.texts.get(title, article(len(self.read)))
        return {"query": {"pages": [{"ns": 0, "title": title, "extract": text}]}}


ALLOW = robots.Robots(read=lambda url: "User-agent: *\nDisallow: /w/\nDisallow: /wiki/Special:\n")


def night(store: Store, api: Api, **more: Any) -> wiki.Night:
    return wiki.refresh(
        store,
        get=api,
        robots=more.pop("robots", ALLOW),
        forms_for=lambda language: forms(),
        at=more.pop("at", AT),
        **more,
    )


def kept(store: Store) -> list[dict[str, Any]]:
    store.db.row_factory = None
    rows = store.db.execute(
        "SELECT url, host, publisher, licence, licence_url, licence_from, source, topics,"
        " published, expires, found FROM find WHERE screen = 'kept' ORDER BY id"
    ).fetchall()
    names = (
        "url host publisher licence licence_url licence_from source topics published expires found"
    ).split()
    return [dict(zip(names, row, strict=True)) for row in rows]


# -- the user agent ------------------------------------------------------------------


def test_every_request_names_targum_and_its_own_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert "targum" in wiki.USER_AGENT and "https://targum.page" in wiki.USER_AGENT
    assert "hello@targum.page" in wiki.USER_AGENT
    assert "gmail" not in wiki.USER_AGENT and "david" not in wiki.USER_AGENT.lower()
    sent: list[Any] = []

    def urlopen(request: Any, timeout: float = 0) -> Any:
        sent.append(request)
        return io.BytesIO(b'{"query": {"pages": []}}')

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    monkeypatch.setattr(wiki, "PAUSE_S", 0.0)
    assert wiki.search(wiki.WIKIS[0], "ספורט", wiki._get) == []
    (request,) = sent
    assert request.get_header("User-agent") == wiki.USER_AGENT
    assert request.full_url.startswith("https://he.wikipedia.org/w/api.php?")


# -- a night -------------------------------------------------------------------------


def test_a_page_is_kept_as_a_web_find_under_cc_by_sa_credited_to_the_contributors(
    store: Store,
) -> None:
    found = night(store, Api(per=1))
    rows = kept(store)
    assert found.kept == len(rows) > 0
    first = rows[0]
    phrase = chips.CHIPS[0].phrases["he"]
    assert first["url"] == url_of(WP, f"{phrase}_0")
    assert first["host"] == WP
    assert first["publisher"] == "Wikipedia contributors"
    assert first["licence"] == "CC BY-SA 4.0"
    assert first["licence_url"] == "https://creativecommons.org/licenses/by-sa/4.0/"
    assert first["licence_from"] == "publisher"
    assert first["source"] == "web"
    assert first["topics"] == chips.tag(chips.CHIPS[0].code)
    assert first["published"] == 0, "a wiki page states no day it was published"
    assert first["expires"] - first["found"] == pool.KEEP_DAYS["web"] * pool.DAY_MS
    voyage = [row for row in rows if row["host"] == WV]
    assert voyage and all(row["publisher"] == "Wikivoyage contributors" for row in voyage)


def test_the_phrases_are_the_chips_own_and_wikivoyage_takes_only_the_travel_ones(
    store: Store,
) -> None:
    api = Api(per=0)
    night(store, api)
    on_wp = [phrase for host, phrase in api.searched if host == WP]
    on_wv = [phrase for host, phrase in api.searched if host == WV]
    assert on_wp == [chip.phrases["he"] for chip in chips.CHIPS]
    travel = {"travel", "food", "nature", "history", "israel", "holidays"}
    assert on_wv == [chip.phrases["he"] for chip in chips.CHIPS if chip.code in travel]
    assert len(set(wiki.WIKIS[1].chips) & set(chips.BY_CODE)) == len(wiki.WIKIS[1].chips)


def test_five_pages_a_wiki_a_night_one_to_a_phrase(store: Store) -> None:
    api = Api(per=3)
    found = night(store, api)
    read = Counter(host for host, _ in api.read)
    assert read == {WP: web.HOST_MOST, WV: web.HOST_MOST}
    assert found.hosts == read
    titles = [title for host, title in api.read if host == WP]
    assert all(title.endswith(" 0") for title in titles), "the best page of each phrase"
    assert len(api.searched) == 2 * web.HOST_MOST


def test_tomorrow_starts_where_tonight_stopped(store: Store) -> None:
    night(store, Api(per=1))
    api = Api(per=1)
    night(store, api, at=AT + pool.DAY_MS)
    first = next(phrase for host, phrase in api.searched if host == WP)
    assert first == chips.CHIPS[web.HOST_MOST].phrases["he"]


def test_a_page_robots_refuses_is_never_read(store: Store) -> None:
    phrase = chips.CHIPS[0].phrases["he"]
    api = Api(
        per=0,
        answers={
            (WP, phrase): [
                {"ns": 0, "title": "שם", "index": 1, "canonicalurl": url_of(WP, "Special:x")},
                {"ns": 0, "title": "עוד", "index": 2, "canonicalurl": url_of(WP, "עוד")},
            ]
        },
    )
    found = night(store, api)
    assert ("he.wikipedia.org", "שם") not in api.read
    assert (WP, "עוד") in api.read
    assert found.dropped["robots"] == 1


def test_disambiguation_and_other_namespaces_are_skipped(store: Store) -> None:
    phrase = chips.CHIPS[0].phrases["he"]
    api = Api(
        per=0,
        answers={
            (WP, phrase): [
                {
                    "ns": 0,
                    "title": "פירושונים",
                    "index": 1,
                    "canonicalurl": url_of(WP, "פירושונים"),
                    "pageprops": {"disambiguation": ""},
                },
                {"ns": 4, "title": "ויקיפדיה:דף", "index": 2, "canonicalurl": url_of(WP, "x")},
            ]
        },
    )
    night(store, api)
    assert not [title for host, title in api.read if host == WP]


def test_the_screens_hold_and_a_short_page_is_dropped(store: Store) -> None:
    phrase = chips.CHIPS[0].phrases["he"]
    api = Api(
        per=0,
        answers={
            (WP, phrase): [
                {"ns": 0, "title": "קצר", "index": 1, "canonicalurl": url_of(WP, "קצר")},
            ]
        },
        texts={"קצר": "מילה אחת"},
    )
    found = night(store, api)
    assert found.dropped["short"] == 1 and not kept(store)


def test_a_denied_wiki_is_not_asked(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(screen, "host_denied", lambda host, also=(): host == WV)
    api = Api(per=1)
    night(store, api)
    assert not [one for one in api.searched if one[0] == WV]


def test_a_failing_wiki_ends_its_own_night_and_writes_the_run(store: Store) -> None:
    def broken(url: str) -> Any:
        raise OSError("down")

    found = night(store, broken)  # type: ignore[arg-type]
    assert "search failed" in found.stopped
    (note,) = store.db.execute("SELECT note FROM find_run WHERE source = 'wiki'").fetchone()
    assert json.loads(note)["searches"] == 0


def test_the_night_spends_nothing(store: Store) -> None:
    night(store, Api(per=1))
    (spent,) = store.db.execute("SELECT spent FROM find_run WHERE source = 'wiki'").fetchone()
    assert spent == 0


# -- with the search -----------------------------------------------------------------


def test_the_search_counts_what_the_wikis_read_against_five_a_host(store: Store) -> None:
    hit = web.Hit(url_of(WP, "דף_מהחיפוש"), "דף מהחיפוש")
    asked = chips.CHIPS[0].phrases["he"]
    read: list[str] = []

    def pages(url: str) -> tuple[str, int]:
        read.append(url)
        return article(0), 0

    web.refresh(
        store,
        ask=lambda query: web.Searched(hits=[hit] if query == asked else [], searches=1, cost=0.01),
        read=pages,
        robots=ALLOW,
        forms_for=lambda language: forms(),
        publishers=[],
        hosts={WP: web.HOST_MOST},
        at=AT,
    )
    assert read == []


# -- the credit ----------------------------------------------------------------------


def test_a_wiki_find_keeps_its_licence_where_the_page_tag_is_not_read(store: Store) -> None:
    night(store, Api(per=1))
    (find_id,) = store.db.execute("SELECT id FROM find WHERE screen = 'kept' LIMIT 1").fetchone()
    found = pool.get(store, int(find_id), at=AT)
    assert found is not None
    licence, where, which = promote.find_licence(found, read=lambda url: "")
    assert (licence, where, which) == (wiki.LICENCE, wiki.LICENCE_URL, "publisher")
    assert promote.clears(licence)


def test_a_joined_wiki_copy_says_targum_changed_it(tmp_path: Path) -> None:
    assert changes_owed(wiki.LICENCE)
    (tmp_path / "credit.json").write_text(
        json.dumps(
            {
                "outlet": "Wikipedia contributors",
                "source": url_of(WP, "כדורסל"),
                "licence": wiki.LICENCE,
                "licence_url": wiki.LICENCE_URL,
                "licence_from": "publisher",
            }
        ),
        encoding="utf-8",
    )
    said = text_credit_in(tmp_path)
    assert said is not None
    assert said["outlet"] == "Wikipedia contributors"
    assert said["source"] == url_of(WP, "כדורסל")
    assert said["licence"] == "CC BY-SA 4.0" and said["changed"] == "yes"


# -- the switch ----------------------------------------------------------------------


def test_off_unless_the_box_says_so(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert not wiki.on()
    said = CliRunner().invoke(app, ["finds", "web", "--store", str(tmp_path / "t.db")])
    assert said.exit_code == 0 and "off" in said.output
    ran: list[Any] = []

    def wikis(store: Store, language: str = "he") -> wiki.Night:
        ran.append(language)
        return wiki.Night(hosts=Counter({WP: 2}))

    monkeypatch.setattr(wiki, "refresh", wikis)
    monkeypatch.setattr(web, "refresh", lambda *a, **k: ran.append("web"))
    monkeypatch.setenv(wiki.FLAG, "1")
    said = CliRunner().invoke(app, ["finds", "web", "--store", str(tmp_path / "t.db")])
    assert said.exit_code == 0, said.output
    # Hebrew's wikis, then Russian's (targum-internal#635), and no search.
    assert ran == ["he", "ru"] and "The web search is off" in said.output
