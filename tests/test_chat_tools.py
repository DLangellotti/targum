"""The chat's tools, run against a real store and a real shelf.

Ownership is the headline: every tool reads whose shelf and whose words from the context
the server built, and nothing a model passes as an argument can name somebody else.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from targum import level
from targum.accounts import Person, Store
from targum.chat import tools
from targum.serve import Job, Library


def signed_in(store: Store, email: str) -> Person:
    token = store.start_sign_in(email)
    signed = store.finish_sign_in(token)
    assert signed is not None
    return signed[0]


def built(home: Path, name: str, source: str, lemmas: list[str], title: str = "A text") -> None:
    """Enough of a targum on disk for the shelf to list it and coverage to measure it."""
    folder = home / name
    (folder / "reader").mkdir(parents=True)
    (folder / "reader" / "index.html").write_text("<html></html>", encoding="utf-8")
    (folder / "document.json").write_text(
        json.dumps(
            {
                "title": title,
                "language": "he",
                "source": source,
                "content_hash": "h",
                "blocks": [{"text": " ".join(lemmas)}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (folder / "annotation.json").write_text(
        json.dumps(
            {"tokens": {"0001.001-a": [{"lemma": lemma, "pos": "NOUN"} for lemma in lemmas]}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


@pytest.fixture
def world(tmp_path: Path) -> tuple[Library, Store, Person, Path]:
    store = Store(tmp_path / "words.db")
    out = tmp_path / "out"
    out.mkdir()
    library = Library(out, store=store)
    person = signed_in(store, "reader@example.com")
    home = library.home(person)
    built(home, "ruth-he", "test:ruth", ["שלום", "בית", "מלך", "ספר"], "רות")
    built(library.shared, "esther-he", "test:esther", ["שלום", "רעב"], "אסתר")
    store.push(
        person,
        {
            "words": [
                {
                    "language": "he",
                    "lemma": "שלום",
                    "status": 9,
                    "band": "easy",
                    "at": 2,
                    "seen": 2,
                },
                {"language": "he", "lemma": "בית", "status": 9, "band": "easy", "at": 3, "seen": 3},
                {
                    "language": "he",
                    "lemma": "מלך",
                    "status": 2,
                    "band": "moderate",
                    "at": 4,
                    "seen": 4,
                },
            ]
        },
    )
    return library, store, person, home


def context(library: Library, store: Store, person: Person | None, home: Path) -> tools.Ctx:
    return tools.Ctx(
        person=person,
        home=home,
        library=library,
        store=store,
        chat_id="c1",
        level=level.snapshot(store, person.id if person else None, "he"),
    )


def test_every_tool_has_a_closed_schema_and_a_distinct_name() -> None:
    names = [tool.name for tool in tools.REGISTRY]
    assert len(names) == len(set(names))
    for tool in tools.REGISTRY:
        assert tool.schema["additionalProperties"] is False, tool.name
        assert tool.description, tool.name
    for shape in tools.anthropic_tools():
        assert set(shape) == {"name", "description", "input_schema"}


def test_search_library_measures_what_is_on_the_shelf(world) -> None:
    library, store, person, home = world
    ctx = context(library, store, person, home)
    got = tools.search_library(ctx, {"register": "biblical"})
    by_id = {row["id"]: row for row in got["texts"]}
    assert set(by_id) >= {"ruth", "esther"}, "the fixture catalogue's biblical shelf"
    assert by_id["ruth"]["on_shelf"] is True
    assert by_id["ruth"]["reader"] == "/reader/ruth-he/reader/index.html"
    assert by_id["ruth"]["known_share"] == pytest.approx(0.5), "two of four lemmas known"
    assert by_id["esther"]["on_shelf"] is True, "the shared shelf counts as built"
    assert by_id["esther"]["known_share"] == pytest.approx(0.5)
    assert all(row["register"] == "biblical" for row in got["texts"])


def test_search_library_filters_and_says_how_many(world) -> None:
    library, store, person, home = world
    ctx = context(library, store, person, home)
    everything = tools.search_library(ctx, {"limit": 20})
    modern = tools.search_library(ctx, {"register": "modern"})
    assert 0 < modern["count"] < everything["count"]
    assert tools.search_library(ctx, {"query": "no such text anywhere"})["count"] == 0
    assert tools.search_library(ctx, {"query": "Declaration"})["count"] >= 1


def test_open_library_text_says_how(world) -> None:
    library, store, person, home = world
    ctx = context(library, store, person, home)
    ruth = tools.open_library_text(ctx, {"id": "ruth"})
    assert ruth["reader"] and "link" in ruth["how_to_open"]
    unbuilt = next(
        row for row in tools.search_library(ctx, {"limit": 20})["texts"] if not row["on_shelf"]
    )
    told = tools.open_library_text(ctx, {"id": unbuilt["id"]})
    assert told["reader"] == "" and "cannot start one" in told["how_to_open"]
    assert "error" in tools.open_library_text(ctx, {"id": "nope"})


def test_my_shelf_is_mine_and_the_shared_one(world) -> None:
    library, store, person, home = world
    ctx = context(library, store, person, home)
    got = tools.search_my_shelf(ctx, {})
    names = {row["name"]: row for row in got["texts"]}
    assert set(names) == {"ruth-he", "esther-he"}
    assert names["ruth-he"]["shared"] is False and names["esther-he"]["shared"] is True
    assert names["ruth-he"]["known_share"] == pytest.approx(0.5)
    assert tools.search_my_shelf(ctx, {"query": "רות"})["count"] == 1


def test_another_reader_sees_neither_my_shelf_nor_my_words(world) -> None:
    library, store, person, home = world
    other = signed_in(store, "other@example.com")
    ctx = context(library, store, other, library.home(other))
    mine = tools.search_my_shelf(ctx, {})
    assert [row["name"] for row in mine["texts"]] == ["esther-he"], "the shared shelf only"
    assert mine["texts"][0]["known_share"] == pytest.approx(0.0)
    assert tools.my_vocabulary(ctx, {})["known"] == 0
    assert tools.my_progress(ctx, {})["known"] == 0


def test_vocabulary_and_progress_are_counts(world) -> None:
    library, store, person, home = world
    ctx = context(library, store, person, home)
    words = tools.my_vocabulary(ctx, {"limit": 2})
    assert (words["known"], words["learning"]) == (2, 1)
    assert [w["lemma"] for w in words["recent"]] == ["מלך", "בית"], "newest first"
    progress = tools.my_progress(ctx, {})
    assert progress["known"] == 2
    assert progress["ladder"]["note"] == "A guide, not a placement."


def test_suggest_next_leaves_out_what_is_already_mine(world) -> None:
    library, store, person, home = world
    ctx = context(library, store, person, home)
    got = tools.suggest_next(ctx, {"limit": 10})
    ids = [row["id"] for row in got["suggestions"]]
    assert "ruth" not in ids, "already on the reader's own shelf"
    assert ids[0] == "esther", "measured coverage ranks ahead of a guess"
    assert all(row["because"] for row in got["suggestions"])
    assert got["suggestions"][0]["because"].startswith("50%")


def test_check_job_answers_only_for_the_owner(world) -> None:
    library, store, person, home = world
    theirs = Job(id="j-theirs", source="x", owner=person.id + 1, stage="working")
    mine = Job(
        id="j-mine", source="x", owner=person.id, stage="done", reader="ruth-he/reader/index.html"
    )
    library.jobs.update({theirs.id: theirs, mine.id: mine})
    ctx = context(library, store, person, home)
    assert "error" in tools.check_job(ctx, {"id": "j-theirs"})
    got = tools.check_job(ctx, {"id": "j-mine"})
    assert got["stage"] == "done" and got["open"] == "/reader/ruth-he/reader/index.html"


def test_run_answers_a_broken_tool_as_an_error_the_model_can_read(world) -> None:
    library, store, person, home = world
    ctx = context(library, store, person, home)
    text, failed = tools.run("no_such_tool", {}, ctx)
    assert failed and "No tool" in text
    text, failed = tools.run("check_job", {"id": "nope"}, ctx)
    assert failed and json.loads(text)["error"]
    text, failed = tools.run("my_progress", {}, ctx)
    assert not failed and json.loads(text)["known"] == 2


# -- quoting -----------------------------------------------------------------------


def priced(job) -> None:  # type: ignore[no-untyped-def]
    """What `Library.prepare` leaves on a job it could price, without the pipeline."""
    job.title = "מאמר"
    job.language = "he"
    job.segments = 40
    job.total = 40
    job.estimate = 0.12
    job.stage = "ready"


def test_a_quote_never_claims_or_enqueues(world, monkeypatch) -> None:
    """The seam: `prepare` is the free half, and nothing here reaches the paid half.
    The card's button posts `/build`; the model has no tool that could."""
    library, store, person, home = world
    monkeypatch.setattr(library, "prepare", priced)

    def forbidden(*_: object) -> str:
        raise AssertionError("a quote must not spend")

    monkeypatch.setattr(library, "claim", forbidden)
    monkeypatch.setattr(library, "enqueue", forbidden)
    ctx = context(library, store, person, home)
    ctx.reads = {"en"}
    got = tools.quote_build(ctx, {"source": "https://example.com/article"})
    quote = got["quote"]
    assert quote["stage"] == "ready" and quote["segments"] == 40
    assert "$" not in got["note"] and "never in money" in got["note"]
    job = library.jobs[quote["id"]]
    assert job.owner == person.id and job.home == home and job.options["to"] == "en"
    assert job.kind == "build", "a quoted job is a build the strip will follow"
    assert store.committed(0) == 0.0, "nothing was claimed"
    assert not [tool for tool in tools.REGISTRY if tool.spends or tool.needs_consent]


