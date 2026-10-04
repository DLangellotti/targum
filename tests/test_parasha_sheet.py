"""The week's sheet as a download, set on the box (targum-internal#415).

The corpus build keeps what the sheet is set from beside each reader, because the box
has no books to cut it from again; the server sets it when somebody presses Download,
keeps the plain one, and never keeps one with a reader's words on it.
"""

from __future__ import annotations

import re
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
from targum.vocalize import strip_nikkud

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
    # And the words it marks, slimmed: where each stands, how rare, what it is filed
    # under, and the meanings cut to the words the text carries.
    assert portion.annotation is not None and portion.annotation.tokens
    token = next(iter(portion.annotation.tokens.values()))[0]
    assert token.lemma == "אתם" and token.ipa is None
    assert portion.glossaries["en"].entries == {"אתם": "you"}
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


def test_the_portions_page_offers_the_download_with_its_choices(serving: tuple[int, str]) -> None:
    port, _ = serving
    page = fetch(port, "/parasha")[2].decode()
    form = page.partition('<form class="sheet-choices"')[2].partition("</form>")[0]
    assert f'action="/parasha/{SLUG}.pdf"' in form and "Download PDF" in form
    # The reader's defaults, ticked: their language, Onkelos and Rashi, the vowels, the
    # te'amim, the meanings and the haftarah; Rashi in English offered and not ticked
    # (targum-internal#414).
    assert '<input type="checkbox" name="with" value="en" checked>' in form
    assert '<input type="checkbox" name="with" value="targum" checked>' in form
    assert '<input type="checkbox" name="with" value="rashi" checked>' in form
    assert '<input type="checkbox" name="with" value="rashi-en">' in form
    for name in ("vowels", "taamim", "gloss", "haftarah"):
        assert f'<input type="hidden" name="{name}" value="0">' in form
        assert f'<input type="checkbox" name="{name}" value="1" checked>' in form
    russian = fetch(port, "/parasha?lang=ru")[2].decode()
    form = russian.partition('<form class="sheet-choices"')[2].partition("</form>")[0]
    assert '<input type="hidden" name="lang" value="ru">' in form
    assert '<input type="checkbox" name="with" value="ru" checked>' in form


def test_the_reader_offers_it_in_its_menu_on_a_portion_only(built: Index) -> None:  # noqa: F811
    """Hidden in the file, and shown by the script where the folder is a portion's."""
    folder = cal.root() / "read" / SLUG / "reader"
    page = next(iter(sorted(folder.glob("sec-*.html"))), folder / "index.html")
    reader = page.read_text(encoding="utf-8")
    assert '<div class="group to-sheet" id="to-sheet" hidden>' in reader
    assert 'id="more-sheet-aliyah"' in reader
    assert "\\/parasha\\/read\\/([a-z0-9-]+)\\/reader\\/(?:sec-(\\d+)\\.html)?" in reader
    assert 'indexOf("haftarah-") === 0' in reader
    # The view goes with the link, in the names the box reads.
    for name in ('"with"', '"vowels"', '"taamim"', '"layout"', '"gloss"', '"aliyah"'):
        assert f"[{name}," in reader or f"push([{name}" in reader


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


# -- the view -----------------------------------------------------------------


def test_a_view_is_read_off_the_link() -> None:
    plain = sheet.view_from({})
    assert plain == printed.View()
    asked = sheet.view_from(
        {
            "with": ["en,targum,rashi"],
            "vowels": ["1"],
            "taamim": ["0"],
            "layout": ["under"],
            "gloss": ["0"],
            "aliyah": ["3"],
            "size": ["letter"],
        }
    )
    assert asked.companions == ("en", "targum", "rashi")
    assert (asked.vowels, asked.taamim, asked.under, asked.gloss) == (True, False, True, False)
    # One aliyah is that aliyah alone, unless the haftarah is asked for as well.
    assert asked.aliyah == 3 and not asked.haftarah and asked.size == "letter"
    assert sheet.view_from({"aliyah": ["3"], "haftarah": ["1"]}).haftarah
    # `with=` empty is the text alone; a form's boxes come as several values, and a
    # ticked switch as its hidden 0 and then its 1.
    assert sheet.view_from({"with": [""]}).companions == ()
    assert sheet.view_from({"with": ["", "en", "targum"]}).companions == ("en", "targum")
    assert sheet.view_from({"vowels": ["0", "1"], "gloss": ["0"]}).vowels
    assert not sheet.view_from({"gloss": ["0"]}).gloss
    # Nonsense is passed over.
    assert sheet.view_from({"aliyah": ["x"], "layout": ["sideways"]}) == printed.View()


