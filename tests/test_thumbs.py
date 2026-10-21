"""A thumbnail for every text (targum-internal#429): its own picture, or a drawn tile."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from targum import thumbs

PIL = pytest.importorskip("PIL")


def png(width: int = 40, height: int = 60) -> bytes:
    from PIL import Image

    kept = io.BytesIO()
    Image.new("RGB", (width, height), (90, 115, 64)).save(kept, format="PNG")
    return kept.getvalue()


def test_a_tile_is_coloured_by_what_the_text_is() -> None:
    assert thumbs.tone("article") == "#1f6f6b"
    assert thumbs.tone("talk") == "#b4553f"
    assert thumbs.tone("dialogue") == thumbs.tone("liturgy") == "#6b5a8e"
    assert thumbs.tone("prose", "rabbinic") == "#6b5a8e", "the Mishnah is a set"
    assert thumbs.tone("novel") == thumbs.tone("") == "#6b645c"


def test_every_tile_colour_is_in_the_palette() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "brand", Path(__file__).with_name("test_brand.py")
    )
    assert spec is not None and spec.loader is not None
    brand = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(brand)
    PALETTE = brand.PALETTE

    for colour in [*thumbs.TONES.values(), thumbs.ON_TONE]:
        assert colour in PALETTE, colour


def test_a_tile_draws_the_first_letter_and_nothing_else() -> None:
    assert thumbs.letter("«בְּרֵאשִׁית»") == "ב"
    assert thumbs.letter("(Муму)") == "М"
    assert thumbs.letter("la parure") == "L"
    assert thumbs.letter("…") == "?"
    drawing = thumbs.drawn("<script>", "article", language="en")
    assert "<script" not in drawing.replace("<svg", "")
    assert ">S</text>" in drawing and 'fill="#1f6f6b"' in drawing
    assert "http" not in drawing.replace("http://www.w3.org/2000/svg", ""), "fetches nothing"


def test_a_page_names_its_own_picture() -> None:
    page = '<html><head><meta property="og:image" content="/img/lead.jpg"></head></html>'
    assert thumbs.page_image(page, "https://example.org/a/b") == "https://example.org/img/lead.jpg"
    card = '<meta name="twitter:image" content="https://cdn.example.org/x.png">'
    assert thumbs.page_image(card, "https://example.org/") == "https://cdn.example.org/x.png"
    hostile = '<meta property="og:image" content="javascript:alert(1)">'
    assert thumbs.page_image(hostile, "https://example.org/") == ""
    assert thumbs.page_image("<p>no picture</p>", "https://example.org/") == ""


def epub(tmp_path: Path, opf_items: str, meta: str = "") -> Path:
    path = tmp_path / "book.epub"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "META-INF/container.xml",
            '<container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles>'
            "</container>",
        )
        archive.writestr(
            "OEBPS/content.opf",
            f"<package><metadata>{meta}</metadata><manifest>{opf_items}</manifest></package>",
        )
        archive.writestr("OEBPS/images/front.png", png())
    return path


def test_an_epub_gives_the_cover_it_declares(tmp_path: Path) -> None:
    three = epub(
        tmp_path,
        '<item id="c" href="images/front.png" media-type="image/png" properties="cover-image"/>',
    )
    assert thumbs.epub_cover(three) == png()
    (tmp_path / "book.epub").unlink()
    two = epub(
        tmp_path,
        '<item id="pic" href="images/front.png" media-type="image/png"/>',
        '<meta name="cover" content="pic"/>',
    )
    assert thumbs.epub_cover(two) == png()
    (tmp_path / "book.epub").unlink()
    none = epub(tmp_path, '<item id="text" href="a.xhtml" media-type="application/xhtml+xml"/>')
    assert thumbs.epub_cover(none) is None


def test_only_a_picture_is_kept(tmp_path: Path) -> None:
    target = tmp_path / "reader" / thumbs.THUMB
    assert not thumbs.keep(b"<html>not a picture</html>", target)
    assert not target.exists()
    assert thumbs.keep(png(1200, 1800), target)
    from PIL import Image

    with Image.open(target) as kept:
        assert kept.format == "WEBP" and kept.width == 320


def test_an_upload_keeps_its_own_picture_beside_its_reader(tmp_path: Path) -> None:
    source = epub(
        tmp_path,
        '<item id="c" href="images/front.png" media-type="image/png" properties="cover-image"/>',
    )
    folder = tmp_path / "out" / "book-he"
    assert thumbs.capture(str(source), folder)
    assert (folder / thumbs.THUMB).is_file()
    # Once: a second build keeps what is there.
    assert thumbs.capture(str(source), folder)


def test_a_library_text_is_never_captured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Its picture is the batch's, chosen by licence: a publisher's picture captured on a
    build of a shared text would reach every reader of it."""
    from targum import catalogue

    monkeypatch.setattr(catalogue, "matching", lambda source: object())
    asked: list[str] = []
    monkeypatch.setattr(thumbs, "own_picture", lambda *a: asked.append("x") or png())
    assert not thumbs.capture("https://example.org/a", tmp_path / "shared" / "a-he")
    assert asked == []


