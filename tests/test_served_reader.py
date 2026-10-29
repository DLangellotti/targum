"""A served reader loads its files once (design.md §12, 2026-10-29, targum-internal#559).

A reader on disk is whole and stays whole: it opens off a disk, a save keeps it for
offline, and it fetches nothing. Opened on the site, the browser is handed the same page
with today's stylesheets, scripts and faces named by address and its recordings as files,
and keeps them. These hold the two forms apart: the page named is the page whole once its
files are put back, a save still gets the whole one, and the worker never keeps a named
one as the copy for the plane.
"""

from __future__ import annotations

import base64
import re
from http.client import HTTPConnection
from pathlib import Path

import pytest
from test_offline import TOKEN, book, served  # noqa: F401 - `served` is a fixture

from targum.render.builder import (
    ASSETS,
    asset_files,
    asset_set,
    carried,
    first_visit,
    named_files,
    names_files,
    reader_files,
    served_reader,
)
from targum.serve import CLIP_ROUTE, KEPT_COOKIE, LINKED_HEADER, Handler, served_page

_BLOCK = re.compile(r"<(script|style)\b([^>]*)>(.*?)</\1>", re.S)


def _same(one: str, other: str) -> bool:
    # A reader's one `<style>` of several sheets comes back as one `<style>` a sheet.
    return one.replace("</style><style>", "") == other.replace("</style><style>", "")


def _big_blocks(html: str) -> list[str]:
    return [
        m.group(3)[:40]
        for m in _BLOCK.finditer(html)
        if len(m.group(3)) > 2000 and "application/json" not in m.group(2)
    ]


def test_a_served_reader_names_its_files_and_is_the_page_once_they_are_back(
    tmp_path: Path,
) -> None:
    reader = book(tmp_path / "a-book")
    for page in sorted(reader.glob("*.html")):
        whole = page.read_text(encoding="utf-8")
        named = served_reader(whole)
        assert names_files(named), page.name
        assert _big_blocks(named) == [], f"{page.name}: nothing of today's files left inline"
        assert len(named) < len(whole) / 5, page.name
        assert set(named_files(named)) <= set(asset_files()), page.name
        assert _same(carried(named), whole), f"{page.name}: put back, it is the page"


def test_a_block_that_is_not_today_s_file_stays_where_it_is(tmp_path: Path) -> None:
    """A reader built before a file changed still works: its old copy stays inline."""
    reader = book(tmp_path / "a-book")
    whole = (reader / "sec-0001.html").read_text(encoding="utf-8")
    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert script
    stale = whole.replace("use strict", "use  strict", 1)
    named = served_reader(stale)
    assert "use  strict" in named, "the changed block is carried as it was"
    assert names_files(named), "and every block that is today's is still named"


def test_every_file_a_served_reader_names_is_warmed_by_a_desk_page(tmp_path: Path) -> None:
    reader = book(tmp_path / "a-book")
    named = set(named_files(served_reader((reader / "sec-0001.html").read_text())))
    assert named <= set(reader_files()), named - set(reader_files())
    sheet = reader_files()[0]
    desk = first_visit(
        f'<html><head><link rel="stylesheet" href="{sheet}"></head><body></body></html>'
    )
    for address in reader_files():
        assert address in desk, address


def _get(
    port: int, path: str, *, navigate: bool, kept: bool = True
) -> tuple[int, dict[str, str], bytes]:
    headers = {"Accept": "text/html"} if navigate else {"Accept": "*/*"}
    headers["Sec-Fetch-Mode"] = "navigate" if navigate else "cors"
    if kept:
        headers["Cookie"] = f"{KEPT_COOKIE}={asset_set()}"
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request("GET", path, headers=headers)
    answer = connection.getresponse()
    body = answer.read()
    connection.close()
    return answer.status, {k.lower(): v for k, v in answer.getheaders()}, body


