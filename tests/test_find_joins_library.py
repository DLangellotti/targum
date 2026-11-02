"""A find with an open licence joins the library, naming nobody (design.md §12, "A suggested
text says where it comes from, and a find with an open licence joins the library",
2026-11-02).

The licence bar, where the licence is read, one copy per original, no trace of the reader,
the back office's take-down, and the source line's outlet and link.
"""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from targum import catalogue, promote, source_line
from targum.accounts import Store
from targum.finds import pool
from targum.serve import Job, Library

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "catalogue.json"
URL = "https://he.globalvoices.org/2026/11/02/a-story/"
EMAIL = "reader-who-opened-it@example.com"


@pytest.fixture
def shelf(tmp_path: Path, monkeypatch: Any):
    copy = tmp_path / "catalogue.json"
    shutil.copy(FIXTURE, copy)
    monkeypatch.setenv("TARGUM_CATALOGUE", str(copy))
    before = list(catalogue.CATALOGUE)
    collections = list(catalogue.COLLECTIONS)
    yield copy
    catalogue.CATALOGUE[:] = before
    catalogue.COLLECTIONS[:] = collections


@pytest.fixture
def world(tmp_path: Path):
    store = Store(tmp_path / "db")
    out = tmp_path / "out"
    out.mkdir()
    library = Library(out, store=store)
    owner = 41
    home = out / f"p{owner}"
    return library, store, home, owner


def a_find(store: Store, url: str = URL, **fields: Any) -> int:
    defaults: dict[str, Any] = {
        "language": "he",
        "source": "news",
        "url": url,
        "bag": {"מילה": 3},
        "tokens": 300,
        "unresolved": 0,
        "rung": 2,
        "title": "סיפור",
        "host": "he.globalvoices.org",
        "publisher": "Global Voices",
        "published": 1_793_000_000_000,
    }
    defaults.update(fields)
    return pool.add(store, **defaults)