def test_a_library_text_is_quoted_with_its_published_translation(world, monkeypatch) -> None:
    library, store, person, home = world
    monkeypatch.setattr(library, "prepare", priced)
    ctx = context(library, store, person, home)
    ctx.reads = {"en"}
    unbuilt = next(
        row
        for row in tools.search_library(ctx, {"limit": 20})["texts"]
        if not row["on_shelf"] and row["has_published_translation"]
    )
    got = tools.quote_build(ctx, {"catalogue_id": unbuilt["id"]})
    job = library.jobs[got["quote"]["id"]]
    assert job.options["translations"], "the published English rides on the job — nothing is bought"
    assert job.options["from"] == "he"
    already = tools.quote_build(ctx, {"catalogue_id": "ruth"})
    assert already["already_built"] is True and already["reader"].startswith("/reader/ruth-he/")
    assert "error" in tools.quote_build(ctx, {"catalogue_id": "nope"})


def test_a_quote_is_refused_on_the_add_page_s_grounds(world, monkeypatch) -> None:
    library, store, person, home = world
    monkeypatch.setattr(library, "prepare", priced)
    ctx = context(library, store, person, home)
    ctx.reads = {"en"}
    assert "profile" in tools.quote_build(ctx, {"source": "https://x.org/a", "to": "ru"})["error"]
    assert (
        "translates into"
        in tools.quote_build(ctx, {"source": "https://x.org/a", "to": "fr"})["error"]
    )
    assert "link" in tools.quote_build(ctx, {"source": "just some words"})["error"]
    assert "Say what" in tools.quote_build(ctx, {})["error"]
    assert library.jobs == {}, "a refused quote leaves no job behind"


