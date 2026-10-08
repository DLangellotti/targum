"""Try the door on the front page (targum-internal#399).

A stranger pastes a link under the headline and is told what it is, in the Add box's
own sentence, with the waitlist beside it carrying the link. What is tested here is the
part that makes that safe to put in front of anybody: nothing is built, nothing is
spent, it is counted per visitor, it works with JavaScript off, and the link is kept
only with a place on the list.
"""

from __future__ import annotations

import html
import io
import re
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pytest

from targum.accounts import Store
from targum.mail import ConsoleMailer
from targum.render.builder import front_page
from targum.serve import Handler, Job, Library, kept_link, tried_for

VIDEO = "https://www.youtube.com/watch?v=abcdefghijk"


@pytest.fixture
def door(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[int, Store, Library, io.StringIO]]:
    """The front door, open, with yt-dlp answering from a fixture rather than the
    network: the suite is offline, and the door's answer is what is under test."""
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")
    out = tmp_path / "targum-out"
    out.mkdir()
    store = Store(tmp_path / "words.db")
    posted = io.StringIO()
    library = Library(out)
    library.store = store
    library.mailer = ConsoleMailer(posted)
    library.hosted = True
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    server.RequestHandlerClass = type(
        "TestHandler",
        (Handler,),
        {
            "library": library,
            "token": "test-key",
            "require_account": True,
            "welcome": "<html>start</html>",
            "store": store,
            "mailer": library.mailer,
            "address": f"http://127.0.0.1:{port}",
        },
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port, store, library, posted
    finally:
        server.shutdown()
        server.server_close()


def youtube_answers(monkeypatch: pytest.MonkeyPatch, **info: Any) -> list[str]:
    """yt-dlp, answering `-J` for one video. Returns the addresses it was asked about."""
    asked: list[str] = []

    def describe(url: str) -> dict[str, Any]:
        asked.append(url)
        return {
            "webpage_url": url,
            "title": "סביח, צעד אחר צעד",
            "duration": 540,
            "subtitles": {"he": [{}]},
            **info,
        }

    monkeypatch.setattr("targum.video.ytdlp_available", lambda: (True, "yt-dlp"))
    monkeypatch.setattr("targum.video.youtube.describe", describe)
    return asked


def post(
    port: int, path: str, form: dict[str, str], headers: dict[str, str] | None = None
) -> tuple[int, str]:
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request(
            "POST",
            path,
            urlencode(form),
            {"Content-Type": "application/x-www-form-urlencoded", **(headers or {})},
        )
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8", "replace")
    finally:
        connection.close()


def said(page: str) -> str:
    found = re.search(r'<p class="tried-what">(.*?)</p>', page, re.S)
    assert found, "no answer on the page"
    return html.unescape(" ".join(found.group(1).split()))


def test_the_box_is_a_plain_form_under_the_headline() -> None:
    """It works with JavaScript off, and it shows no percentage: "you know X%" needs a
    record, and getting one is the reason to join (2026-09-30)."""
    page = front_page(address="https://targum.page")
    form = re.search(r'<form class="try-form" method="post" action="([^"]+)">', page)
    assert form and form.group(1) == "/try#try"
    assert page.index('class="try-form"') < page.index('class="showcase"')
    assert '<div class="tried"' not in page, "nothing is said before anything is tried"
    russian = front_page(language="ru", address="https://targum.page", asked="ru")
    assert 'action="/try?lang=ru#try"' in russian


def test_a_video_is_said_in_one_sentence_and_nothing_is_spent(
    door: tuple[int, Store, Library, io.StringIO], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, store, library, _ = door
    asked = youtube_answers(monkeypatch)

    def no_spending(*_: object, **__: object) -> str:
        raise AssertionError("a stranger's try claimed against the rails")

    monkeypatch.setattr(Library, "claim", no_spending)

    status, page = post(port, "/try", {"link": VIDEO})
    assert status == 200
    assert asked == [VIDEO]
    sentence = said(page)
    assert sentence.startswith(
        "That’s a YouTube video, 9 minutes, Hebrew subtitles written by a person."
    ), sentence
    assert "Ready in" in sentence
    assert "%" not in sentence
    assert "סביח, צעד אחר צעד" in page
    # The waitlist sits right there and carries the link.
    assert f'<input type="hidden" name="link" value="{VIDEO}">' in page
    # No job anybody can see, and no build.
    assert not library.jobs
    assert store.db.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 0


def test_a_refusal_is_the_add_pages_own_and_offers_no_join(
    door: tuple[int, Store, Library, io.StringIO], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, *_ = door
    youtube_answers(monkeypatch, duration=0)
    status, page = post(port, "/try", {"link": VIDEO})
    assert status == 200
    assert "a live stream" in said(page)
    assert 'name="link" value=' not in page.split('<div class="tried"')[1]

    status, page = post(port, "/try", {"link": "not a link at all"})
    assert said(page) == "That isn't a link. Paste one that starts with https."


def test_a_host_we_cannot_fetch_is_named(
    door: tuple[int, Store, Library, io.StringIO],
) -> None:
    port, *_ = door
    _, page = post(port, "/try", {"link": "https://vimeo.com/123456"})
    assert said(page) == "Vimeo doesn't let us fetch its videos."


def test_a_visitor_is_counted_and_told_when_to_come_back(
    door: tuple[int, Store, Library, io.StringIO], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each try is a yt-dlp call through the proxy, which bills by the gigabyte. Counted
    per visitor, under a digest of their address, never the address itself."""
    from targum.serve import TRIES_PER_HOUR

    port, store, _, _ = door
    asked = youtube_answers(monkeypatch)
    one = {"X-Forwarded-For": "203.0.113.7"}
    for _ in range(TRIES_PER_HOUR):
        post(port, "/try", {"link": VIDEO}, one)
    _, page = post(port, "/try", {"link": VIDEO}, one)
    assert "That's a lot of links for one hour" in said(page)
    assert len(asked) == TRIES_PER_HOUR, "the refused try asked nobody"

    _, page = post(port, "/try", {"link": VIDEO}, {"X-Forwarded-For": "203.0.113.8"})
    assert said(page).startswith("That’s a YouTube video"), "somebody else is not held to it"

    kept = [str(row[0]) for row in store.db.execute("SELECT who FROM asked")]
    assert kept and not any("203.0.113" in who for who in kept)


def test_joining_keeps_the_link_and_leaving_takes_it(
    door: tuple[int, Store, Library, io.StringIO], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, store, _, _ = door
    youtube_answers(monkeypatch)
    _, page = post(port, "/try", {"link": VIDEO})
    hidden = dict(re.findall(r'<input type="hidden" name="(from|link)" value="([^"]*)">', page))
    assert hidden["link"] == VIDEO

    post(port, "/waitlist", {"email": "tal@example.com", **hidden})
    row = store.db.execute(
        "SELECT link, page FROM waiting WHERE email = ?", ("tal@example.com",)
    ).fetchone()
    assert row["link"] == VIDEO and row["page"] == "/"

    # Asking again without a link keeps the one they came with.
    post(port, "/waitlist", {"email": "tal@example.com"})
    assert (
        store.db.execute(
            "SELECT link FROM waiting WHERE email = ?", ("tal@example.com",)
        ).fetchone()["link"]
        == VIDEO
    )

    stop = store.db.execute(
        "SELECT stop FROM waiting WHERE email = ?", ("tal@example.com",)
    ).fetchone()["stop"]
    post(port, "/waitlist/stop", {"t": stop})
    assert (
        store.db.execute(
            "SELECT link FROM waiting WHERE email = ?", ("tal@example.com",)
        ).fetchone()["link"]
        == ""
    )


@pytest.mark.parametrize(
    ("link", "kept"),
    [
        (VIDEO, VIDEO),
        ("  https://www.ynet.co.il/news/article/abc  ", "https://www.ynet.co.il/news/article/abc"),
        ("javascript:alert(1)", ""),
        ("file:///etc/passwd", ""),
        ("https://", ""),
        ("https://example.com/" + "a" * 3000, ""),
    ],
)
def test_only_a_web_address_is_kept(link: str, kept: str) -> None:
    """The link comes back from a hidden field, so it is whatever the request says."""
    assert kept_link(link) == kept


def test_the_back_office_shows_the_link(tmp_path: Path) -> None:
    from targum.backoffice import survey
    from targum.render.builder import back_office_page

    store = Store(tmp_path / "targum.db")
    store.join_waitlist("tal@example.com", "en", "/", VIDEO)
    found = survey(store.db)
    assert [who.link for who in found.waiting_list] == [VIDEO]
    assert f'href="{VIDEO}"' in back_office_page(found, 30)


# -- let in, and the saved link is built (David, 2026-10-01) ---------------------------


def waiting_with_a_link(store: Store, email: str = "tal@example.com") -> None:
    """Somebody who tried a link, joined with it, confirmed, and is next in line."""
    token = store.join_waitlist(email, "en", "/", VIDEO)
    assert token is not None
    store.confirm_waiting(token)


def quoted(
    monkeypatch: pytest.MonkeyPatch, *, estimate: float = 0.2, stage: str = "ready"
) -> list[str]:
    """`prepare` answering as it would for a nine-minute video, without yt-dlp, and the
    queue recording what it was given instead of building it."""
    queued: list[str] = []

    def prepare(self: Library, job: Any) -> None:
        job.title = "סביח"
        job.audio = True
        job.seconds = 540.0
        job.parts = 1
        job.estimate = estimate
        job.stage = stage
        if stage == "failed":
            job.error = "That video has no length yet."

    monkeypatch.setattr(Library, "prepare", prepare)
    monkeypatch.setattr(Library, "enqueue", lambda self, job: queued.append(job.id))
    return queued


def test_letting_somebody_in_builds_their_saved_link_on_targum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """targum pays, through the same `claim` every build takes: a job row, owned by the
    new account, held to the box ceiling, and no hours taken from their eight."""
    from targum.doorway import let_in

    store = Store(tmp_path / "targum.db")
    library = Library(tmp_path / "out", budget=5.0)
    library.store = store
    queued = quoted(monkeypatch)
    waiting_with_a_link(store)
    sent: list[str] = []

    class Mailer:
        def notify(self, to: str, *_: object) -> None:
            sent.append(to)

    row = let_in(
        store, Mailer(), "https://targum.page", "tal@example.com", library.build_saved_link
    )
    assert row is not None and row.ok and sent == ["tal@example.com"]

    person = store.person_by_email("tal@example.com")
    assert person is not None, "the account exists before they sign in, to own the build"
    [job] = list(library.jobs.values())
    assert job.gift and job.owner == person.id and job.source == VIDEO
    assert queued == [job.id], "claimed, then queued: the same press any build takes"
    claimed = store.db.execute(
        "SELECT owner, claimed, length FROM job WHERE id = ?", (job.id,)
    ).fetchone()
    assert claimed["owner"] == person.id
    assert claimed["claimed"] == pytest.approx(0.2)
    assert claimed["length"] == 0, "targum pays: none of their hours"


def test_the_box_ceiling_still_holds_and_the_link_stays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(tmp_path / "targum.db")
    library = Library(tmp_path / "out", budget=0.05)
    library.store = store
    queued = quoted(monkeypatch, estimate=0.2)
    waiting_with_a_link(store)
    store.invite("tal@example.com")

    job = library.build_saved_link("tal@example.com")
    assert job is not None and job.stage == "blocked" and queued == []
    assert store.waiting_link("tal@example.com") == VIDEO


def test_a_link_that_will_not_open_is_left_saved_and_the_invitation_still_goes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum.doorway import open_the_door

    store = Store(tmp_path / "targum.db")
    library = Library(tmp_path / "out", budget=5.0)
    library.store = store
    queued = quoted(monkeypatch, stage="failed")
    waiting_with_a_link(store)
    sent: list[str] = []

    class Mailer:
        def notify(self, to: str, *_: object) -> None:
            sent.append(to)

    rows = open_the_door(store, Mailer(), "https://targum.page", 5, then=library.build_saved_link)
    assert [row.ok for row in rows] == [True] and sent == ["tal@example.com"]
    assert queued == []
    assert store.waiting_link("tal@example.com") == VIDEO


def test_whatever_the_build_raises_never_undoes_the_invitation(tmp_path: Path) -> None:
    from targum.doorway import open_the_door

    store = Store(tmp_path / "targum.db")
    waiting_with_a_link(store)

    class Mailer:
        def notify(self, *_: object) -> None:
            pass

    def broken(email: str, language: str) -> None:
        raise RuntimeError("yt-dlp fell over")

    rows = open_the_door(store, Mailer(), "https://targum.page", 5, then=broken)
    assert [row.ok for row in rows] == [True]
    assert store.waiting_for_a_way_in() == [], "stamped as let in"


def test_nobody_without_a_saved_link_gets_a_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(tmp_path / "targum.db")
    library = Library(tmp_path / "out", budget=5.0)
    library.store = store
    quoted(monkeypatch)
    token = store.join_waitlist("noa@example.com", "en", "/")
    assert token is not None
    store.confirm_waiting(token)
    store.invite("noa@example.com")
    assert library.build_saved_link("noa@example.com") is None
    assert not library.jobs


def test_a_request_cannot_make_its_own_build_a_gift(
    door: tuple[int, Store, Library, io.StringIO],
) -> None:
    """`gift` is a field on the job, never read from `options`, which is the request's."""
    import dataclasses

    from targum.serve import Job

    assert "gift" in {one.name for one in dataclasses.fields(Job)}
    source = (Path(__file__).parents[1] / "src" / "targum" / "serve.py").read_text("utf-8")
    assert 'options.get("gift")' not in source and "options['gift']" not in source


def test_a_page_tried_leaves_nothing_on_the_shelf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A web page is fetched and cut into sentences to say how long it is, and both
    steps write what they read. Written beside the shelf, every stranger's try was a
    folder on the box nobody built; now it is a scratch folder that goes with the answer."""
    from targum.models import Block, Document

    out = tmp_path / "targum-out"
    out.mkdir()
    page = Document(
        source="https://news.example/item",
        title="ידיעה",
        language="he",
        blocks=[Block(id="b0000", text="הממשלה התכנסה היום. השרים דנו בתקציב.")],
        content_hash="",
    )
    monkeypatch.setattr("targum.audio.episode.sounds_like_audio", lambda url: False)
    monkeypatch.setattr("targum.audio.episode.find", lambda url: None)
    monkeypatch.setattr("targum.ingest.load", lambda source, language=None: page)
    job = Library(out).describe("https://news.example/item")
    assert job.stage == "ready", job.error
    assert job.segments > 0
    assert list(out.rglob("*")) == [], "a try wrote to the shelf"


def test_a_refusal_never_shows_a_stranger_how_the_inside_works() -> None:
    """A fetcher's own words name the address it asked and the status it got; the box
    says the plain sentence instead, and keeps the ones written for a person (2026-10-02)."""
    inside = Job(id="try-1", source="https://x.com/a/status/1")
    inside.stage = "failed"
    inside.error = "We couldn't open https://cdn.syndication.twimg.com/tweet-result. HTTP 404"
    assert tried_for(inside, "en") == {"refused": "We couldn't open that link."}
    person = Job(id="try-2", source="hello")
    person.stage = "failed"
    person.error = "That isn't a link. Paste one that starts with https."
    assert tried_for(person, "en") == {"refused": person.error}
