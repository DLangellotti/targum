"""A first visit gets the page whole (design.md §12, 2026-10-19; Privacy Notice 3.13).

A desk page names its files by address only for a browser whose kept-files cookie names
the current set. Without it, or with an older set, the page is sent whole, as before
2026-10-18, with `warm.js` to fetch the files once it is up; the cookie is given only when
they have all arrived. The Library's shelf is a file of its own, named by what it says."""

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
    KEPT_ROUTE,
    asset_files,
    asset_set,
    first_visit,
    library_page,
    list_page,
    names_files,
)
from targum.serve import KEPT_COOKIE, KEPT_DAYS, kept_cookie

served = test_serve.served
postbox = test_serve.postbox

TOKEN = "test-key"
DOOR = "/account/signin"  # a desk page, rendered per request


def _get(
    port: int, path: str, cookie: str = "", gzip_ok: bool = False
) -> tuple[int, dict[str, str], list[str], str]:
    headers = {"Cookie": cookie} if cookie else {}
    if gzip_ok:
        headers["Accept-Encoding"] = "gzip"
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        body = response.read()
        if response.getheader("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        cookies = [v for k, v in response.getheaders() if k.lower() == "set-cookie"]
        return (
            response.status,
            {k.lower(): v for k, v in response.getheaders()},
            cookies,
            body.decode("utf-8", "replace"),
        )
    finally:
        connection.close()


def _sources(policy: str, directive: str) -> list[str]:
    part = next(one for one in policy.split(";") if one.strip().startswith(directive + " "))
    return part.split()[1:]


def _blocks(html: str) -> list[bytes]:
    return [
        block.encode("utf-8")
        for block in re.findall(r"<(?:script|style)[^>]*>(.*?)</(?:script|style)>", html, re.S)
    ]


def _every_block_is_named(html: str, policy: str) -> None:
    import base64

    allowed = set(_sources(policy, "script-src")) | set(_sources(policy, "style-src"))
    for block in _blocks(html):
        digest = base64.b64encode(hashlib.sha256(block).digest()).decode("ascii")
        assert f"'sha256-{digest}'" in allowed, "an inline block the policy does not name"


# -- the page, both ways ------------------------------------------------------------


def test_a_browser_with_no_cookie_is_sent_the_page_whole(served: tuple[int, str, Path]) -> None:
    status, headers, cookies, html = _get(served[0], DOOR)
    assert status == 200
    assert not names_files(html), "a first visit names no file"
    assert 'data-kept="' + KEPT_ROUTE + "?set=" + asset_set() + '"' in html.replace("&amp;", "&")
    assert str(builder._asset("warm.js")) in html, "and it carries the warm-up"
    assert cookies == [], "the page itself gives no cookie; the warm-up's last fetch does"
    assert "Cookie" in headers["vary"]
    assert headers["cache-control"] == "no-store"
    policy = headers["content-security-policy"]
    for directive in ("script-src", "style-src"):
        assert "'self'" not in _sources(policy, directive), "nothing to load from here"
    assert "connect-src 'self'" in policy, "the warm-up's fetches"
    _every_block_is_named(html, policy)


def test_the_warm_up_fetches_this_page_s_files_first_and_then_the_desk_s() -> None:
    linked = list_page(TOKEN, "texts")
    own = re.findall(r'(?:src|href)="(/assets/[^"]+)"', linked)
    library_page(TOKEN)  # names the Library's files too
    whole = first_visit(linked)
    tag = re.search(r'<script data-files="([^"]+)"', whole)
    assert tag is not None
    files = json.loads(tag.group(1).replace("&#34;", '"').replace("&quot;", '"'))
    assert files[: len(own)] == list(dict.fromkeys(own))
    assert any("/assets/library." in name for name in files[len(own) :]), "and the desk's others"
    assert set(files) <= set(asset_files()), "only files the server holds"
    assert whole.index("data-files") > whole.index(str(builder._asset("home.js")))


def test_a_browser_that_kept_the_current_set_gets_the_page_by_address(
    served: tuple[int, str, Path],
) -> None:
    status, headers, _, html = _get(served[0], DOOR, cookie=f"{KEPT_COOKIE}={asset_set()}")
    assert status == 200
    assert names_files(html)
    assert "warm.js" not in html and "data-kept" not in html
    assert "Cookie" in headers["vary"]
    policy = headers["content-security-policy"]
    for directive in ("script-src", "style-src"):
        sources = _sources(policy, directive)
        assert sources[0] == "'self'"
        assert all(source.startswith("'sha256-") for source in sources[1:])
    assert "'unsafe-inline'" not in policy
    _every_block_is_named(html, policy)


def test_a_cookie_from_an_older_set_is_a_first_visit_again(
    served: tuple[int, str, Path],
) -> None:
    _, _, _, html = _get(served[0], DOOR, cookie=f"{KEPT_COOKIE}=0000000000000000")
    assert not names_files(html)
    assert "data-kept" in html


def test_a_page_with_no_files_does_not_vary_with_the_cookie(served: tuple[int, str, Path]) -> None:
    port, token, _ = served
    _, headers, _, _ = _get(port, f"/?k={token}")  # the fixture's stub page names nothing
    assert "Cookie" not in headers.get("vary", "")


# -- the cookie ---------------------------------------------------------------------


def test_the_cookie_is_given_for_the_current_set_and_holds_nothing_else(
    served: tuple[int, str, Path],
) -> None:
    status, headers, cookies, body = _get(served[0], f"{KEPT_ROUTE}?set={asset_set()}")
    assert status == 204 and body == ""
    assert headers["cache-control"] == "no-store"
    assert len(cookies) == 1
    parts = [part.strip() for part in cookies[0].split(";")]
    assert parts[0] == f"{KEPT_COOKIE}={asset_set()}", "the set's hash, the same for everyone"
    assert set(parts[1:]) == {"HttpOnly", "SameSite=Lax", "Path=/", f"Max-Age={KEPT_DAYS * 86400}"}
    # Asked again, the answer is the same: there is nothing in it about who asked.
    assert _get(served[0], f"{KEPT_ROUTE}?set={asset_set()}")[2] == cookies


def test_no_cookie_for_a_set_that_is_not_the_current_one(served: tuple[int, str, Path]) -> None:
    for asked in ("", "?set=0000000000000000", "?set=" + asset_set() + "x"):
        status, _, cookies, _ = _get(served[0], KEPT_ROUTE + asked)
        assert status == 204 and cookies == [], asked


def test_hosted_on_https_the_cookie_is_secure() -> None:
    assert kept_cookie("abc", "https://targum.page").endswith("; Secure")
    assert "Secure" not in kept_cookie("abc", "http://127.0.0.1:8420")


def test_the_set_changes_when_any_file_does() -> None:
    before = asset_set()
    page = library_page(TOKEN)
    assert asset_set() == before, "the same shelf names the same file"
    builder._GENERATED["/assets/catalogue.ffffffffffffffff.js"] = (b"x", "text/javascript", "x")
    try:
        assert asset_set() != before
    finally:
        del builder._GENERATED["/assets/catalogue.ffffffffffffffff.js"]
    assert asset_set() == before
    assert page


# -- the shelf ------------------------------------------------------------------------


SHELF = re.compile(r"window\.TARGUM_SHELF_FILES = (\{[^\n]*\});")


def shelf_files(html: str) -> dict[str, str]:
    found = SHELF.search(html)
    assert found is not None, "the page names the shelf's files"
    return json.loads(found.group(1))


def test_the_library_shelf_is_files_named_by_what_they_say(
    served: tuple[int, str, Path],
) -> None:
    html = library_page(TOKEN)
    assert "window.TARGUM_CATALOGUE" not in html, "the shelf is not written into the page"
    files = shelf_files(html)
    assert "" in files and "he" in files, "the common file and Hebrew's"
    for code, address in files.items():
        stem = "catalogue" + (f"-{code}" if code else "")
        found = re.fullmatch(rf"/assets/{stem}\.([0-9a-f]{{16}})\.json", address)
        assert found is not None, address
        status, headers, _, body = _get(served[0], address, gzip_ok=True)
        assert status == 200
        assert headers["cache-control"] == "public, max-age=31536000, immutable"
        assert headers["content-type"] == "application/json; charset=utf-8"
        assert hashlib.sha256(body.encode("utf-8")).hexdigest()[:16] == found.group(1)
        said = json.loads(body)
        assert set(said) == ({"ids", "collections", "sets"} if not code else {"catalogue"})
    # A wrong hash is not there.
    assert _get(served[0], f"{ASSET_ROUTE}catalogue.0000000000000000.json")[0] == 404


def test_a_first_visit_does_not_carry_the_shelf() -> None:
    """targum-internal#484: a desk page sent whole carried the shelf inside it, 303 kB
    gzipped of a 479 kB Library, every byte in front of the first card. It names the
    files, which `library.js` asks for once the page is up, and carries none of them."""
    whole = first_visit(library_page(TOKEN))
    files = shelf_files(whole)
    ids = json.loads(asset_files()[files[""]][0])["ids"]
    assert ids, "the fixture catalogue is on the shelf"
    for one in ids[:20]:
        assert json.dumps(one) not in whole, f"{one} rides in the page"
    assert "window.TARGUM_CATALOGUE = " not in whole


def test_each_language_file_is_its_rows_in_the_catalogues_order() -> None:
    """Hebrew's file is Hebrew's rows and the Aramaic door's, each with its place, so the
    page asks for one language and still sorts as the whole catalogue did."""
    files = shelf_files(library_page(TOKEN))
    ids = json.loads(asset_files()[files[""]][0])["ids"]
    merged: dict[str, dict] = {}
    for code, address in files.items():
        if not code:
            continue
        rows = json.loads(asset_files()[address][0])["catalogue"]
        places = [row["place"] for row in rows]
        assert places == sorted(places), code
        for row in rows:
            languages = {lang.split("-")[0] for lang in (row.get("languages") or [row["language"]])}
            assert code in languages or (code == "he" and "arc" in languages), (code, row["id"])
            assert ids[row["place"] - 1] == row["id"]
            merged[row["id"]] = row
    assert sorted(merged, key=lambda one: merged[one]["place"]) == ids, "every row, once"


def test_a_different_shelf_is_a_different_file(monkeypatch: pytest.MonkeyPatch) -> None:
    from targum import catalogue as catalogue_module

    first = shelf_files(library_page(TOKEN))[""]
    real = catalogue_module.everything
    monkeypatch.setattr(catalogue_module, "everything", lambda: list(real())[:1])
    second = shelf_files(library_page(TOKEN))[""]
    assert first != second