def test_a_failing_picture_never_fails_the_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_: Any) -> bytes:
        raise RuntimeError("host said no")

    monkeypatch.setattr(thumbs, "own_picture", broken)
    assert not thumbs.capture("https://example.org/a", tmp_path / "a-he")


README = """\
Index # | Story title | Illustrator | License
------- | ----------- | ----------- | -------
0001 | [A very tall man](https://x/0001) | **C G** | [BY](https://creativecommons.org/licenses/by/3.0/)
0002 | [Look](https://x/0002) | **S C** | [BY-NC](https://creativecommons.org/licenses/by-nc/3.0/)
"""


def test_the_image_bank_is_read_for_each_storys_pictures() -> None:
    licences = thumbs.gsn_licences(README)
    assert licences == {"0001": "CC BY 3.0", "0002": "CC BY-NC 3.0"}
    assert thumbs.may_show("CC BY 3.0") and thumbs.may_show("Public Domain")
    assert not thumbs.may_show("CC BY-NC 3.0"), "NonCommercial pictures stay off the shelf"
    assert not thumbs.may_show("CC BY-ND 4.0") and not thumbs.may_show("")


def row(source: str, licence: str = "CC BY 3.0") -> Any:
    return SimpleNamespace(source=source, licence=licence)


def test_a_row_is_given_its_own_picture_only_where_its_licence_allows() -> None:
    def fetch(url: str) -> Any:
        assert "storyweaver" in url
        sizes = [
            {"width": 268, "url": "https://s/size1/a.jpg"},
            {"width": 428, "url": "https://s/size3/a.jpg"},
            {"width": 308, "url": "https://s/size2/a.jpg"},
        ]
        return SimpleNamespace(text=json.dumps({"data": {"coverImage": {"sizes": sizes}}}))

    gsn = thumbs.gsn_licences(README)
    video = thumbs.remote_picture(row("video:abc-123"), fetch, gsn)
    assert video == ("https://i.ytimg.com/vi/abc-123/mqdefault.jpg", "CC BY 3.0", "video poster")
    book = thumbs.remote_picture(row("storyweaver:257052", "CC BY 4.0"), fetch, gsn)
    assert book is not None and book[0] == "https://s/size3/a.jpg"
    story = thumbs.remote_picture(row("globalstorybooks:sbc/0001/ru"), fetch, gsn)
    assert story is not None and story[0].endswith("/0001/01.jpg")
    assert thumbs.remote_picture(row("globalstorybooks:sbc/0002/ru"), fetch, gsn) is None
    assert thumbs.remote_picture(row("video:abc", "CC BY-NC 4.0"), fetch, gsn) is None
    # A publisher's article: its picture is not the shelf's, whatever the article's terms.
    assert (
        thumbs.remote_picture(row("https://he.globalvoices.org/x", "CC BY 3.0"), fetch, gsn) is None
    )
    assert thumbs.remote_picture(row("sefaria:Genesis", "Public Domain"), fetch, gsn) is None


def test_an_uploads_reader_carries_its_own_picture_as_its_cover(tmp_path: Path) -> None:
    from targum.render.builder import own_cover_uri

    assert own_cover_uri(tmp_path) == "" and own_cover_uri(None) == ""
    assert thumbs.keep(png(), tmp_path / thumbs.THUMB)
    assert own_cover_uri(tmp_path).startswith("data:image/webp;base64,")


# -- slices 2 and 3: a row with no picture is named, and every picture says where from ----


def shelf(*ids: str) -> list[Any]:
    return [
        SimpleNamespace(id=name, source=f"test:{name}", licence="CC BY 4.0", language="he")
        for name in ids
    ]


def run_thumbs(out: Path, *more: str) -> str:
    from typer.testing import CliRunner

    from targum.cli import app

    result = CliRunner().invoke(
        app, ["thumbs", "--no-fetch", "--out", str(out), *more], env={"COLUMNS": "400"}
    )
    assert result.exit_code == 0, result.output
    return result.output