def _sheet(slug: str = SLUG, **view: object) -> str:
    """The page `make` hands the press for a view, signed out."""
    pages: list[str] = []

    def press(html: str, out: Path, seconds: float) -> Path:
        pages.append(html)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"%PDF-1.7 stand-in")
        return out

    original = printed.write_pdf_within
    printed.write_pdf_within = press  # type: ignore[assignment]
    try:
        sheet.make(slug, view=printed.View(**view))  # type: ignore[arg-type]
    finally:
        printed.write_pdf_within = original  # type: ignore[assignment]
    return pages[-1] if pages else ""


def _rare(read: Path) -> None:
    """Make every word the build kept beside the portion a rare one."""
    from targum.models import Annotation, read_artifact

    path = read / SLUG / "print" / "words.json"
    words = read_artifact(Annotation, path)
    assert words is not None
    for tokens in words.tokens.values():
        for token in tokens:
            token.band = 5
    words.write(path)


def test_the_sheet_prints_the_view_it_was_asked_for(
    built: Index,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    default = _sheet()
    # The reader's defaults: their language beside the verse, pointed, accented, and
    # the haftarah after.
    assert 'class="tr" lang="en"' in default and "Isaiah 61:10-63:9" in default
    assert '<body class="beside verses' in default
    alone = _sheet(companions=())
    assert 'class="tr"' not in alone and 'class="pair verse alone"' in alone
    under = _sheet(under=True, vowels=False)
    assert '<body class="under verses' in under
    lines = re.findall(r'<p class="src"[^>]*>(?:<span[^>]*>\d+</span>)?(.*?)</p>', under)
    assert lines and all(strip_nikkud(line)[0] == line for line in lines)
    one = _sheet(aliyah=1, haftarah=False)
    assert "Isaiah 61:10-63:9" not in one
    assert one.count('<section class="chapter">') == 1 < default.count('<section class="chapter">')
    # A companion the text has not got is passed over, and the default stands: the very
    # same page, so the press is not even asked — the kept one answers.
    assert _sheet(companions=("rashi",)) == ""
    import shutil

    shutil.rmtree(tmp_path / "cache")
    assert _sheet(companions=("rashi",)) == default


def test_signed_out_the_rarer_words_have_their_meaning_above_them(
    built: Index,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    # In the fixture every word is common, and nothing is marked.
    assert 'class="g"' not in _sheet()
    _rare(cal.root() / "read")
    html = _sheet()
    glossed = re.findall(r'<span class="gl" lang="en" dir="ltr">(.*?)</span>', html)
    # Once an aliyah, not at every verse; and nothing is lit for a stranger.
    assert glossed and set(glossed) == {"you"}
    assert 0 < len(glossed) < html.count('<div class="pair verse')
    assert 'class="lit' not in html
    assert "glossed" in html.partition("<body")[2].partition(">")[0]
    assert 'class="g"' not in _sheet(gloss=False)


def test_a_reader_signed_in_has_their_learning_words_lit(
    serving: tuple[int, str], pressed: list[str]
) -> None:
    port, session = serving
    fetch(port, f"/parasha/{SLUG}.pdf", session)
    html = pressed[-1]
    # אתם is a word they are learning, step 1: lit on every verse it stands in, and its
    # meaning above it the first time in each aliyah.
    assert html.count('<span class="lit s1">') > html.count('<span class="gl"') > 0
    assert '<span class="gl" lang="en" dir="ltr">you</span>' in html
    fetch(port, f"/parasha/{SLUG}.pdf?gloss=0", session)
    assert 'class="lit' not in pressed[-1] and 'class="gl"' not in pressed[-1]


def test_a_plain_sheet_is_kept_once_for_each_view(
    serving: tuple[int, str], pressed: list[str], tmp_path: Path
) -> None:
    port, _ = serving
    for _ in range(2):
        assert fetch(port, f"/parasha/{SLUG}.pdf")[0] == 200
        assert fetch(port, f"/parasha/{SLUG}.pdf?layout=under&taamim=0")[0] == 200
    assert len(pressed) == 2
    assert len(list((tmp_path / "cache" / "sheets").glob("*.pdf"))) == 2


def test_the_page_carries_the_imprint_and_the_address(
    built: Index,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    html = _sheet()
    assert '<header class="imprint" dir="ltr" lang="en">' in html
    assert '<span class="wordmark">targum</span>' in html
    assert f'"\\2002targum.page/parasha/{SLUG}"' in html
    assert "background: #fbf9f5" in html


# -- the marks ----------------------------------------------------------------


def test_a_meaning_fits_above_its_word() -> None:
    assert printed.gloss_of("(absolutely) to create; to choose") == "to create"
    assert printed.gloss_of("[marks the direct object]") == ""
    assert printed.gloss_of("heavens, sky") == "heavens"
    assert printed.gloss_of("something waited for eagerly") == "something…"


def test_a_mark_takes_the_whole_word_it_stands_in() -> None:
    from targum.models import Token

    text = "וְהָאָרֶץ הָיְתָה תֹהוּ׃"
    # The token is the noun without its prefix; the mark is drawn on the whole word.
    noun = Token(start=2, end=9, surface="הָאָרֶץ", lemma="ארץ", band=5)
    marked = printed._marked(
        text,
        text,
        [noun],
        printed.learning_marker({"ארץ": (2, "land")}),
        None,
        set(),
        direction="rtl",
        chrome="en",
    )
    assert marked is not None
    assert '<span class="gw"><span class="lit s2">וְהָאָרֶץ</span></span>' in marked
    # And on the bare text the same token lands on the same word.
    bare = strip_nikkud(text)[0]
    again = printed._marked(
        text,
        bare,
        [noun],
        printed.learning_marker({"ארץ": (2, "land")}),
        None,
        set(),
        direction="rtl",
        chrome="en",
    )
    assert again is not None and '<span class="lit s2">והארץ</span>' in again


def test_rashi_prints_in_hebrew_and_english_in_the_view_the_reader_has(
    built: Index,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """targum-internal#414. The sheet's sources keep Rashi in Hebrew and in English as two
    files beside the English rather than one over it; `with=rashi` and `with=rashi-en`
    print each, named and with his comments apart; and with no `with=` the sheet is the
    reader's own default, Rashi in Hebrew on and Rashi in English off."""
    from targum.models import Translation, read_artifact

    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    folder = cal.root() / "read" / SLUG / "print" / "translations"
    english = read_artifact(Translation, folder / "en.json")
    assert english is not None
    sid = next(iter(english.segments))
    added = []
    for language, said in (("he", "פירוש ראשון\nפירוש שני"), ("en", "First comment")):
        rashi = english.model_copy(
            update={
                "name": "Rashi on Deuteronomy",
                "target_language": language,
                "segments": {key: (said if key == sid else "—") for key in english.segments},
            }
        )
        path = folder / f"{sheet._file_of(rashi)}.json"
        rashi.write(path)
        added.append(path)
    try:
        assert sorted(p.name for p in folder.glob("*.json")) == [
            "en.json",
            "rashi-en.json",
            "rashi-he.json",
        ]
        both = _sheet(companions=("en", "rashi", "rashi-en"))
        assert '<div class="note" lang="he" dir="rtl"><span class="cmp-name"' in both
        assert ">Rashi</span>" in both and ">Rashi · English</span>" in both
        assert "First comment" in both and "פירוש ראשון" in both
        # Only the verse he comments on carries him: an unremarked verse prints no dash.
        assert both.count(">Rashi</span>") == 1
        default = _sheet()
        assert ">Rashi</span>" in default and ">Rashi · English</span>" not in default
        assert 'class="tr" lang="en"' in default
    finally:
        for path in added:
            path.unlink()


def _laid_out(
    html: str,
) -> tuple[list[float], list[float], list[tuple[int, float, float, float, float]]]:
    """The heights of the source's own lines, bare and glossed, and every meaning's box,
    as WeasyPrint lays the page out."""
    printed._find_pango()
    try:
        from weasyprint import HTML
    except (ImportError, OSError):
        pytest.skip("WeasyPrint or Pango is not installed")
    bare: list[float] = []
    glossed: list[float] = []
    meanings: list[tuple[int, float, float, float, float]] = []

    def classes(box: object) -> str:
        element = getattr(box, "element", None)
        return (element.get("class") or "") if element is not None else ""

    def walk(box: object, page: int) -> None:
        kind = type(box).__name__
        if (
            kind == "BlockBox"
            and getattr(box, "element_tag", "") == "p"
            and "src" in classes(box).split()
        ):
            for line in box.children:  # type: ignore[attr-defined]
                if type(line).__name__ != "LineBox":
                    continue
                has = any(classes(one) == "gl" for one in line.descendants())
                (glossed if has else bare).append(round(line.height, 2))
        if kind == "BlockBox" and classes(box) == "gl":
            meanings.append((page, box.position_x, box.position_y, box.width, box.height))  # type: ignore[attr-defined]
        for child in getattr(box, "children", None) or []:
            walk(child, page)

    for number, page in enumerate(HTML(string=html).render().pages):
        walk(page._page_box, number)
    return bare, glossed, meanings


def test_meanings_never_overlap_and_every_line_is_one_height(
    built: Index,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Genesis 1:2 printed "a vacuity" over "chaos", and a glossed line stood taller than
    the lines around it (targum-internal#415, 2026-10-05). With meanings on, every line of
    the text is one height, and no meaning reaches into its neighbour; with them off, the
    page keeps the reader's leading."""
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    _rare(cal.root() / "read")
    # Every word rare, and each verse's meanings set side by side: the closest they come.
    bare, glossed, meanings = _laid_out(_sheet(aliyah=1, haftarah=False))
    assert glossed and bare, "lines with a meaning and lines without"
    assert set(glossed) == set(bare) and len(set(bare)) == 1, (set(bare), set(glossed))
    for index, one in enumerate(meanings):
        for other in meanings[index + 1 :]:
            same_line = one[0] == other[0] and abs(one[2] - other[2]) < 1
            assert not (
                same_line and one[1] < other[1] + other[3] and other[1] < one[1] + one[3]
            ), "two meanings overlap"
    plain, _, none = _laid_out(_sheet(aliyah=1, haftarah=False, gloss=False))
    assert not none and max(plain) < min(bare), "without meanings, the reader's leading"


def test_two_meanings_side_by_side_do_not_touch() -> None:
    """The case Genesis 1:2 printed wrong: short words next to each other, each with a
    meaning wider than itself."""
    from targum.models import Token

    text = "תֹהוּ וָבֹהוּ וְחֹשֶׁךְ עַל תֹהוּ וָבֹהוּ וְחֹשֶׁךְ"
    words = text.split(" ")
    starts = [sum(len(word) + 1 for word in words[:n]) for n in range(len(words))]
    tokens = [
        Token(start=start, end=start + len(word), surface=word, lemma=f"w{n}", band=5)
        for n, (start, word) in enumerate(zip(starts, words, strict=True))
    ]
    meanings = {f"w{n}": "a long meaning here" for n in range(len(words))}

    def mark(token: Token, glossary: object) -> printed.Mark:
        return printed.Mark(status=1, meaning=meanings[token.lemma])

    line = printed.Line(
        kind="verse",
        level=2,
        source=text,
        verse="Genesis 1:2",
        source_html=printed._marked(
            text, text, tokens, mark, None, set(), direction="rtl", chrome="en"
        ),
    )
    part = printed.Part(
        title="בראשית",
        english="Bereshit",
        chapters=[printed.Chapter(title="", lines=[line] * 3)],
        source_language="he",
        target_language="en",
    )
    html = printed._page(
        [part],
        title="בראשית",
        english="Bereshit",
        chrome="en",
        accented=False,
        under=False,
        size="a4",
    )
    _, glossed, boxes = _laid_out(html)
    assert len(boxes) >= 3 * len(words) and len(set(glossed)) == 1
    for index, one in enumerate(boxes):
        for other in boxes[index + 1 :]:
            if one[0] == other[0] and abs(one[2] - other[2]) < 1:
                assert one[1] + one[3] <= other[1] + 0.01 or other[1] + other[3] <= one[1] + 0.01


def test_rashi_keeps_his_own_leading_and_carries_no_meanings(
    built: Index,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The room a meaning needs is the verse's alone: Rashi's rows under it are set at their
    own height whether the verse's words carry meanings or not, and his words carry none
    (targum-internal#414, #415)."""
    from targum.models import Translation, read_artifact

    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    folder = cal.root() / "read" / SLUG / "print" / "translations"
    english = read_artifact(Translation, folder / "en.json")
    assert english is not None
    sid = next(iter(english.segments))
    rashi = english.model_copy(
        update={
            "name": "Rashi on Deuteronomy",
            "target_language": "he",
            "segments": {
                key: ("פירוש ראשון על הפסוק הזה " * 12 if key == sid else "—")
                for key in english.segments
            },
        }
    )
    rashi.write(folder / f"{sheet._file_of(rashi)}.json")
    _rare(cal.root() / "read")

    def notes(html: str) -> list[float]:
        _laid_out(html)  # skips without Pango
        from weasyprint import HTML

        heights: list[float] = []

        def walk(box: object) -> None:
            element = getattr(box, "element", None)
            classes = (element.get("class") or "") if element is not None else ""
            if type(box).__name__ == "BlockBox" and classes == "note":
                heights.extend(
                    round(line.height, 2)
                    for line in box.children  # type: ignore[attr-defined]
                    if type(line).__name__ == "LineBox"
                )
            for child in getattr(box, "children", None) or []:
                walk(child)

        for page in HTML(string=html).render().pages:
            walk(page._page_box)
        return heights

    glossed = _sheet(companions=("en", "rashi"), aliyah=1, haftarah=False)
    note = glossed.partition('<div class="note"')[2].partition("</div>")[0]
    assert note and 'class="g"' not in note and 'class="lit' not in note
    plain = _sheet(companions=("en", "rashi"), aliyah=1, haftarah=False, gloss=False)
    with_meanings, without = notes(glossed), notes(plain)
    assert len(with_meanings) > 1 and with_meanings == without
    _, verse_lines, _ = _laid_out(glossed)
    assert max(with_meanings) < min(verse_lines), "not the glossed verse's tall line"