def test_a_link_that_is_in_the_library_is_pointed_there(world, monkeypatch) -> None:
    library, store, person, home = world
    monkeypatch.setattr(library, "prepare", priced)
    ctx = context(library, store, person, home)
    ctx.reads = {"en"}
    got = tools.quote_build(ctx, {"source": "test:esther"})
    assert got["in_library"]["id"] == "esther" and "catalogue_id" in got["in_library"]["note"]
    assert library.jobs == {}


def test_a_quote_that_cannot_be_built_says_why(world, monkeypatch) -> None:
    library, store, person, home = world

    def blocked(job) -> None:  # type: ignore[no-untyped-def]
        job.stage = "blocked"
        job.blocked = "Too long. Try a chapter, or something from the library."

    monkeypatch.setattr(library, "prepare", blocked)
    ctx = context(library, store, person, home)
    ctx.reads = {"en"}
    got = tools.quote_build(ctx, {"source": "https://example.com/novel"})
    assert got["quote"]["blocked"].startswith("Too long") and "cannot be built" in got["note"]


def test_hours_are_hours(world) -> None:
    library, store, person, home = world
    store.save_job(
        {"id": "r1", "owner": person.id, "home": str(home), "source": "x", "made": now_ms()}
    )
    store.claim("r1", 0.5, 40.0, 0, owner=person.id, length=2 * 3600.0)
    ctx = context(library, store, person, home)
    got = tools.my_hours(ctx, {})
    assert got["used_hours"] == 2.0 and got["allowed_hours"] == 8.0 and got["left_hours"] == 6.0
    assert "$" not in json.dumps(got) and got["month_ends"]


