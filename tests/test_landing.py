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
            "welcome": "<html>start</html>",
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
        "https://x.com/targum_app",  # and targum's own accounts beside it
        "https://www.instagram.com/targum.page/",
        "https://www.linkedin.com/company/targum-page/",
        f"{ADDRESS}/",  # its own canonical
        f"{ADDRESS}/?lang=ru",  # and the same page in the other language
    }
    assert not re.search(r"url\(\s*['\"]?https?:", html), "a stylesheet fetches something"


def test_the_foot_links_targums_own_accounts_in_both_languages() -> None:
    """The accounts are the brand's, not the page's language: the Russian door links the
    same ones, named by their platforms, marked as this site's own. Drawn as glyphs since
    2026-09-28, so the name is the label rather than the text."""
    from targum.render.builder import SOCIAL

    for language in ("en", "ru"):
        html = front_page(language, ADDRESS)
        for name, address in SOCIAL:
            assert f'<a href="{address}" rel="me" aria-label="{name}"' in html, (language, name)


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
    """One waitlist form, the ending's, and a plain post. The hero has one call to action,
    the box (2026-10-02): its form posts to `/try` and draws the waitlist, carrying the
    link, only once something was tried (targum-internal#399, `test_try_the_door.py`)."""
    html = front_page("en", ADDRESS)
    forms = re.findall(r'<form[^>]*action="/waitlist"[^>]*>', html)
    assert len(forms) == 1
    for form in forms:
        assert 'method="post"' in form
    assert html.count('name="email"') == 1
    hero = html[html.index('<div class="hero">') : html.index('class="showcase"')]
    assert hero.count("<form") == 1 and 'class="try-form"' in hero, "one action in the hero"
    assert '<form class="try-form" method="post" action="/try#try">' in html


def test_the_page_promises_no_order_and_no_price() -> None:
    """Nothing about the order people are let in, which the operator also does by hand,
    and nothing about who hears the price first, which is not decided."""
    html = front_page("en", ADDRESS)
    assert "The earlier you join" not in html
    assert "hears what it costs" not in html


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
    assert "We’ve sent you an email to confirm" in body
    assert store.waiting_state("dina@example.com") == "pending"
    sent = posted.getvalue()
    assert "dina@example.com" in sent
    assert "/waitlist/confirm?t=" in sent


