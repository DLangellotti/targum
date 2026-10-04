"""The week's sheet as a download, set on the box (targum-internal#415).

The corpus build keeps what the sheet is set from beside each reader, because the box
has no books to cut it from again; the server sets it when somebody presses Download,
keeps the plain one, and never keeps one with a reader's words on it.
"""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from test_parasha_page import built  # noqa: F401  (a fixture)
from test_print import _kept, _looked, _words

from targum.errors import TargumError
from targum.mail import ConsoleMailer
from targum.parasha import calendar as cal
from targum.parasha import sheet
from targum.parasha.models import Index
from targum.render import printed
from targum.serve import SESSION_COOKIE, Handler, Library

SLUG = "nitzavim-vayeilech"


@pytest.fixture
def pressed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    """Every page handed to the press, which writes a stand-in PDF rather than setting
    one: what is on the sheet is decided before Pango, and is tested there."""
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    pages: list[str] = []

    def press(html: str, out: Path, seconds: float) -> Path:
        pages.append(html)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"%PDF-1.7 stand-in")
        return out

    monkeypatch.setattr(printed, "write_pdf_within", press)
    return pages


@pytest.fixture
def serving(tmp_path: Path, built: Index) -> Iterator[tuple[int, str]]:  # noqa: F811
    """The server over the built corpus, and a session for a reader who looked words up
    in the week the clock is pinned to."""
    store, person = _kept(tmp_path)
    _looked(store, person)
    signed = store.finish_sign_in(store.start_sign_in("r@example.com"))
    assert signed is not None
    out = tmp_path / "targum-out"
    out.mkdir(exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    server.RequestHandlerClass = type(
        "TestHandler",
        (Handler,),
        {
            "library": Library(out),
            "token": "test-key",
            "page": "<html>start</html>",
            "shelf": "<html>library</html>",
            "store": store,
            "mailer": ConsoleMailer(),
            "address": f"http://127.0.0.1:{port}",
        },
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port, signed[1]
    finally:
        server.shutdown()
        server.server_close()


def fetch(port: int, path: str, session: str = "") -> tuple[int, dict[str, str], bytes]:
    conn = HTTPConnection("127.0.0.1", port)
    headers = {"Cookie": f"{SESSION_COOKIE}={session}"} if session else {}
    conn.request("GET", path, headers=headers)
    answer = conn.getresponse()
    body = answer.read()
    conn.close()
    return answer.status, {k.lower(): v for k, v in answer.getheaders()}, body


# -- what the build keeps -----------------------------------------------------


def test_the_build_keeps_the_sheets_sources_beside_each_reader(built: Index) -> None:  # noqa: F811
    read = cal.root() / "read"
    portion, cited = sheet.kept(read / SLUG)
    assert portion.segmented.segments and portion.vocalization is not None
    assert {t.target_language for t in portion.translations} == {"en"}
    # The words a reader's own are set beside, without the annotation they came from.
    assert cited["en"]["אתם"] == ("אתם", "you")
    assert not (read / SLUG / "print" / "annotation.json").exists()
    haftarah = built.haftarot[built.portions[SLUG].haftarah]
    assert sheet.kept(read / haftarah.folder)[0].document.source.endswith("Isaiah 61:10-63:9")


def test_a_corpus_built_before_the_sheet_says_it_is_not_ready(built: Index) -> None:  # noqa: F811
    import shutil

    shutil.rmtree(cal.root() / "read" / SLUG / "print")
    with pytest.raises(sheet.NotReady):
        sheet.kept(cal.root() / "read" / SLUG)


# -- the download -------------------------------------------------------------


def test_signed_out_it_is_the_sheet_without_a_list_and_it_is_set_once(
    serving: tuple[int, str], pressed: list[str]
) -> None:
    port, _ = serving
    status, headers, body = fetch(port, f"/parasha/{SLUG}.pdf")
    assert status == 200 and body.startswith(b"%PDF")
    assert headers["content-type"] == "application/pdf"
    assert headers["content-disposition"] == f'attachment; filename="{SLUG}.pdf"'
    assert headers["cache-control"] == "no-store"
    html = pressed[0]
    # This week's: the portion, the week's haftarah and the Hebrew date.
    assert "Deuteronomy 29 verse 9" in html and "Isaiah 61:10-63:9" in html
    assert '<aside class="words week">' not in html
    # Nobody's words on it, so the second press is the first one's file.
    assert fetch(port, f"/parasha/{SLUG}.pdf")[0] == 200
    assert len(pressed) == 1


def test_a_reader_signed_in_gets_their_words_and_they_are_kept_nowhere(
    serving: tuple[int, str], pressed: list[str], tmp_path: Path
) -> None:
    port, session = serving
    status, _, body = fetch(port, f"/parasha/{SLUG}.pdf", session)
    assert status == 200 and body.startswith(b"%PDF")
    listed = pressed[0].partition('<aside class="words week">')[2]
    assert "Words you looked up this week" in listed
    # The same list the command line gives, set beside the forms the box kept.
    assert _words(listed) == [("שלום", "peace"), ("אתם", "you"), ("אנון", "they")]
    fetch(port, f"/parasha/{SLUG}.pdf", session)
    assert len(pressed) == 2, "set again each time"
    assert not list((tmp_path / "cache" / "sheets").glob("*.pdf"))


def test_a_portion_nobody_built_is_not_found(serving: tuple[int, str], pressed: list[str]) -> None:
    port, _ = serving
    assert fetch(port, "/parasha/no-such-portion.pdf")[0] == 404
    assert not pressed


def test_a_sheet_that_cannot_be_set_is_one_sentence(
    serving: tuple[int, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))

    def refuse(html: str, out: Path, seconds: float) -> Path:
        raise TargumError("Printing needs WeasyPrint and Pango, and this machine has not got them.")

    monkeypatch.setattr(printed, "write_pdf_within", refuse)
    port, _ = serving
    status, headers, body = fetch(port, f"/parasha/{SLUG}.pdf")
    assert status == 503 and headers["content-type"].startswith("text/plain")
    # The reader's sentence, not the operator's.
    assert body.decode() == "The PDF can't be made right now. Try again in a minute."


def test_the_portions_page_offers_the_download(serving: tuple[int, str]) -> None:
    port, _ = serving
    page = fetch(port, "/parasha")[2].decode()
    assert f'href="/parasha/{SLUG}.pdf"' in page and "Download PDF" in page
    russian = fetch(port, "/parasha?lang=ru")[2].decode()
    assert f'href="/parasha/{SLUG}.pdf?lang=ru"' in russian


def test_the_reader_offers_it_in_its_menu_on_a_portion_only(built: Index) -> None:  # noqa: F811
    """Hidden in the file, and shown by the script where the folder is a portion's."""
    folder = cal.root() / "read" / SLUG / "reader"
    page = next(iter(sorted(folder.glob("sec-*.html"))), folder / "index.html")
    reader = page.read_text(encoding="utf-8")
    assert '<div class="group to-sheet" id="to-sheet" hidden>' in reader
    assert "/^\\/parasha\\/read\\/([a-z0-9-]+)\\/reader\\//" in reader
    assert 'indexOf("haftarah-") === 0' in reader


# -- the press ----------------------------------------------------------------


def test_a_sheet_that_runs_long_is_stopped_in_a_sentence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def slow(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="targum", timeout=1)

    monkeypatch.setattr(subprocess, "run", slow)
    with pytest.raises(TargumError, match="took longer than 1 seconds"):
        printed.write_pdf_within("<p>x</p>", tmp_path / "x.pdf", 1)
    assert not (tmp_path / "x.pdf").exists()


def test_the_press_sets_a_real_page_in_a_process_of_its_own(tmp_path: Path) -> None:
    printed._find_pango()
    try:
        import weasyprint  # noqa: F401
    except (ImportError, OSError):
        pytest.skip("WeasyPrint or Pango is not installed")
    out = printed.write_pdf_within("<p lang='he'>שָׁלוֹם</p>", tmp_path / "x.pdf", 60)
    assert out.read_bytes().startswith(b"%PDF")
