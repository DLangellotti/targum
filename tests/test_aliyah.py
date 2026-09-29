"""The olim's own door, `/aliyah` (targum-internal#385).

A second page in front of the door, beside the front door and not in place of it. What
is tested here is what `test_landing.py` holds the front door to, because a stranger
meets this page the same way: it fetches nothing, it says what it is to a crawler in
both languages, its form works with no JavaScript, and it is not there while the switch
that opens the front door is off.

And the two things that make it this page and not that one: it says who it is for, and
it leaves the Torah to the front door.
"""

from __future__ import annotations

import io
import re
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from targum.accounts import Store
from targum.mail import ConsoleMailer
from targum.render.builder import aliyah_page, front_page
from targum.serve import Handler, Library

ADDRESS = "https://targum.page"


@pytest.fixture
def served(tmp_path: Path) -> Iterator[int]:
    """A running server, hosted, with a stranger at the door."""
    out = tmp_path / "targum-out"
    out.mkdir()
    store = Store(tmp_path / "words.db")
    library = Library(out)
    library.store = store
    library.mailer = ConsoleMailer(io.StringIO())
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
        yield port
    finally:
        server.shutdown()
        server.server_close()


def get(port: int, path: str) -> tuple[int, str]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8", "replace")
    finally:
        connection.close()


# -- the page itself ------------------------------------------------------------------


def test_the_page_fetches_nothing() -> None:
    """§11, as on the front door: the only outbound addresses are links a reader chooses
    to press, its own canonical, and the same page in the other language."""
    html = aliyah_page("en", ADDRESS)
    outbound = set(re.findall(r'(?:src|href)="(https?://[^"]+)', html))
    assert outbound == {
        "https://github.com/DLangellotti/targum",
        "https://x.com/targum_app",
        "https://www.instagram.com/targum.page/",
        "https://www.linkedin.com/company/targum-page/",
        f"{ADDRESS}/aliyah",
        f"{ADDRESS}/aliyah?lang=ru",
    }
    assert not re.search(r"url\(\s*['\"]?https?:", html), "a stylesheet fetches something"


def test_the_page_carries_no_script() -> None:
    """Nothing on it moves, so there is nothing for a script to do, and the front door's
    own script would look for demos this page does not draw."""
    assert "<script" not in aliyah_page("en", ADDRESS)


def test_the_page_says_what_it_is_to_a_crawler() -> None:
    html = aliyah_page("en", ADDRESS)
    assert "<title>targum — Hebrew for life in Israel</title>" in html
    assert f'<link rel="canonical" href="{ADDRESS}/aliyah">' in html
    assert 'hreflang="ru"' in html, "a crawler is told the two addresses are one page"
    russian = aliyah_page("ru", ADDRESS)
    assert "<title>targum — иврит для жизни в Израиле</title>" in russian
    assert f'<link rel="canonical" href="{ADDRESS}/aliyah?lang=ru">' in russian


def test_the_waitlist_form_needs_no_javascript() -> None:
    """Two forms, one under the headline and one where the page ends, each a plain post."""
    html = aliyah_page("en", ADDRESS)
    forms = re.findall(r'<form[^>]*action="/waitlist"[^>]*>', html)
    assert len(forms) == 2
    for form in forms:
        assert 'method="post"' in form
    assert html.count('name="email"') == 2


def test_the_page_loads_one_stylesheet_and_it_is_the_front_doors() -> None:
    template = (
        Path(__file__).resolve().parents[1] / "src/targum/render/templates/aliyah.html.j2"
    ).read_text(encoding="utf-8")
    assert "asset('landing.css')" in template
    assert "asset('reader.css')" not in template, "both sheets collide on .lines and .thread"


# -- who it is for --------------------------------------------------------------------


def test_the_page_says_who_it_is_for_in_its_first_line() -> None:
    html = aliyah_page("en", ADDRESS)
    headline = re.search(r"<h1>(.*?)</h1>", html, re.S)
    assert headline is not None
    assert headline.group(1) == "Learn Hebrew from your own life in Israel."
    assert "ulpan" in html


