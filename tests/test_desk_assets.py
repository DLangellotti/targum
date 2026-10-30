"""A desk page loads its stylesheets and scripts once and keeps them (design.md §12, "A
desk page loads its files once and keeps them", 2026-10-18, targum-internal#484).

The desk names its files under `/assets/<name>.<hash>.<ext>`, served for a year as
immutable. Everything else still carries its files inline and fetches nothing: readers,
contents pages, the series pages, a card in a host's frame, a printed page, and
Saved on this device, the one desk page a worker keeps for offline. The public pages in
front of the account (the front door, a text's page, About, the legal pages) joined the
desk on 2026-10-28 (targum-internal#549), and the public Library on 2026-10-29 (#558)."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from http.client import HTTPConnection
from pathlib import Path

import pytest
import test_serve

from targum.render import builder
from targum.render.builder import (
    ASSET_ROUTE,
    DESK_PAGES,
    TEMPLATES,
    asset_address,
    asset_files,
    carried,
    list_page,
    progress_page,
    saved_page,
)
from targum.serve import Handler

served = test_serve.served
postbox = test_serve.postbox

TOKEN = "test-key"
_INLINE = re.compile(r"<(script|style)\b([^>]*)>(.*?)</\1>", re.S)
_NAMED = re.compile(r'(?:src|href)="(' + re.escape(ASSET_ROUTE) + r'[^"]+)"')

#: The pages that must keep inlining, whatever is added to the desk: each is opened off a
#: disk, framed by a host, printed, or kept by the worker for offline.
STAYS_INLINE = {
    "reader.html.j2",
    "contents.html.j2",
    "index.html.j2",
    "print.html.j2",
    "saved.html.j2",
    "card-build.html.j2",
    "card-offer.html.j2",
    "card-text.html.j2",
    "series.html.j2",
    "weekly-note.html.j2",
    "how.html.j2",
    "holding.html.j2",
    "connect.html.j2",
    "approve.html.j2",
    "connect_refused.html.j2",
    "backoffice.html.j2",
}


def _big_inline_blocks(html: str, over: int = 4000) -> list[str]:
    """Inline blocks over `over` characters that are not the page's own data."""
    return [
        body[:60]
        for _, attributes, body in _INLINE.findall(html)
        if len(body) > over
        and "application/json" not in attributes
        and not body.lstrip().startswith("window.TARGUM_")
    ]


def test_every_desk_page_is_a_template_that_exists_and_no_reader_is_one() -> None:
    names = {path.name for path in TEMPLATES.glob("*.j2")}
    assert DESK_PAGES <= names, DESK_PAGES - names
    assert not DESK_PAGES & STAYS_INLINE, DESK_PAGES & STAYS_INLINE
    assert STAYS_INLINE <= names, STAYS_INLINE - names


@pytest.mark.parametrize("which", ["texts", "words"])
def test_a_desk_page_names_its_files_and_carries_no_big_script(which: str) -> None:
    html = list_page(TOKEN, which)
    named = _NAMED.findall(html)
    if which == "texts":
        assert asset_address("home.js") in named
    assert asset_address("chrome.css") in named
    assert asset_address("face-chrome.css") in named, "the chrome's face rides as a file too"
    assert _big_inline_blocks(html) == []
    # Every file it names is one the server holds.
    assert set(named) <= set(asset_files())
    # strings.js stays inline beside the strings it reads.
    assert str(builder._asset("strings.js")) in html


def test_a_desk_page_runs_its_scripts_in_the_order_it_did() -> None:
    """A classic script by address runs where it stands, as the inline one did; so the
    order of scripts on the page is the order of the asset names, inline ones between."""
    html = list_page(TOKEN, "texts")
    order = re.findall(r'<script\b[^>]*src="/assets/([a-z0-9-]+)\.', html)
    assert order.index("sync") < order.index("home") < order.index("yours")
    assert not re.search(r'<script\b[^>]*src="/assets/[^"]+"[^>]*\b(?:defer|async)\b', html)


def test_saved_on_this_device_keeps_inlining() -> None:
    """The worker keeps this page for offline, alone, so its copy must need nothing else."""
    html = saved_page(TOKEN)
    assert ASSET_ROUTE not in html
    assert str(builder._asset("saved.js")) in html