def test_the_waitlist_s_answer_has_a_tab_of_its_own(
    served: tuple[int, Store, io.StringIO], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copy audit, 2026-09-28 (Q23): it borrowed the weekly's furniture and its title
    with it, so the tab said "Weekly News Digest" over an answer about the waitlist."""
    port, _, _ = served
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")
    _, body = post(port, "/waitlist", {"email": "tab@example.com"})
    head = body.split("</head>")[0]
    assert "<title>The waitlist — targum</title>" in head
    assert "Weekly News Digest" not in head
    assert 'rel="canonical"' not in head or "/weekly" not in head


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


# -- and all of it in the language they came through (targum-internal#288) --------------


def test_the_front_door_answers_in_the_language_it_was_read_in(
    served: tuple[int, Store, io.StringIO], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The door has been bilingual since #69 and `waiting.language` has recorded which
    one somebody came through since #292 — and only the invitation ever read it back. So
    a visitor typed their address into a Russian page and every single thing targum said
    between joining and being invited was English, starting with the mail.
    """
    port, store, posted = served
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")

    status, body = post(port, "/waitlist?lang=ru", {"email": "dina@example.com"})
    assert status == 200
    assert "Мы отправили вам письмо для подтверждения" in body
    assert "We’ve sent you an email to confirm" not in body
    assert 'lang="ru"' in body, "the page says which language it is in"

    # The mail too, which is the first thing targum ever sends anybody.
    sent = posted.getvalue()
    assert "Подтвердите место в списке ожидания targum" in sent
    assert "Confirm your place" not in sent

    # And the row remembers it, so the page the mail leads to is Russian without the
    # link having to say so. The token comes out of the mail, which is the only place it
    # exists in the clear — `confirm` is hashed in the row, like a sign-in link.
    token = re.search(r"/waitlist/confirm\?t=(\S+)", sent).group(1)
    assert store.waiting_language(token) == "ru"

    status, page = get(port, f"/waitlist/confirm?t={token}")
    assert status == 200
    assert "Подтвердите dina@example.com, чтобы сохранить место" in page
    assert "Подтвердить" in page and ">Confirm<" not in page

    status, page = post(port, "/waitlist/confirm", {"t": token})
    assert status == 200 and "Вы в списке" in page and "Спасибо за подтверждение" in page
    assert store.waiting_state("dina@example.com") == "on"


def test_the_form_posts_in_the_language_that_was_pressed(
    served: tuple[int, Store, io.StringIO], monkeypatch: pytest.MonkeyPatch
) -> None:
    """targum-internal#391. The test above posts to `/waitlist?lang=ru` by hand, and the
    page itself never did: its form posted to `/waitlist`, so a visitor on an English
    browser who pressed RU was answered, mailed and invited in English. Read the action
    off the page and post to it, with the browser asking for the other language."""
    port, store, posted = served
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")

    def actions(path: str, browser: str) -> set[str]:
        connection = HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request("GET", path, headers={"Accept-Language": browser})
            page = connection.getresponse().read().decode("utf-8")
        finally:
            connection.close()
        return set(re.findall(r'<form class="join-form" method="post" action="([^"]+)"', page))

    pressed = actions("/?lang=ru", "en-US,en;q=0.9")
    assert pressed == {"/waitlist?lang=ru"}, pressed
    # Where nothing was pressed the browser decides, at the post as on the page.
    assert actions("/", "ru-RU,ru;q=0.9") == {"/waitlist"}

    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(
            "POST",
            pressed.pop(),
            urlencode({"email": "lev@example.com"}),
            {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        body = connection.getresponse().read().decode("utf-8")
    finally:
        connection.close()
    assert "Мы отправили вам письмо для подтверждения" in body
    assert "Подтвердите место в списке ожидания targum" in posted.getvalue()
    token = re.search(r"/waitlist/confirm\?t=(\S+)", posted.getvalue()).group(1)
    assert store.waiting_language(token) == "ru", "so the invitation is Russian too"


def test_no_join_form_drops_the_language_that_was_pressed() -> None:
    """#391 was two forms written out by hand beside the shared one, on the landing's
    close and on `/connect`. Every form that posts to the waitlist carries `asked`."""
    templates = Path(__file__).parent.parent / "src" / "targum" / "render" / "templates"
    for template in sorted(templates.glob("*.j2")):
        for action in re.findall(r'action="(/waitlist[^"]*)"', template.read_text("utf-8")):
            assert "?lang={{ asked }}" in action, f"{template.name}: {action}"


@pytest.mark.parametrize(
    ("said", "kept"),
    [
        ("/", "/"),
        ("https://targum.page/", "/"),
        ("/aliyah", "/aliyah"),
        ("https://targum.page/aliyah?lang=ru", "/aliyah"),
        ("/connect", "/connect"),
        ("/weekly/2026-w39/simplified", "/weekly"),
        ("https://targum.page/parasha/bereshit", "/parasha"),
        ("/mishna-yomi", "/mishna-yomi"),
        ("/tehillim/day-3", "/tehillim"),
        ("", ""),
        ("/library/ruth", ""),
        ("/anything-at-all", ""),
        ("javascript:alert(1)", ""),
    ],
)
def test_the_waitlist_keeps_only_a_page_of_targum_s_own(said: str, kept: str) -> None:
    """targum-internal#388. One word on a row somebody made by pressing Join, narrowed
    to the pages worth counting; anything else is unknown rather than stored as sent."""
    from targum.serve import joined_from

    assert joined_from(said) == kept


def test_the_front_door_says_which_page_its_form_is_on(
    served: tuple[int, Store, io.StringIO], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every form on the front door says `/`, and the row keeps it."""
    port, store, _ = served
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")
    status, page = get(port, "/")
    assert status == 200
    said = re.findall(r'<input type="hidden" name="from" value="([^"]*)">', page)
    assert said and set(said) == {"/"}, said

    post(port, "/waitlist", {"email": "noa@example.com", "from": said[0]})
    row = store.db.execute(
        "SELECT page FROM waiting WHERE email = ?", ("noa@example.com",)
    ).fetchone()
    assert row["page"] == "/"


def test_a_page_with_no_name_of_its_own_is_known_by_its_address() -> None:
    """`/aliyah` (targum#543) renders the shared form without naming itself; the form
    falls back to the page's canonical address, which the server narrows."""
    from targum.render.builder import _environment

    form = (
        _environment()
        .get_template("_join_form.html.j2")
        .render(t=lambda _key, default, **_: default, canonical="https://targum.page/aliyah")
    )
    assert '<input type="hidden" name="from" value="https://targum.page/aliyah">' in form


def test_an_english_visitor_is_answered_as_they_always_were(
    served: tuple[int, Store, io.StringIO], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The half that would be easy to break while fixing the other one."""
    port, _store, posted = served
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")
    status, body = post(port, "/waitlist", {"email": "dina@example.com"})
    assert status == 200 and "We’ve sent you an email to confirm" in body
    assert "Confirm your place on the targum waitlist" in posted.getvalue()


def test_the_way_out_cannot_be_used_to_ask_who_is_waiting(
    served: tuple[int, Store, io.StringIO], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`/waitlist/stop` must say the same thing for a real token and a made-up one, and
    drawing the page in the *row's* language would break that: Russian for a real token
    and English for a fake one is that question answered.

    So the stop door takes the request's language, which is the same for both, and the
    mail mints its link with `?lang=` so somebody who joined in Russian still lands on a
    Russian page. Asserted in Russian precisely because English would pass either way.
    """
    port, store, _ = served
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")
    token = store.join_waitlist("dina@example.com", "ru")
    assert token and store.confirm_waiting(token)
    stop = store.db.execute(
        "SELECT stop FROM waiting WHERE email = ?", ("dina@example.com",)
    ).fetchone()["stop"]

    for lang in ("", "?lang=ru"):
        _, real = post(port, f"/waitlist/stop{lang}", {"t": stop})
        _, made_up = post(port, f"/waitlist/stop{lang}", {"t": "not-a-token"})
        assert real == made_up, f"the two replies differ at {lang!r}"
    # And the page really is Russian when asked in Russian, so the sameness above is not
    # the sameness of two English pages.
    _, said = post(port, "/waitlist/stop?lang=ru", {"t": "not-a-token"})
    assert "Мы больше не будем писать вам о списке ожидания." in said


def test_x_is_listed_as_working_only_where_its_door_is_open(monkeypatch) -> None:
    """targum-internal#158: X is a door the deployment arms. The list says so only where
    it is: 'Posts from X' on its own when the switch is on, and 'soon' when it is off.
    Reddit is not promised at all: it refused every route on 2026-09-30."""
    from targum.ingest import x as x_door
    from targum.render.builder import front_page

    monkeypatch.delenv(x_door.ENV, raising=False)
    shut = front_page()
    assert re.search(r"Posts from X<span class=\"soon\">", shut)
    monkeypatch.setenv(x_door.ENV, "1")
    armed = front_page()
    assert "Posts from X</h3>" in armed
    for page in (shut, armed):
        assert "Reddit" not in page


def test_facebook_videos_are_listed_with_the_doors_that_open() -> None:
    """Facebook's videos are fetched since 2026-09-30, so they are named with the reels,
    Shorts and TikToks, and never as 'soon'."""
    from targum.render.builder import front_page

    page = front_page()
    assert "Reels, Shorts, TikToks and Facebook videos</h3>" in page


def test_the_connector_is_mentioned_in_talk_while_it_is_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lightly, once (design.md §12, "The connector is met on the way in"): a line in the
    part about talking to targum, with the way to `/connect`, and not in the list under
    the headline, where it read as what targum is built on (David, 2026-10-02). Dark, it
    is not said: a door to a 404 is worse than none."""
    monkeypatch.setenv("TARGUM_CONNECTOR", "1")
    page = front_page()
    facts = page[page.index('<ul class="facts">') :]
    assert "Claude" not in facts[: facts.index("</ul>")]
    talk = page[page.index('id="talk"') :]
    talk = talk[: talk.index("</section>")]
    assert "It works in Claude and ChatGPT too." in talk
    assert 'href="/connect"' in talk
    monkeypatch.delenv("TARGUM_CONNECTOR")
    quiet = front_page()
    assert "It works in Claude and ChatGPT too." not in quiet


def test_every_colour_the_front_door_draws_is_a_token() -> None:
    """A design review on 2026-10-02 found 26 colours written straight into rules, three
    of them passing `test_brand.py` only by sharing a hex with something else. Each is
    named once in a `:root` block now, and a rule says a token or says nothing."""
    sheet = Path(__file__).resolve().parents[1] / "src/targum/render/assets/landing.css"
    literals: list[tuple[int, str]] = []
    in_root = False
    for number, line in enumerate(sheet.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith(":root"):
            in_root = True
        if in_root:
            in_root = not line.startswith("}")
            continue
        if line.strip().startswith(("/*", "*")):
            continue
        literals += [
            (number, found) for found in re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)", line)
        ]
    assert not literals, f"colours outside a token: {literals}"