def test_a_row_filed_without_a_picture_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum import catalogue

    where = tmp_path / "thumbs"
    where.mkdir()
    (where / "drawn-one.webp").write_bytes(b"drawn")
    (where / "own-one.webp").write_bytes(b"poster")
    held = {"own-one": {"from": "video poster", "licence": "CC BY 4.0"}}
    (where / thumbs.SOURCES).write_text(json.dumps(held), encoding="utf-8")
    monkeypatch.setattr(
        catalogue, "CATALOGUE", shelf("drawn-one", "own-one", "scene-ru-filed-later")
    )

    said = run_thumbs(tmp_path, "--dry-run")

    lines = said.splitlines()
    assert "1 row without a picture" == lines[-1]
    assert "1 own · 1 drawn · 1 tile" == lines[-2]
    assert any(line.strip() == "scene-ru-filed-later" for line in lines)
    assert not any(line.strip() in ("drawn-one", "own-one") for line in lines)
    assert "1 drawn covers would be written into sources.json." in said
    assert json.loads((where / thumbs.SOURCES).read_text("utf-8")) == held, (
        "a dry run writes nothing"
    )


def test_every_picture_says_where_it_came_from(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os
    from datetime import date, datetime

    from targum import catalogue

    where = tmp_path / "thumbs"
    (where / "small").mkdir(parents=True)
    for name in ("genesis", "genesis-c002", "home1-notes", "own-one"):
        (where / f"{name}.webp").write_bytes(b"picture")
    (where / ".exodus.webp.part").write_bytes(b"half")
    (where / "small" / "genesis.webp").write_bytes(b"small")
    drawn_on = datetime(2026, 10, 8, 12).timestamp()
    os.utime(where / "genesis.webp", (drawn_on, drawn_on))
    poster = {"from": "video poster", "url": "https://i.ytimg.com/x", "licence": "CC BY 4.0"}
    (where / thumbs.SOURCES).write_text(json.dumps({"own-one": poster}), encoding="utf-8")
    monkeypatch.setattr(catalogue, "CATALOGUE", shelf("genesis", "own-one"))

    said = run_thumbs(tmp_path)

    sources = thumbs.read_sources(where)
    assert set(sources) == {"genesis", "genesis-c002", "home1-notes", "own-one"}
    assert sources["own-one"] == poster, "a picture's own line is kept as it was"
    assert sources["genesis"] == {
        "from": "drawn",
        "model": "openai/gpt-image-2",
        "date": "2026-10-08",
        "backfilled": date.today().isoformat(),
    }
    assert thumbs.unrecorded(where, sources) == []
    assert "3 drawn covers were written into sources.json." in said
    assert said.splitlines()[-2:] == ["1 own · 1 drawn · 0 tile", "0 rows without a picture"]

    # Run again, and nothing is left to write.
    before = (where / thumbs.SOURCES).read_bytes()
    assert "written into sources.json" not in run_thumbs(tmp_path)
    assert (where / thumbs.SOURCES).read_bytes() == before


def test_a_drawn_cover_adds_its_own_line(tmp_path: Path) -> None:
    thumbs.record(tmp_path, "a", thumbs.drawn_entry("openai/gpt-image-2", "2026-10-21"))
    thumbs.record(tmp_path, "b", thumbs.drawn_entry("openai/gpt-image-2", "2026-10-21"))

    said = thumbs.read_sources(tmp_path)
    assert said["a"] == {"from": "drawn", "model": "openai/gpt-image-2", "date": "2026-10-21"}
    assert set(said) == {"a", "b"}
    assert thumbs.origin(said["a"]) == thumbs.DRAWN
    assert thumbs.origin({"from": "book cover"}) == thumbs.OWN
    assert thumbs.origin(None) == thumbs.DRAWN


def test_a_deploy_carries_only_the_librarys_pictures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum import catalogue

    where = tmp_path / "thumbs"
    where.mkdir()
    for name in ("genesis", "genesis-c002", "p3-[115]-Yair-Lapid-he", "father-sergius"):
        (where / f"{name}.webp").write_bytes(b"picture")
    held = {
        "genesis": {"from": "drawn", "model": "m", "date": "2026-10-08"},
        "p3-[115]-Yair-Lapid-he": {"from": "drawn", "model": "m", "date": "2026-08-31"},
    }
    (where / thumbs.SOURCES).write_text(json.dumps(held), encoding="utf-8")
    monkeypatch.setattr(catalogue, "CATALOGUE", shelf("genesis"))
    carried = tmp_path / "carried"

    run_thumbs(tmp_path, "--for-box", str(carried))

    lines = thumbs.read_sources(carried)
    assert set(lines) == {"genesis", "genesis-c002"}, (
        "the library's lines, the chapter's backfilled"
    )
    assert (carried / "exclude").read_text(encoding="utf-8").splitlines() == [
        "/father-sergius.webp",
        "/p3-\\[115\\]-Yair-Lapid-he.webp",
    ]
    assert json.loads((where / thumbs.SOURCES).read_text("utf-8")) == held, "thumbs/ is only read"