def _policy(headers: dict[str, str]) -> dict[str, list[str]]:
    return {
        part.split()[0]: part.split()[1:]
        for part in headers["content-security-policy"].split(";")
        if part.strip()
    }


def test_opened_it_is_named_saved_it_is_whole(served: tuple[int, Path]) -> None:  # noqa: F811
    port, out = served
    reader = book(out / "local" / "book-he")
    on_disk = (reader / "sec-0001.html").read_bytes()
    address = f"/reader/book-he/reader/sec-0001.html?k={TOKEN}"

    status, head, body = _get(port, address, navigate=True)
    assert status == 200
    assert names_files(body) and len(body) < len(on_disk) / 5
    assert head[LINKED_HEADER.lower()] == "1"
    policy = _policy(head)
    assert policy["script-src"][0] == "'self'" and policy["style-src"][0] == "'self'"
    assert "'unsafe-inline'" not in head["content-security-policy"]
    assert "frame-ancestors 'self'" in head["content-security-policy"], "framed as before"

    # A save for offline, or any script, asks without navigating: the page as on disk.
    status, head, body = _get(port, address, navigate=False)
    assert status == 200 and body == on_disk
    assert LINKED_HEADER.lower() not in head

    # A browser that has not kept the files is sent it whole, and fetches them after.
    status, head, body = _get(port, address, navigate=True, kept=False)
    assert status == 200 and b"data-kept" in body
    assert head[LINKED_HEADER.lower()] == "1", "and the worker keeps that one neither"


def test_a_recording_rides_as_a_file_of_its_own(
    served: tuple[int, Path],  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    port, out = served
    reader = book(out / "local" / "book-he")
    sound = b"ID3" + bytes(range(256)) * 4
    uri = "data:audio/mpeg;base64," + base64.b64encode(sound).decode("ascii")
    page = reader / "sec-0002.html"
    page.write_text(
        page.read_text(encoding="utf-8").replace(
            "</body>", f'<script type="application/json" id="clip">"{uri}"</script></body>'
        ),
        encoding="utf-8",
    )
    status, _, body = _get(port, f"/reader/book-he/reader/sec-0002.html?k={TOKEN}", navigate=True)
    assert status == 200 and b"data:audio" not in body
    clip = re.search(rb'"(' + CLIP_ROUTE.encode() + rb'[0-9a-f]{32}\.mp3)"', body)
    assert clip, "the recording is named"
    status, head, got = _get(port, f"{clip.group(1).decode()}?k={TOKEN}", navigate=False)
    assert status == 200 and got == sound
    assert head["content-type"] == "audio/mpeg"
    assert head["cache-control"] == Handler.ASSET_CACHE
    for wrong in ("../x.mp3", "abc.mp3", "0" * 32 + ".exe", "0" * 32 + ".mp3"):
        assert _get(port, f"{CLIP_ROUTE}{wrong}?k={TOKEN}", navigate=False)[0] == 404, wrong
    # Saved, it keeps its recording inside it.
    _, _, whole = _get(port, f"/reader/book-he/reader/sec-0002.html?k={TOKEN}", navigate=False)
    assert uri.encode() in whole


def test_a_page_is_worked_out_once_while_it_stays_as_it_is(tmp_path: Path) -> None:
    reader = book(tmp_path / "a-book")
    page = reader / "sec-0001.html"
    first = served_page(page, page.read_bytes())
    assert served_page(page, page.read_bytes()) is first
    page.write_text(page.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert served_page(page, page.read_bytes()) is not first


def test_the_worker_never_keeps_a_named_page_as_the_copy_for_the_plane() -> None:
    worker = (ASSETS / "sw.js").read_text(encoding="utf-8")
    opening = worker[worker.index("function opening(") : worker.index("function kept(")]
    assert 'var linked = answer && answer.headers.get("x-targum-linked");' in opening
    assert "saved[key] && !linked" in opening
    assert LINKED_HEADER.lower() == "x-targum-linked"