def now_ms() -> int:
    from targum.accounts import now

    return now()


# -- finding things out there ----------------------------------------------------------


def test_a_video_is_described_from_metadata_and_never_refused_on_licence(
    world, monkeypatch
) -> None:
    from targum.video import youtube

    monkeypatch.setattr(
        youtube,
        "describe",
        lambda url: {
            "title": "שיעור על הלב",
            "duration": 1500,
            "webpage_url": url,
            "license": "Creative Commons Attribution license (reuse allowed)",
            "formats": [{"acodec": "mp4a", "language": "he", "language_preference": 10}],
            "subtitles": {"he": []},
        },
    )
    library, store, person, home = world
    ctx = context(library, store, person, home)
    got = tools.describe_source(ctx, {"url": "https://www.youtube.com/watch?v=abc123"})
    assert got["kind"] == "video" and got["title"] == "שיעור על הלב"
    assert got["hebrew_subtitles"] is True and got["audio_language"] == "he"
    assert got["hours"] == 0.42 and got["quote_with"] == "https://www.youtube.com/watch?v=abc123"
    assert got["licence_standing"] == "owed" and got["corpus_exportable"] is True
    assert "never here" in got["licence_note"]


def test_a_video_without_hebrew_subtitles_is_advised_not_refused(world, monkeypatch) -> None:
    from targum.video import youtube

    monkeypatch.setattr(
        youtube,
        "describe",
        lambda url: {
            "title": "x",
            "duration": 600,
            "formats": [{"acodec": "a", "language": "en"}],
            "subtitles": {},
        },
    )
    library, store, person, home = world
    got = tools.describe_source(
        context(library, store, person, home), {"url": "https://youtu.be/abc123"}
    )
    assert "error" not in got
    assert any("transcribed" in line for line in got["advice"])
    assert any("tagged en" in line for line in got["advice"])
    assert got["licence_standing"] == "unknown", "recorded as unknown, and still described"


def test_a_recording_and_an_article_are_described(world, monkeypatch) -> None:
    from targum.audio import episode
    from targum.ingest import url as url_module

    library, store, person, home = world
    ctx = context(library, store, person, home)
    monkeypatch.setattr(
        episode,
        "find",
        lambda url: episode.Episode(
            audio_url=url, title="פרק 3", seconds=1800, transcript_url="https://x/t.srt"
        ),
    )
    got = tools.describe_source(ctx, {"url": "https://podcast.example/ep3"})
    assert got["kind"] == "recording" and got["hours"] == 0.5 and got["has_transcript"] is True
    assert "nothing is transcribed" in got["advice"][0]

    monkeypatch.setattr(episode, "find", lambda url: None)
    page = (
        "<html><title> מאמר  על הים </title><body>"
        + "<p>"
        + " ".join(["שלום"] * 200)
        + "</p></body></html>"
    )
    monkeypatch.setattr(
        url_module, "fetch", lambda url: url_module.Fetched(text=page, content_type="text/html")
    )
    got = tools.describe_source(ctx, {"url": "https://news.example/a"})
    assert got["kind"] == "article" and got["title"] == "מאמר על הים"
    # The extractor keeps the page's title as a paragraph too, so a few over two hundred.
    assert 200 <= got["words"] <= 210 and got["minutes"] == 2 and got["hebrew_share"] == 1.0
    assert got["advice"] == []


