"""The front door (targum-internal#69).

The one page a stranger meets. What is tested here is what makes it safe to leave at
`/`: it fetches nothing, it says what it is to a crawler, its form works with no
JavaScript, and none of it is reachable while the switch that opens it is off.
"""

from __future__ import annotations

import io
import re
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

import pytest

from targum.accounts import Store
from targum.mail import ConsoleMailer
from targum.render.builder import front_page
from targum.serve import Handler, Library

ADDRESS = "https://targum.page"


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[int, Store, io.StringIO]]:
    """A running server with a front door and a mailbox to read."""
    out = tmp_path / "targum-out"
    out.mkdir()
    store = Store(tmp_path / "words.db")
    posted = io.StringIO()
    library = Library(out)
    library.store = store
    library.mailer = ConsoleMailer(posted)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    server.RequestHandlerClass = type(
        "TestHandler",
        (Handler,),
        {
            "library": library,
            "token": "test-key",
            # Hosted: a stranger at the door is the whole subject here.
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
        yield port, store, posted
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


def post(port: int, path: str, form: dict[str, str]) -> tuple[int, str]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(
            "POST",
            path,
            urlencode(form),
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8", "replace")
    finally:
        connection.close()


# -- the page itself ------------------------------------------------------------------


def test_the_page_fetches_nothing() -> None:
    """§11, and the reason it holds here: the first page anybody sees should not be a
    page that phones somebody else first. The faces, the stylesheet and the script are
    baked in, and the only outbound addresses are links a reader chooses to press."""
    html = front_page("en", ADDRESS)
    outbound = set(re.findall(r'(?:src|href)="(https?://[^"]+)', html))
    assert outbound == {
        "https://github.com/DLangellotti/targum",  # the foot, a link to press
        f"{ADDRESS}/",  # its own canonical
        f"{ADDRESS}/?lang=ru",  # and the same page in the other language
    }
    assert not re.search(r"url\(\s*['\"]?https?:", html), "a stylesheet fetches something"


def test_the_page_says_what_it_is_to_a_crawler() -> None:
    html = front_page("en", ADDRESS)
    assert "<title>targum — learn modern and biblical Hebrew</title>" in html
    # And says it in the page's own language: the tab and the search result are the two
    # sentences a stranger reads before the page itself.
    assert "<title>targum — учите современный и библейский иврит</title>" in front_page(
        "ru", ADDRESS
    )
    assert f'<link rel="canonical" href="{ADDRESS}/">' in html
    assert 'property="og:title"' in html


def test_the_waitlist_form_needs_no_javascript() -> None:
    """Three forms, one on each ask, and every one of them a plain post."""
    html = front_page("en", ADDRESS)
    forms = re.findall(r'<form[^>]*action="/waitlist"[^>]*>', html)
    assert len(forms) == 3
    for form in forms:
        assert 'method="post"' in form
    assert html.count('name="email"') == 3


def test_the_page_speaks_through_the_catalogue() -> None:
    """A visitor whose browser asks for Russian gets the Russian the catalogue has, and
    English for the rest; nothing on the page is hard-coded past `t`."""
    english = front_page("en", ADDRESS)
    assert "Learn modern and biblical Hebrew" in english
    russian = front_page("ru", ADDRESS)
    assert 'lang="ru"' in russian


# -- the switch -----------------------------------------------------------------------


def test_the_holding_page_stands_until_the_switch_is_thrown(
    served: tuple[int, Store, io.StringIO], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, _, _ = served
    monkeypatch.delenv("TARGUM_FRONT_DOOR", raising=False)
    status, body = get(port, "/")
    assert status == 200
    assert "Coming soon" in body
    assert "Join the waitlist" not in body


def test_the_front_door_answers_once_the_switch_is_thrown(
    served: tuple[int, Store, io.StringIO], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, _, _ = served
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")
    status, body = get(port, "/")
    assert status == 200
    assert "Join the waitlist" in body
    assert "Coming soon" not in body


def test_only_the_root_becomes_the_front_door(
    served: tuple[int, Store, io.StringIO], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every other page a signed-out visitor asks for is still the holding page: the
    front door is a page about the product, not a stand-in for one of its rooms."""
    port, _, _ = served
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")
    status, body = get(port, "/library")
    assert status == 200
    assert "Coming soon" in body


def test_the_waitlist_is_shut_while_the_door_is(
    served: tuple[int, Store, io.StringIO], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A form that takes an address is not something to leave reachable beside a page
    that says "Coming soon"."""
    port, store, _ = served
    monkeypatch.delenv("TARGUM_FRONT_DOOR", raising=False)
    status, _ = post(port, "/waitlist", {"email": "dina@example.com"})
    # Refused by the start-up key, which is what every other closed door
    # answers with: the route simply is not there while the switch is off.
    assert status == 403
    assert store.waiting_count() == {"pending": 0, "on": 0, "off": 0}


# -- joining --------------------------------------------------------------------------


def test_joining_takes_the_address_and_mails_a_link(
    served: tuple[int, Store, io.StringIO], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, store, posted = served
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")
    status, body = post(port, "/waitlist", {"email": "dina@example.com"})
    assert status == 200
    assert "Check your email" in body
    assert store.waiting_state("dina@example.com") == "pending"
    sent = posted.getvalue()
    assert "dina@example.com" in sent
    assert "/waitlist/confirm?t=" in sent


def test_a_typo_is_refused_before_anything_is_stored(
    served: tuple[int, Store, io.StringIO], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, store, _ = served
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")
    status, body = post(port, "/waitlist", {"email": "dina at example"})
    assert status == 429
    assert "read that as an email" in body
    assert store.waiting_count()["pending"] == 0


def test_the_door_says_the_same_thing_however_it_goes(
    served: tuple[int, Store, io.StringIO], monkeypatch: pytest.MonkeyPatch
) -> None:
    """An address already on the list, and one never seen, get one sentence between
    them: an endpoint that answered differently would be a way to ask who is waiting."""
    port, store, _ = served
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")
    token = store.join_waitlist("already@example.com")
    assert token and store.confirm_waiting(token)
    _, said_again = post(port, "/waitlist", {"email": "already@example.com"})
    _, said_new = post(port, "/waitlist", {"email": "new@example.com"})
    assert said_again == said_new


def test_confirming_is_a_button_and_never_a_bare_link(
    served: tuple[int, Store, io.StringIO], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mail client that fetches every link in a message must not answer for the
    person it was sent to."""
    port, store, _ = served
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")
    token = store.join_waitlist("dina@example.com")
    assert token
    status, body = get(port, f"/waitlist/confirm?t={token}")
    assert status == 200
    assert "dina@example.com" in body
    assert store.waiting_state("dina@example.com") == "pending", "the GET spent the token"
    status, body = post(port, "/waitlist/confirm", {"t": token})
    assert status == 200
    assert store.waiting_state("dina@example.com") == "on"


def test_leaving_says_nothing_about_whether_the_token_was_one(
    served: tuple[int, Store, io.StringIO], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, store, _ = served
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")
    token = store.join_waitlist("dina@example.com")
    assert token and store.confirm_waiting(token)
    stop = store.db.execute(
        "SELECT stop FROM waiting WHERE email = ?", ("dina@example.com",)
    ).fetchone()["stop"]
    _, real = post(port, "/waitlist/stop", {"t": stop})
    _, made_up = post(port, "/waitlist/stop", {"t": "not-a-token"})
    assert real == made_up
    assert store.waiting_state("dina@example.com") == "off"


# -- the tokens it carries ------------------------------------------------------------


def test_the_desk_it_carries_is_the_desk_the_rest_of_the_product_stands_on() -> None:
    """The page copies `reader.css`'s token blocks rather than loading that file,
    because the reader's sheet styles `.lines`, `.thread`, `.card` and `.stage` for the
    reader and this page draws things by those names too — loading both put the
    conversation on top of the hero. A copy drifts unless something holds it, and this
    is the something."""
    assets = Path(__file__).resolve().parents[1] / "src/targum/render/assets"
    reader = assets.joinpath("reader.css").read_text(encoding="utf-8").splitlines()
    landing = assets.joinpath("landing.css").read_text(encoding="utf-8")
    # The light block alone: the front door has no dark half (David, 2026-09-16).
    tokens = "\n".join(reader[:113])
    assert tokens in landing, "landing.css no longer carries reader.css's tokens verbatim"


def test_the_front_door_is_light_whatever_the_browser_prefers() -> None:
    """One page, one look. A stranger meeting it for three seconds should not meet a
    second design because their phone is in night mode; the product behind the door
    keeps both themes."""
    assets = Path(__file__).resolve().parents[1] / "src/targum/render/assets"
    landing = assets.joinpath("landing.css").read_text(encoding="utf-8")
    assert "color-scheme: light" in landing
    assert "prefers-color-scheme: dark" not in landing
    assert 'data-theme="dark"' not in landing
    html = front_page("en", ADDRESS)
    assert "theme.js" not in html, "no switch, because there is nothing to switch to"


def test_the_page_loads_one_stylesheet_and_it_is_its_own() -> None:
    template = (
        Path(__file__).resolve().parents[1] / "src/targum/render/templates/landing.html.j2"
    ).read_text(encoding="utf-8")
    assert "asset('landing.css')" in template
    assert "asset('reader.css')" not in template, "both sheets collide on .lines and .thread"


# -- the two languages ----------------------------------------------------------------


def test_the_page_is_wholly_russian_when_asked_for_in_russian() -> None:
    """Not half of it. A catalogue that has the headline and not the FAQ gives a
    visitor a page that changes language halfway down, which is worse than English."""
    from targum import strings

    english = strings.catalogue("en")
    russian = strings.catalogue("ru")
    said = {key for key in english if key.startswith("landing.")}
    assert said, "the page says nothing through the catalogue"
    missing = sorted(key for key in said if key not in russian)
    assert not missing, f"the front door is half-translated: {missing[:5]}"


def test_the_switcher_offers_the_language_you_are_not_reading() -> None:
    """One link, named in itself. A page in two languages has to offer the other one,
    and a control that lists the language you are already reading says nothing."""
    for code, offered, reading in (("en", "ru", "EN"), ("ru", "en", "RU")):
        html = front_page(code, ADDRESS)
        markup = re.sub(r"<style>.*?</style>", "", html, flags=re.S)
        tongue = re.search(r'<p class="tongue">.*?</p>', markup, re.S)
        assert tongue is not None
        assert f'href="/?lang={offered}"' in tongue.group(0)
        assert f"<b>{reading}</b>" in tongue.group(0)


def test_a_russian_page_says_it_is_russian() -> None:
    html = front_page("ru", ADDRESS)
    assert '<html lang="ru"' in html
    assert "Учите современный и библейский иврит" in html
    assert 'hreflang="ru"' in html, "a crawler is told the two addresses are one page"