def built(home: Path, name: str, source: str) -> Path:
    folder = home / name
    (folder / "reader").mkdir(parents=True)
    (folder / "reader" / "index.html").write_text("<html>the reader's own page</html>")
    (folder / "shelf.json").write_text(json.dumps({"home": str(home)}))
    (folder / "deck.apkg").write_text("the reader's words")
    (folder / ".meta.json").write_text("{}")
    (folder / "document.json").write_text(
        json.dumps(
            {
                "schema_version": 4,
                "source": source,
                "title": "סיפור",
                "author": "",
                "language": "he",
                "blocks": [{"id": "b0000", "kind": "paragraph", "level": 0, "text": "מילה " * 40}],
                "content_hash": "h",
                "source_hash": "s",
                "ingester": "test",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (folder / "segments.json").write_text("{}")
    return folder


def opened(home: Path, name: str, find_id: int, owner: int) -> Job:
    return Job(
        id=f"job-{name}-7f3a",
        source=URL,
        owner=owner,
        home=home,
        stage="done",
        reader=f"{name}/reader/index.html",
        options={"via": "find", "find": find_id},
    )


def drawn(where: Path) -> None:
    (where / "reader").mkdir(exist_ok=True)
    (where / "reader" / "index.html").write_text("<html>the shelf's page</html>")


def no_tag(_url: str) -> str:
    return "<html><body><p>All rights reserved, says the footer.</p></body></html>"


# -- the bar -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "licence",
    [
        "Public Domain",
        "CC0 1.0",
        "CC BY 4.0",
        "CC BY-SA 4.0",
        "CC BY-NC 4.0",
        "CC BY-NC-SA 4.0",
        "Creative Commons Attribution license (reuse allowed)",
        "Public Domain Mark 1.0",
    ],
)
def test_the_bar_lets_in_the_list_david_named(licence: str) -> None:
    assert promote.clears(licence)


@pytest.mark.parametrize(
    "licence",
    [
        "CC BY-ND 4.0",
        "CC BY-NC-ND 4.0",
        "",
        "All rights reserved",
        "BBC — all rights reserved",
        "State of Israel — free use, attribution required",
        "MIT",
        "Copyright, updated 2020",
    ],
)
def test_the_bar_refuses_nd_reserved_unknown_and_terms_not_listed(licence: str) -> None:
    assert not promote.clears(licence)


# -- where the licence is read -------------------------------------------------------


@pytest.mark.parametrize(
    ("html", "said"),
    [
        ('<link rel="license" href="https://creativecommons.org/licenses/by/4.0/">', "CC BY 4.0"),
        (
            '<a rel="nofollow license" href="https://creativecommons.org/licenses/by-sa/3.0/">x</a>',
            "CC BY-SA 3.0",
        ),
        (
            '<meta name="dcterms.license" content="https://creativecommons.org/publicdomain/zero/1.0/">',
            "CC0 1.0",
        ),
        (
            '<script type="application/ld+json">{"@type": "NewsArticle", '
            '"license": "https://creativecommons.org/licenses/by-nc-sa/4.0/"}</script>',
            "CC BY-NC-SA 4.0",
        ),
    ],
)
def test_a_page_states_its_licence_in_its_markup(html: str, said: str) -> None:
    licence, address = promote.page_licence(f"<html><head>{html}</head><body></body></html>")
    assert licence == said
    assert address.startswith("https://creativecommons.org/")


def test_words_and_other_addresses_are_not_a_licence() -> None:
    assert promote.page_licence(no_tag("")) == ("", "")
    assert promote.page_licence('<link rel="license" href="https://example.com/terms">') == (
        "",
        "",
    )
    assert promote.page_licence("<html><p>Licensed CC BY 4.0</p></html>") == ("", "")


def test_the_page_tag_comes_first_then_the_outlets_site_wide_statement(world) -> None:
    _, store, _, _ = world
    found = pool.get(
        store,
        a_find(
            store,
            licence="CC BY 3.0",
            licence_url="https://globalvoices.org/about/",
            licence_from="publisher",
        ),
    )
    assert found is not None
    tagged = '<link rel="license" href="https://creativecommons.org/licenses/by-sa/4.0/">'
    assert promote.find_licence(found, lambda _u: tagged)[::2] == ("CC BY-SA 4.0", "page")
    assert promote.find_licence(found, no_tag) == (
        "CC BY 3.0",
        "https://globalvoices.org/about/",
        "publisher",
    )


def test_a_video_reads_its_own_licence_field_and_never_its_page(world) -> None:
    _, store, _, _ = world
    found = pool.get(
        store,
        a_find(
            store,
            url="https://www.youtube.com/watch?v=abcdefghijk",
            medium="video",
            licence="Creative Commons Attribution license (reuse allowed)",
            licence_url="https://creativecommons.org/licenses/by/3.0/",
            licence_from="youtube",
        ),
    )
    assert found is not None

    def never(_url: str) -> str:
        raise AssertionError("a video's page is not read")

    assert promote.find_licence(found, never)[2] == "youtube"


# -- joining -------------------------------------------------------------------------


def test_a_find_on_an_open_licence_joins_credited_and_naming_nobody(world, shelf) -> None:
    library, store, home, owner = world
    find_id = a_find(
        store,
        licence="CC BY 3.0",
        licence_url="https://globalvoices.org/about/",
        licence_from="publisher",
    )
    built(home, "story-he", URL)
    job = opened(home, "story-he", find_id, owner)
    entry = promote.join_find(
        library, store, job, read=no_tag, render=drawn, today=date(2026, 11, 2)
    )
    assert entry is not None
    assert entry["source"] == URL
    assert entry["credit"] == "Global Voices"
    assert (entry["licence"], entry["licence_from"]) == ("CC BY 3.0", "publisher")
    assert entry["licence_url"] == "https://globalvoices.org/about/"
    assert entry["added"] == "2026-11-02"
    assert entry["id"] == promote.joined_name(URL)
    # On the shelf, opened as a built text, its own page drawn and its credit beside it.
    shelf_copy = library.shared / entry["id"]
    assert (shelf_copy / "reader" / "index.html").read_text() == "<html>the shelf's page</html>"
    credit = json.loads((shelf_copy / "credit.json").read_text())
    assert (credit["outlet"], credit["source"]) == ("Global Voices", URL)
    assert library.built_from(library.shared, URL) == entry["id"]
    # And in the catalogue.
    assert catalogue.matching(URL) is not None
    assert [row["title"] for row in store.joined()] == ["סיפור"]
    # The reader's own copy is untouched.
    assert (home / "story-he" / "reader" / "index.html").read_text() == (
        "<html>the reader's own page</html>"
    )


def test_nothing_written_names_the_reader(world, shelf) -> None:
    library, store, home, owner = world
    find_id = a_find(store, licence="CC BY 3.0", licence_from="publisher")
    built(home, "story-he", URL)
    job = opened(home, "story-he", find_id, owner)
    entry = promote.join_find(library, store, job, read=no_tag, render=drawn)
    assert entry is not None
    traces = [job.id, str(home), home.name, EMAIL, "story-he"]
    written = [json.dumps(entry, ensure_ascii=False), shelf.read_text(encoding="utf-8")]
    written += [json.dumps(row, ensure_ascii=False) for row in store.joined()]
    for path in (library.shared / entry["id"]).rglob("*"):
        if path.is_file():
            written.append(path.read_text(encoding="utf-8", errors="replace"))
            assert path.name not in promote.NOT_COPIED and not path.name.startswith(".")
    catalogue_row = next(
        row
        for row in json.loads(shelf.read_text(encoding="utf-8"))["entries"]
        if row["id"] == entry["id"]
    )
    assert not {"owner", "home", "job", "person", "opened"} & set(catalogue_row)
    for text in written:
        for trace in traces:
            assert trace not in text, trace
    assert f'"{owner}"' not in json.dumps(store.joined())
    # And no proposal row, which would name the reader.
    assert store.proposals() == []


def test_a_second_reader_opening_the_same_find_adds_nothing(world, shelf, tmp_path) -> None:
    library, store, home, owner = world
    find_id = a_find(store, licence="CC BY-SA 4.0", licence_from="publisher")
    built(home, "story-he", URL)
    assert promote.join_find(
        library, store, opened(home, "story-he", find_id, owner), read=no_tag, render=drawn
    )
    other = library.out / "p99"
    built(other, "story-he", URL)
    assert (
        promote.join_find(
            library, store, opened(other, "story-he", find_id, 99), read=no_tag, render=drawn
        )
        is None
    )
    assert len([path for path in library.shared.iterdir() if path.is_dir()]) == 1
    assert len(store.joined()) == 1


@pytest.mark.parametrize("licence", ["", "CC BY-NC-ND 4.0", "All rights reserved"])
def test_a_find_off_the_bar_stays_the_readers_alone(world, shelf, licence: str) -> None:
    library, store, home, owner = world
    find_id = a_find(store, licence=licence, licence_from="publisher" if licence else "")
    built(home, "story-he", URL)
    assert (
        promote.join_find(
            library, store, opened(home, "story-he", find_id, owner), read=no_tag, render=drawn
        )
        is None
    )
    assert not library.shared.exists() or not any(library.shared.iterdir())
    assert catalogue.matching(URL) is None


def test_a_pasted_link_never_joins_this_way(world, shelf) -> None:
    library, store, home, owner = world
    find_id = a_find(store, licence="CC BY 4.0", licence_from="publisher")
    built(home, "story-he", URL)
    job = opened(home, "story-he", find_id, owner)
    job.options = {"to": "en"}
    assert promote.join_find(library, store, job, read=no_tag, render=drawn) is None


def test_the_build_queue_joins_a_find_and_proposes_nothing(world, shelf, monkeypatch) -> None:
    library, store, home, owner = world
    find_id = a_find(store, licence="CC BY 3.0", licence_from="publisher")
    built(home, "story-he", URL)
    monkeypatch.setattr(promote, "read_page", no_tag)
    calls: list[Path] = []

    def joined(lib: Any, st: Any, job: Any, **_: Any) -> None:
        calls.append(job.home)

    monkeypatch.setattr(promote, "join_find", joined)
    assert promote.candidate(library, store, opened(home, "story-he", find_id, owner)) is None
    assert calls == [home]
    assert store.proposals() == []


# -- the back office's take-down ---------------------------------------------------------


def test_take_down_removes_the_entry_and_the_copy_and_it_never_joins_again(world, shelf) -> None:
    library, store, home, owner = world
    find_id = a_find(store, licence="CC BY 3.0", licence_from="publisher")
    built(home, "story-he", URL)
    job = opened(home, "story-he", find_id, owner)
    entry = promote.join_find(library, store, job, read=no_tag, render=drawn)
    assert entry is not None
    assert promote.take_down(library, store, entry["id"])
    assert not (library.shared / entry["id"]).exists()
    assert catalogue.matching(URL) is None
    assert store.joined() == []
    assert [row["state"] for row in store.joined("removed")] == ["removed"]
    assert promote.join_find(library, store, job, read=no_tag, render=drawn) is None
    assert not promote.take_down(library, store, entry["id"])


# -- the source line -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("credit", "outlet"),
    [
        ("Project Ben-Yehuda", "Project Ben-Yehuda"),
        ("Tanach with Ta'amei Hamikra, via Sefaria", "Sefaria"),
        (
            "Kaakaasauro, translated by Lida Balloni (© Lida Balloni, 2018). Via StoryWeaver, "
            "Pratham Books.",
            "StoryWeaver",
        ),
        ("", ""),
    ],
)
def test_the_outlet_is_the_one_the_credit_names(credit: str, outlet: str) -> None:
    assert source_line.outlet_of(credit) == outlet


def entry(**fields: Any) -> catalogue.Entry:
    base: dict[str, Any] = {
        "id": "x",
        "title": "t",
        "author": "",
        "language": "he",
        "source": "",
        "blurb": "",
        "words": 1,
    }
    base.update(fields)
    return catalogue.Entry(**base)


@pytest.mark.parametrize(
    ("source", "licence_url", "page"),
    [
        ("https://benyehuda.org/download/6600.txt", "", "https://benyehuda.org/read/6600"),
        ("sefaria:Ruth", "http://www.tanach.us/Tanach.xml", "https://www.sefaria.org/Ruth"),
        ("video:zIFJ-zRtKKE", "", "https://www.youtube.com/watch?v=zIFJ-zRtKKE"),
        ("wikisource:he:x", "https://he.wikisource.org/wiki/x", "https://he.wikisource.org/wiki/x"),
        # A licence's terms are not where the text lives.
        ("storyweaver:1", "https://creativecommons.org/licenses/by/4.0/", ""),
        ("dialogue:01", "", ""),
    ],
)
def test_a_shelf_text_links_its_own_page_or_nothing(
    source: str, licence_url: str, page: str
) -> None:
    assert source_line.page_of(entry(source=source, licence_url=licence_url)) == page


def test_a_find_names_its_publisher_its_day_and_its_page() -> None:
    line = source_line.for_find(
        {"find": 7, "publisher": "Ynet", "url": "https://www.ynet.co.il/a", "published": 5}
    )
    assert line == {"name": "Ynet", "url": "https://www.ynet.co.il/a", "date": 5}
    # A live look stored no publisher: the site, never a name a model wrote.
    assert source_line.for_find({"find": 8, "url": "https://www.he.wikibooks.org/x"}) == {
        "name": "he.wikibooks.org",
        "url": "https://www.he.wikibooks.org/x",
        "date": 0,
    }


def test_targums_own_writing_has_no_source_line() -> None:
    assert source_line.for_entry(entry(source="dialogue:01", credit="")) is None
    assert source_line.attach({"id": "no-such-entry"}) == {"id": "no-such-entry"}


# -- what a find carries from its source ------------------------------------------------


def test_a_news_item_carries_its_outlets_site_wide_licence() -> None:
    from types import SimpleNamespace

    from targum.chat.sources import Publisher
    from targum.finds import news

    outlet = Publisher(
        key="ovd",
        name="ОВД-Инфо",
        publisher="OVD-Info",
        feed="https://ovd.info/rss",
        homepage="https://ovd.info",
        licence="CC BY 3.0",
        licence_url="https://ovd.info/about",
        language="ru",
    )
    item = SimpleNamespace(link="https://ovd.info/a", title="t", published=None, full_text="")
    (one,) = news.items_from({outlet.feed: [item]}, [outlet])
    assert (one.licence, one.licence_url) == ("CC BY 3.0", "https://ovd.info/about")


def test_a_youtube_find_keeps_the_licence_field_the_api_gave() -> None:
    from targum.finds import youtube

    item = {"id": "abc", "snippet": {"title": "t"}, "status": {"license": "creativeCommon"}}
    assert youtube._video(item, []).licence == "creativeCommon"
    assert youtube._video({"id": "abc", "snippet": {}}, []).licence == ""


def test_the_back_office_lists_what_joined_and_names_no_reader(world, shelf) -> None:
    from targum.backoffice import survey
    from targum.render.builder import back_office_page

    library, store, home, owner = world
    find_id = a_find(
        store,
        licence="CC BY 3.0",
        licence_url="https://globalvoices.org/about/",
        licence_from="publisher",
    )
    built(home, "story-he", URL)
    job = opened(home, "story-he", find_id, owner)
    entry = promote.join_find(library, store, job, read=no_tag, render=drawn)
    assert entry is not None
    page = back_office_page(survey(store.db, today=date(2026, 11, 2)), 30, joined=store.joined())
    assert "Joined from finds" in page
    assert "Global Voices" in page and "CC BY 3.0" in page and "(site-wide)" in page
    assert f'name="id" value="{entry["id"]}"' in page and 'action="/back-office/take-down"' in page
    assert job.id not in page and "story-he" not in page
