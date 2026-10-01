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
from targum.serve import Handler, Library, kept_link

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
            "page": "<html>start</html>",
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
    assert "That video has no length yet" in said(page)
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