def test_a_desk_page_in_russian_still_carries_what_its_files_ask_for() -> None:
    """`_with_called_strings` reads the files a page names as well as the page: a key a
    linked script calls still rides in the page's own TARGUM_STRINGS."""
    from targum.strings import catalogue

    html = progress_page(TOKEN, language="ru")
    assert ASSET_ROUTE in html
    called = dict.fromkeys(builder._CALLED.findall(builder.linked_scripts(html)))
    assert called, "the progress page's files call catalogued sentences"
    at = re.search(r"window\.TARGUM_STRINGS\s*=\s*", html)
    assert at is not None
    given, _ = json.JSONDecoder().raw_decode(html, at.end())
    known = catalogue("ru")
    missing = [key for key in called if key in known and key not in given["strings"]]
    assert missing == []


def test_the_files_are_named_by_their_bytes() -> None:
    files = asset_files()
    assert files, "nothing to serve"
    kinds = {
        "js": "text/javascript",
        "css": "text/css",
        "jpg": "image/jpeg",
        "json": "application/json",
    }
    for address, (body, kind, name) in files.items():
        # A picture is named by its folder (`scroll/columns.jpg`) and served by its name.
        stem, _, ext = name.rpartition("/")[2].rpartition(".")
        digest = hashlib.sha256(body).hexdigest()[:16]
        assert address == f"{ASSET_ROUTE}{stem}.{digest}.{ext}", "named by its own bytes"
        named = r"/assets/[a-z0-9-]+\.[0-9a-f]{16}\.(js|css|jpg|json)"
        assert re.fullmatch(named, address), address
        assert kind.startswith(kinds[ext])
        assert body
    assert not any(name == "sw.js" for _, _, name in files.values()), "the worker is at the root"


def test_carried_puts_every_named_file_back_where_it_stood() -> None:
    whole = carried(list_page(TOKEN, "texts"))
    assert ASSET_ROUTE not in whole
    sync, home = str(builder._asset("sync.js")), str(builder._asset("home.js"))
    assert sync in whole and home in whole
    assert whole.index(sync) < whole.index(home)