def test_what_describe_refuses_is_the_door_not_the_licence(world, monkeypatch) -> None:
    from targum.audio import episode
    from targum.errors import UnsupportedSource

    library, store, person, home = world
    ctx = context(library, store, person, home)
    assert "link" in tools.describe_source(ctx, {"url": "just words"})["error"]
    assert "Give a link" in tools.describe_source(ctx, {})["error"]
    assert tools.describe_source(ctx, {"url": "gutenberg:1234"})["kind"] == "fetcher"

    def spotify(url: str) -> None:
        raise UnsupportedSource("Spotify does not hand out its audio.", "Find the show's own feed.")

    monkeypatch.setattr(episode, "find", spotify)
    got = tools.describe_source(ctx, {"url": "https://open.spotify.com/episode/x"})
    assert got["error"].startswith("Spotify") and "feed" in got["error"]


def test_a_private_address_is_refused_by_the_fetch_door(world) -> None:
    """The SSRF guard is the one control a model choosing addresses makes primary."""
    library, store, person, home = world
    got = tools.describe_source(
        context(library, store, person, home), {"url": "http://127.0.0.1:8420/health"}
    )
    assert "private network" in got["error"], "the fetch door's own refusal, in its words"


def test_search_sources_reads_the_registered_feeds(world, monkeypatch, tmp_path) -> None:
    from datetime import UTC, datetime

    from targum.weekly import feeds

    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps(
            {
                "publishers": [
                    {
                        "key": "kan",
                        "name": "כאן",
                        "publisher": "Kan",
                        "feed": "https://kan.example/rss",
                        "kind": "news",
                    },
                    {
                        "key": "pod",
                        "name": "Pod",
                        "feed": "https://pod.example/rss",
                        "kind": "podcast",
                    },
                    {
                        "key": "dead",
                        "name": "Dead",
                        "feed": "https://dead.example/rss",
                        "kind": "news",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TARGUM_SOURCES", str(path))

    def pull(url: str, *, limit: int = 30) -> list[feeds.Item]:
        from targum.errors import TargumError

        if "dead" in url:
            raise TargumError("Could not fetch")
        if "pod" in url:
            return [
                feeds.Item(
                    title="על הים",
                    link="https://pod.example/3",
                    published=datetime(2026, 9, 1, tzinfo=UTC),
                    enclosure="https://pod.example/3.mp3",
                    seconds=1800,
                    transcript="https://pod.example/3.srt",
                )
            ]
        return [
            feeds.Item(
                title="חדשות הים",
                link="https://kan.example/1",
                published=datetime(2026, 9, 4, tzinfo=UTC),
            ),
            feeds.Item(
                title="ספורט",
                link="https://kan.example/2",
                published=datetime(2026, 9, 5, tzinfo=UTC),
            ),
        ]

    monkeypatch.setattr(feeds, "pull", pull)
    library, store, person, home = world
    ctx = context(library, store, person, home)
    got = tools.search_sources(ctx, {"query": "הים"})
    assert [row["link"] for row in got["items"]] == [
        "https://kan.example/1",
        "https://pod.example/3",
    ], "newest first"
    assert got["items"][1]["has_transcript"] is True and got["items"][1]["seconds"] == 1800
    assert got["unreachable"] == ["dead"]
    assert tools.search_sources(ctx, {"kind": "podcast"})["count"] == 1

    monkeypatch.setenv("TARGUM_SOURCES", str(tmp_path / "none.json"))
    assert "No publishers" in tools.search_sources(ctx, {})["note"]


def test_the_search_stands_in_israel_so_a_hebrew_question_gets_hebrew_writing() -> None:
    """Unlocalised, a search run from a server in Germany answers a Hebrew question with
    the English-language coverage of Israel rather than with Israeli writing."""
    searching = [
        one for one in tools.anthropic_tools(web_search=True) if one.get("name") == "web_search"
    ]
    assert len(searching) == 1
    where = searching[0]["user_location"]
    assert where["country"] == "IL" and where["type"] == "approximate"
    assert where["timezone"] == "Asia/Jerusalem"


def test_the_search_names_domains_or_blocks_them_but_never_both() -> None:
    """The API returns a 400 when a request carries both lists."""
    for tool in tools.anthropic_tools(web_search=True):
        if tool.get("name") == "web_search":
            assert not ("allowed_domains" in tool and "blocked_domains" in tool)