def test_the_torah_is_left_to_the_front_door() -> None:
    """The GTM note had said it of the front door's own line: "one list, from Genesis to
    the news" reads as a bible tool to an oleh. The front door keeps it; this page is
    the one that does not say it."""
    html = aliyah_page("en", ADDRESS)
    body = html[html.index("<main") : html.index("</main>")]
    for word in ("Torah", "Genesis", "biblical", "Onkelos", "chanting"):
        assert word not in body, word
    assert "Genesis" in front_page("en", ADDRESS), "the front door says what it said"


def test_the_hebrew_it_shows_is_pointed() -> None:
    """The page promises vowels on every line, so the lines it shows carry them."""
    html = aliyah_page("en", ADDRESS)
    lines = re.findall(r'<p class="he">(.*?)</p>', html)
    assert len(lines) == 4
    for line in lines:
        for word in line.rstrip(".").split():
            assert re.search(r"[ְ-ּׁׂ]", word), f"{word} has no vowels"


def test_somebody_with_an_account_is_not_asked_to_join() -> None:
    """§6: somebody who has already chosen targum is not sold to again."""
    html = aliyah_page("en", ADDRESS, signed_in=True)
    assert 'action="/waitlist"' not in html
    assert 'id="join"' not in html


# -- the two languages ----------------------------------------------------------------


def test_the_page_is_wholly_russian_when_asked_for_in_russian() -> None:
    from targum import strings

    english = strings.catalogue("en")
    russian = strings.catalogue("ru")
    said = {key for key in english if key.startswith("aliyah.")}
    assert said, "the page says nothing through the catalogue"
    missing = sorted(key for key in said if key not in russian)
    assert not missing, f"the olim's door is half-translated: {missing[:5]}"
    html = aliyah_page("ru", ADDRESS)
    assert '<html lang="ru"' in html
    assert "Учите иврит по своей жизни в Израиле." in html


def test_a_russian_reader_is_not_told_they_get_by_in_english() -> None:
    """The one sentence that is adapted and not translated: an oleh reading the Russian
    page gets by in Russian, and is promised Russian under every line."""
    html = aliyah_page("ru", ADDRESS)
    assert "Вы обходитесь русским" in html
    assert "русский под каждой строкой" in html


def test_the_switcher_stays_on_this_page() -> None:
    for code, offered in (("en", "ru"), ("ru", "en")):
        html = aliyah_page(code, ADDRESS)
        markup = re.sub(r"<style>.*?</style>", "", html, flags=re.S)
        tongue = re.search(r'<p class="tongue">.*?</p>', markup, re.S)
        assert tongue is not None
        assert f'href="/aliyah?lang={offered}"' in tongue.group(0)


# -- the switch -----------------------------------------------------------------------


def test_the_page_is_not_there_while_the_front_door_is_shut(
    served: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Its one ask is the waitlist, and the waitlist takes no address while the door is
    shut: a page asking for one would be asking for something nobody will take."""
    monkeypatch.delenv("TARGUM_FRONT_DOOR", raising=False)
    status, body = get(served, "/aliyah")
    assert status == 404
    assert "Join the waitlist" not in body


def test_the_page_answers_a_stranger_once_the_front_door_is_open(
    served: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")
    status, body = get(served, "/aliyah")
    assert status == 200
    assert "Learn Hebrew from your own life in Israel." in body
    assert "Coming soon" not in body
    status, body = get(served, "/aliyah?lang=ru")
    assert status == 200
    assert '<html lang="ru"' in body


def test_the_front_door_is_what_it_was(served: int, monkeypatch: pytest.MonkeyPatch) -> None:
    """David, 2026-09-29: the front door does not change. It still opens on its own
    headline, and it does not point at this page."""
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")
    status, body = get(served, "/")
    assert status == 200
    assert "Learn modern and biblical Hebrew from videos, podcasts and books." in body
    assert "/aliyah" not in body
