"""When the door is open, every door says so (targum-internal#671; design.md §12,
2026-11-10).

#485 opened accounts to strangers behind `TARGUM_OPEN_SIGNUP` and changed no copy, so with
the switch on every page still asked a stranger to join a waitlist that no longer stood
between them and an account. Every template that draws the waitlist now asks
`door_is_open()` (`serve.signup_is_open`, the switch asked for with plans on): open, the
call to action is Sign up, to the sign-in page, and a page with the form mails the sign-in
link from it. Shut, or asked for without plans, every page is as it was, byte for byte.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable
from html import unescape
from http.client import HTTPConnection
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import pytest

from targum import serve
from targum.accounts import Store
from targum.render import builder

ADDRESS = "https://targum.page"
TEMPLATES = Path(builder.__file__).parent / "templates"

#: What the shut door says, in both languages the public pages speak. Not "Before you
#: join." (Перед тем как записаться.): joining targum is what an open door asks too.
WAITING = re.compile(
    r"(?i:waitlist|invited|small groups|when does it open"
    r"|список ожидания|приглаш|небольшими группами)|>Записаться<"
)

#: The switches every door is drawn under: the front door and the connector open, so the
#: pages that draw the waitlist draw it; then the open door, asked for with and without
#: the plans it needs.
SHUT = {"TARGUM_FRONT_DOOR": "1", "TARGUM_CONNECTOR": "1"}
ASKED = {**SHUT, "TARGUM_OPEN_SIGNUP": "1"}
PLANS = {**SHUT, "TARGUM_PLANS": "1"}
OPEN = {**ASKED, "TARGUM_PLANS": "1"}
SWITCHES = ("TARGUM_FRONT_DOOR", "TARGUM_CONNECTOR", "TARGUM_OPEN_SIGNUP", "TARGUM_PLANS")


def _asked(language: str) -> str:
    """The language a visitor pressed, as `Handler._asked` carries it: Russian is pressed,
    English is where the browser decided."""
    return "" if language == "en" else language


def _too_often(language: str) -> dict[str, str]:
    """What `_try_post` hands the front page when a visitor has tried too many links."""
    return {
        "refused": serve.said_in(
            language,
            "open-door.too-often" if serve.signup_is_open() else "door.too-often",
            "",
        )
    }


def _entry() -> Any:
    from targum.catalogue import everything

    return next(iter(everything()))


TRIED = {
    "door": "youtube",
    "title": "A video",
    "site": "",
    "minutes": 3,
    "sentences": 0,
    "subtitles": True,
    "link": "https://www.youtube.com/watch?v=abc",
}

#: Every public page, and the sign-in page, with the template that draws it. A template
#: that includes the bar, the foot or the form and is missing here fails
#: `test_the_walk_misses_no_public_page`.
PAGES: list[tuple[str, str, Callable[[str], str]]] = [
    ("front", "landing.html.j2", lambda lang: builder.front_page(lang, ADDRESS, _asked(lang))),
    (
        "front, a link tried",
        "landing.html.j2",
        lambda lang: builder.front_page(lang, ADDRESS, _asked(lang), tried=TRIED),
    ),
    (
        # The box refused a try: too many links this hour (qa-claude on targum#1180).
        "front, a try refused",
        "landing.html.j2",
        lambda lang: builder.front_page(lang, ADDRESS, _asked(lang), tried=_too_often(lang)),
    ),
    ("aliyah", "aliyah.html.j2", lambda lang: builder.aliyah_page(lang, ADDRESS, _asked(lang))),
    # English only (targum-internal#676): the language is ignored, and both walks see it.
    (
        "after-duolingo-hebrew",
        "after_duolingo.html.j2",
        lambda lang: builder.after_duolingo_page(ADDRESS),
    ),
    (
        "after-duolingo-hebrew, a link tried",
        "after_duolingo.html.j2",
        lambda lang: builder.after_duolingo_page(ADDRESS, tried=TRIED),
    ),
    ("about", "about.html.j2", lambda lang: builder.about_page(lang, ADDRESS)),
    ("how", "how.html.j2", lambda lang: builder.how_page(lang, ADDRESS)),
    ("credits", "credits.html.j2", lambda lang: builder.credits_page(lang, ADDRESS)),
    ("holding", "holding.html.j2", lambda lang: builder.holding_page(lang)),
    (
        "connect",
        "connect.html.j2",
        lambda lang: builder.connect_page(lang, ADDRESS, asked=_asked(lang)),
    ),
    ("library", "shelf.html.j2", lambda lang: builder.shelf_page(ADDRESS, lang, _asked(lang))),
    ("text", "text.html.j2", lambda lang: builder.text_page(_entry(), ADDRESS, lang)),
    (
        "sign-in",
        "signin.html.j2",
        lambda lang: builder.signin_page(language=lang, asked=_asked(lang)),
    ),
    (
        # What the server hands the page while the front door takes an address; the page
        # still says nothing of it once the door is open.
        "sign-in, the waitlist handed",
        "signin.html.j2",
        lambda lang: builder.signin_page(language=lang, join="/#join"),
    ),
    (
        "a note from the door",
        "weekly-note.html.j2",
        lambda lang: builder.weekly_note("Thanks.", language=lang, home="/"),
    ),
]

#: The legal documents describe what is kept of somebody on the waitlist, which stays true
#: of every row already there; a notice changes by its own decision, not by a switch. And
#: /connect signed in is the desk's, where nobody is asked to join (§6).
NOT_WALKED = {"legal.html.j2", "connect-desk.html.j2"}


def _switched(monkeypatch: pytest.MonkeyPatch, switches: dict[str, str]) -> None:
    for name in SWITCHES:
        monkeypatch.delenv(name, raising=False)
    for name, value in switches.items():
        monkeypatch.setenv(name, value)


def _walk(monkeypatch: pytest.MonkeyPatch, switches: dict[str, str]) -> dict[str, str]:
    _switched(monkeypatch, switches)
    return {f"{name} ({lang})": draw(lang) for name, _, draw in PAGES for lang in ("en", "ru")}


def test_the_walk_misses_no_public_page() -> None:
    drawing = re.compile(r"_public_foot|_front_bar|_join_form|_join_end|_connect_body")
    found = {
        path.name
        for path in TEMPLATES.glob("*.html.j2")
        if not path.name.startswith("_") and drawing.search(path.read_text(encoding="utf-8"))
    }
    walked = {template for _, template, _ in PAGES}
    assert found - NOT_WALKED <= walked, sorted(found - NOT_WALKED - walked)


def test_with_the_door_open_no_public_page_says_waitlist_or_invited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, page in _walk(monkeypatch, OPEN).items():
        said = WAITING.search(unescape(page))
        assert said is None, f"{name} still says {said.group(0)!r}"
        assert "/waitlist" not in page and "#join" not in page, name


def test_with_the_door_open_the_call_to_action_is_sign_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = _walk(monkeypatch, OPEN)
    entry = _entry()
    for lang, sign_up, ask in (("en", "Sign up", ""), ("ru", "Регистрация", "?lang=ru")):
        # The foot's, on every page in front of the door.
        for name in ("front", "aliyah", "about", "how", "credits", "connect", "library", "text"):
            foot = f'<a class="sf-join" href="/account/signin">{sign_up} '
            assert foot in pages[f"{name} ({lang})"], (name, lang)
        # The bar's, on every page that wears it.
        for name in ("front", "aliyah", "library"):
            bar = f'<a class="btn cta small" href="/account/signin{ask}">{sign_up}</a>'
            assert bar in pages[f"{name} ({lang})"], (name, lang)
        # A text's press carries the text through the sign-in page, and "Already invited?"
        # goes: Sign up and Sign in are one page.
        text = pages[f"text ({lang})"]
        door = f"/account/signin?next=%2Fopen%2F{entry.id}" + (
            "&amp;lang=ru" if lang == "ru" else ""
        )
        assert re.findall(r'<a class="go" href="([^"]+)">([^<]+)</a>', text) == [(door, sign_up)]
        assert 'class="door-in"' not in text
        # The Library's one press, and /connect's account line.
        library = pages[f"library ({lang})"]
        assert f'<a class="btn cta" href="/account/signin{ask}">{sign_up}</a>' in library
        assert f'<a href="/account/signin{ask}">{sign_up}</a></p>' in pages[f"connect ({lang})"]
        # Every form on a public page mails the sign-in link, from /signup.
        for name in ("front", "front, a link tried", "aliyah", "connect"):
            actions = re.findall(
                r'<form class="join-form"[^>]* action="([^"]+)"', pages[f"{name} ({lang})"]
            )
            assert actions and set(actions) == {"/signup" + ask}, (name, lang, actions)
    assert "Free to read once you’re in." in pages["text (en)"]
    english = pages["front (en)"]
    assert '<p class="label">Sign up</p>' in english
    assert "Start learning Hebrew this way." in english
    assert "Enter your email and we’ll send you a link. There’s no password." in english
    assert "Free to start, with the whole library open." in english
    tried = pages["front, a link tried (en)"]
    assert "Sign up and this link will be waiting for you." in tried
    assert f'name="link" value="{TRIED["link"]}"' in tried
    for name in ("sign-in (en)", "sign-in, the waitlist handed (en)"):
        signin = unescape(pages[name])
        assert "If you're new, the same link sets up your account." in signin, name
        assert "New here?" not in signin, name
    assert "that’s what your AI reads.</p>" in pages["connect (en)"]


@pytest.mark.parametrize("switches", [ASKED, PLANS], ids=["asked-without-plans", "plans-only"])
@pytest.mark.parametrize("front", [True, False], ids=["front-door-open", "front-door-shut"])
def test_short_of_the_open_door_every_page_is_as_it_was(
    monkeypatch: pytest.MonkeyPatch, switches: dict[str, str], front: bool
) -> None:
    """The switch asked for without plans is the switch off (qa-claude on targum#1160),
    and so is plans without the switch: every page byte for byte as with neither."""
    drop = set() if front else {"TARGUM_FRONT_DOOR"}
    shut = _walk(monkeypatch, {k: v for k, v in SHUT.items() if k not in drop})
    either = _walk(monkeypatch, {k: v for k, v in switches.items() if k not in drop})
    for name, page in shut.items():
        assert either[name] == page, name
    if front:
        assert 'href="#join">Join the waitlist</a>' in shut["front (en)"]
        assert "Already invited?" in shut["text (en)"]
        assert "If you've been invited" in unescape(shut["sign-in (en)"])


# -- the server --------------------------------------------------------------


def _box(
    tmp_path: Path, free_port: Callable[[], int], links: list[tuple[str, str]]
) -> tuple[int, Store]:
    """A hosted server of its own, whose mailer writes down who it mailed, and what."""

    class Mailer:
        def send(self, to: str, link: str, language: str = "en") -> None:
            links.append((to, link))

        def notify(
            self,
            to: str,
            subject: str,
            body: str,
            headers: object = None,
            html: str | None = None,
        ) -> None:
            links.append((to, body))

    store_path = tmp_path / "box.db"
    store = Store(store_path)
    port = free_port()
    threading.Thread(
        target=lambda: serve.start(
            out=tmp_path / "out",
            port=port,
            open_browser=False,
            store=store_path,
            mailer=Mailer(),
            require_account=True,
            public_address=ADDRESS,
        ),
        daemon=True,
    ).start()
    for _ in range(60):
        try:
            probe = HTTPConnection("127.0.0.1", port, timeout=1)
            probe.request("GET", "/health")
            probe.getresponse().read()
            probe.close()
            break
        except OSError:
            time.sleep(0.1)
    return port, store


def _ask(port: int, method: str, path: str, body: bytes = b"", kind: str = "") -> tuple[int, str]:
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest(method, path, skip_host=True)
    conn.putheader("Host", "targum.page")
    conn.putheader("X-Forwarded-For", "203.0.113.7")
    if body:
        conn.putheader("Content-Type", kind)
        conn.putheader("Content-Length", str(len(body)))
    conn.endheaders()
    if body:
        conn.send(body)
    response = conn.getresponse()
    said = response.read().decode("utf-8")
    conn.close()
    return response.status, unescape(said)


def _sign_up(port: int, path: str = "/signup", **form: str) -> tuple[int, str]:
    body = urlencode(form).encode()
    return _ask(port, "POST", path, body, "application/x-www-form-urlencoded")


def test_the_open_door_s_form_mails_the_sign_in_link(
    tmp_path: Path, free_port: Callable[[], int], monkeypatch: pytest.MonkeyPatch
) -> None:
    links: list[tuple[str, str]] = []
    port, _ = _box(tmp_path, free_port, links)
    _switched(monkeypatch, OPEN)
    status, page = _sign_up(port, email="new@example.com")
    assert status == 200
    assert "<h1>Check your email</h1>" in page
    assert "Thanks. We've sent a link to new@example.com." in page
    assert "<title>Sign up — targum</title>" in page
    assert WAITING.search(page) is None
    assert [to for to, _ in links] == ["new@example.com"]
    assert "/account/enter?t=" in links[-1][1]
    # In the language of the page the form stood on.
    status, page = _sign_up(port, "/signup?lang=ru", email="novyi@example.com")
    assert status == 200 and "Спасибо. Мы отправили ссылку на novyi@example.com." in page
    assert links[-1][1].endswith("&lang=ru")


def test_a_link_tried_at_the_front_door_waits_in_upload(
    tmp_path: Path, free_port: Callable[[], int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The try box keeps the link for them: the mailed link lands on Upload holding it,
    and nothing is built (design.md §12, 2026-11-10)."""
    links: list[tuple[str, str]] = []
    port, _ = _box(tmp_path, free_port, links)
    _switched(monkeypatch, OPEN)
    tried = "https://www.youtube.com/watch?v=abc&t=3"
    assert _sign_up(port, email="new@example.com", link=tried)[0] == 200
    mailed = parse_qs(urlparse(links[-1][1]).query)
    assert mailed["next"] == ["/add?source=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3Dabc%26t%3D3"]
    # Nothing a stranger wrote in the field is a way off the site.
    assert _sign_up(port, email="other@example.com", link="javascript:alert(1)")[0] == 200
    assert "next" not in parse_qs(urlparse(links[-1][1]).query)


def test_the_open_door_s_form_keeps_the_sign_in_s_gates(
    tmp_path: Path, free_port: Callable[[], int], monkeypatch: pytest.MonkeyPatch
) -> None:
    links: list[tuple[str, str]] = []
    port, store = _box(tmp_path, free_port, links)
    _switched(monkeypatch, OPEN)
    status, page = _sign_up(port, email="not an address")
    assert status == 400 and "Check your email address" in page
    status, page = _sign_up(port, email="someone@mailinator.com")
    assert status == 403 and "throwaway" in page
    # An inbox taken off the guest list is told so in the open door's words, never
    # "targum isn't open yet", which an open door does not say.
    store.invite("pest@example.com")
    store.uninvite("pest@example.com")
    status, page = _sign_up(port, email="pest@example.com")
    assert status == 403 and "We can't open an account at that address." in page
    assert "isn't open yet" not in page
    assert links == []


def test_shut_the_form_is_not_there(
    tmp_path: Path, free_port: Callable[[], int], monkeypatch: pytest.MonkeyPatch
) -> None:
    links: list[tuple[str, str]] = []
    port, _ = _box(tmp_path, free_port, links)
    for switches in (SHUT, ASKED):
        _switched(monkeypatch, switches)
        assert _sign_up(port, email="new@example.com")[0] != 200, switches
    assert links == []


def test_with_the_door_open_the_sign_in_page_and_a_reader_say_no_waitlist(
    tmp_path: Path, free_port: Callable[[], int], monkeypatch: pytest.MonkeyPatch
) -> None:
    links: list[tuple[str, str]] = []
    port, _ = _box(tmp_path, free_port, links)
    _switched(monkeypatch, SHUT)
    assert "New here?" in _ask(port, "GET", "/account/signin")[1]
    assert json.loads(_ask(port, "GET", "/account/me")[1])["join"] == "/#join"
    _switched(monkeypatch, OPEN)
    status, page = _ask(port, "GET", "/account/signin")
    assert status == 200 and WAITING.search(page) is None
    assert "If you're new, the same link sets up your account." in page
    # A signed-out reader keeps "Sign in to keep the words you mark" and nothing beside it.
    assert "join" not in json.loads(_ask(port, "GET", "/account/me")[1])


def test_a_try_refused_at_the_open_door_does_not_wait_to_be_invited(
    tmp_path: Path, free_port: Callable[[], int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """qa-claude on targum#1180: too many links tried in an hour said «…когда вас
    пригласят» at a door that invites nobody. Open, it says sign up; shut, as it was."""
    links: list[tuple[str, str]] = []
    port, _ = _box(tmp_path, free_port, links)
    monkeypatch.setattr(serve, "TRIES_PER_HOUR", 0)
    for switches, lang, said in (
        (OPEN, "ru", "зарегистрируйтесь и загрузите их, когда войдёте"),
        (OPEN, "en", "or sign up and upload them when you're in."),
        (SHUT, "ru", "когда вас пригласят"),
    ):
        _switched(monkeypatch, switches)
        body = urlencode({"link": "https://www.youtube.com/watch?v=abc"}).encode()
        status, page = _ask(
            port, "POST", f"/try?lang={lang}", body, "application/x-www-form-urlencoded"
        )
        assert status == 200 and said in page, (switches, lang)
        if switches is OPEN:
            assert WAITING.search(page) is None, lang


def _posted(
    port: int, path: str, body: bytes, kind: str, fetched_from: str | None, visitor: int = 9
) -> tuple[int, str]:
    """A post as a browser sends it, naming where it came from in `Sec-Fetch-Site`."""
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("POST", path, skip_host=True)
    conn.putheader("Host", "targum.page")
    conn.putheader("X-Forwarded-For", f"203.0.113.{visitor}")
    if fetched_from is not None:
        conn.putheader("Sec-Fetch-Site", fetched_from)
    conn.putheader("Content-Type", kind)
    conn.putheader("Content-Length", str(len(body)))
    conn.endheaders()
    conn.send(body)
    response = conn.getresponse()
    said = response.read().decode("utf-8")
    conn.close()
    return response.status, said


#: Each post that mails a link to the address it is given (targum-internal#688), as its
#: own page sends it, with the switches that open it.
MAILING = {
    "/account/sign-in": ("application/json", lambda to: json.dumps({"email": to}).encode()),
    "/waitlist": (
        "application/x-www-form-urlencoded",
        lambda to: urlencode({"email": to}).encode(),
    ),
    "/signup": ("application/x-www-form-urlencoded", lambda to: urlencode({"email": to}).encode()),
    "/weekly/subscribe": (
        "application/x-www-form-urlencoded",
        lambda to: urlencode({"email": to}).encode(),
    ),
}


@pytest.mark.parametrize("path", sorted(MAILING))
def test_a_mailing_post_from_another_site_is_refused(
    path: str,
    tmp_path: Path,
    free_port: Callable[[], int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A form on another site could otherwise mail a link to an address it chose, counted
    against the visitor's IP. A browser names such a post `cross-site`; ours, a typed
    address, and an old browser or curl that sends no header at all still get through.
    The mailer here records every letter, the weekly's and the waitlist's as well as
    sign-in's, so "nothing mailed" is a real check."""
    links: list[tuple[str, str]] = []
    port, store = _box(tmp_path, free_port, links)
    _switched(monkeypatch, SHUT if path == "/waitlist" else OPEN)
    monkeypatch.setenv("TARGUM_PUBLIC_SHELVES", "1")
    kind, body = MAILING[path]
    store.invite("guest@example.com")
    status, said = _posted(port, path, body("guest@example.com"), kind, "cross-site")
    assert status == 403, said
    assert links == []
    # One visitor and address each, so the doors' own limits never answer instead.
    for visitor, fetched_from in enumerate(("same-origin", "same-site", "none", None), 20):
        address = f"guest{visitor}@example.com"
        store.invite(address)
        status, said = _posted(port, path, body(address), kind, fetched_from, visitor)
        assert status == 200, (fetched_from, status, said)
        assert links[-1][0] == address, fetched_from


def test_sign_in_takes_only_a_body_named_as_json(
    tmp_path: Path, free_port: Callable[[], int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A form on another site can send JSON as text/plain without the browser asking
    first; our own script always names the type, so nothing else is read."""
    links: list[tuple[str, str]] = []
    port, store = _box(tmp_path, free_port, links)
    _switched(monkeypatch, OPEN)
    store.invite("guest@example.com")
    body = json.dumps({"email": "guest@example.com"}).encode()
    for kind in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data"):
        status, _ = _posted(port, "/account/sign-in", body, kind, None)
        assert status == 415, kind
    assert links == []
    status, _ = _posted(port, "/account/sign-in", body, "application/json; charset=utf-8", None)
    assert status == 200
    assert [to for to, _ in links] == ["guest@example.com"]