def _get(
    port: int, path: str, headers: dict[str, str] | None = None
) -> tuple[int, dict[str, str], bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request("GET", path, headers=headers or {})
        response = connection.getresponse()
        return response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
    finally:
        connection.close()


def test_a_file_is_kept_for_a_year_and_a_wrong_hash_is_not_there(
    served: tuple[int, str, Path],
) -> None:
    port = served[0]
    address = asset_address("home.js")
    # No key and no cookie: the sign-in page names these files too.
    status, headers, body = _get(port, address)
    assert status == 200
    assert headers["cache-control"] == "public, max-age=31536000, immutable"
    assert headers["content-type"] == "text/javascript; charset=utf-8"
    assert headers["x-content-type-options"] == "nosniff"
    assert body == asset_files()[address][0]
    assert "content-security-policy" not in headers, "a policy is a page's, not a file's"
    status, headers, body = _get(port, address, {"Accept-Encoding": "gzip"})
    assert status == 200 and headers.get("content-encoding") == "gzip"
    assert gzip.decompress(body) == asset_files()[address][0]
    status, headers, _ = _get(port, asset_address("face-chrome.css"))
    assert status == 200 and headers["content-type"] == "text/css; charset=utf-8"

    stem = address.rsplit(".", 2)[0]
    for wrong in (
        f"{stem}.0000000000000000.js",
        f"{ASSET_ROUTE}home.js",
        f"{ASSET_ROUTE}sw.js",
        f"{ASSET_ROUTE}../serve.py",
        f"{ASSET_ROUTE}fonts/NotoSansHebrew-Regular.woff2",
    ):
        status, headers, _ = _get(port, wrong)
        assert status == 404, wrong
        assert "immutable" not in headers.get("cache-control", ""), wrong


def _directives(policy: str) -> dict[str, list[str]]:
    parts = [one.split() for one in policy.split(";") if one.strip()]
    return {part[0]: part[1:] for part in parts}


def test_the_policy_lets_a_desk_page_load_its_own_files_and_nothing_else() -> None:
    """`'self'` joins script-src and style-src only on a page that names files under
    `/assets/`; inline blocks are still hashed, and nothing is `'unsafe-inline'`."""
    policy = Handler._policy(list_page(TOKEN, "texts").encode("utf-8"))
    directives = _directives(policy)
    assert directives["default-src"] == ["'none'"]
    assert directives["frame-ancestors"] == ["'none'"]
    assert directives["form-action"] == ["'self'"]
    assert directives["font-src"] == ["data:"], "the faces are still data: URIs in their sheets"
    for name in ("script-src", "style-src"):
        sources = directives[name]
        assert sources[0] == "'self'", name
        assert len(sources) > 1, f"{name}: the page's inline blocks are still named by hash"
        assert all(source.startswith("'sha256-") for source in sources[1:]), name
    assert "'unsafe-inline'" not in policy


def test_a_page_that_names_no_file_is_held_to_its_hashes() -> None:
    for page in (saved_page(TOKEN), builder.holding_page()):
        directives = _directives(Handler._policy(page.encode("utf-8")))
        assert "'self'" not in directives["script-src"]
        assert "'self'" not in directives["style-src"]
    # A page naming only a script gains 'self' for scripts and not for styles.
    page = (
        b"<html><head><style>a{}</style></head><body>"
        b'<script src="/assets/a.0123456789abcdef.js"></script></body></html>'
    )
    directives = _directives(Handler._policy(page))
    assert directives["script-src"][0] == "'self'"
    assert "'self'" not in directives["style-src"]
    # Text that only mentions the route is not a file the page loads.
    page = b'<html><body><p>&lt;script src="/assets/x.js"&gt;</p><script>x=1</script></body></html>'
    assert "'self'" not in _directives(Handler._policy(page))["script-src"]


def _public_pages() -> dict[str, str]:
    from targum.catalogue import Entry

    entry = Entry(
        id="ruth",
        title="רות",
        author="Ketuvim · Ruth",
        language="he",
        source="sefaria:Ruth",
        blurb="Four chapters.",
        words=1129,
    )
    return {
        "front door": builder.front_page(address="https://targum.page"),
        "about": builder.about_page(address="https://targum.page"),
        "privacy": builder.legal_page("privacy", "https://targum.page"),
        "terms": builder.legal_page("terms", "https://targum.page"),
        "a text's page": builder.text_page(entry, "https://targum.page"),
        # Missed in #549 and added on 2026-10-29 (targum-internal#558).
        "the public Library": builder.shelf_page("https://targum.page"),
        "a kind's page": builder.kind_page("he", "story", "https://targum.page") or "",
    }


def test_the_pages_in_front_of_the_account_load_their_files_once() -> None:
    """targum-internal#549 (design.md §12, 2026-10-28, proposed): each carried 65 to 122 kB
    of faces and up to 290 kB of CSS on every page a stranger opened. Kept, a page names
    them by address, every one a file the server holds, and its policy lets it load them;
    a first visit gets the page whole, its scripts held to their hashes, as a desk page."""
    for name, html in _public_pages().items():
        named = _NAMED.findall(html)
        assert any("/face-" in one for one in named), f"{name}: its faces ride as files"
        assert set(named) <= set(asset_files()), name
        assert _big_inline_blocks(html) == [], name
        linked = _directives(Handler._policy(html.encode("utf-8")))
        assert linked["style-src"][0] == "'self'", name
        whole = builder.first_visit(html)
        # The faces wait in an inert <template> that nothing fetches until `load`.
        live = re.sub(r'<template id="late-faces">.*?</template>', "", whole, flags=re.S)
        assert not builder.names_files(live), f"{name}: a first visit names no file"
        held = _directives(Handler._policy(whole.encode("utf-8")))
        # Its scripts are held to their hashes; styles keep `'self'` for the late faces
        # alone, which `warm.js` puts on at `load` (design.md §12, 2026-10-23).
        assert "'self'" not in held["script-src"], name
        assert "'unsafe-inline'" not in " ".join(sum(held.values(), [])), name
