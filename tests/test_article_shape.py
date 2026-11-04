"""An article in the shape its page gives it (design.md §12, "A text keeps the shape its
edition gives it", 2026-11-04): its headline without the site's name, its dateline, and
its pictures with their captions — for articles imported from now on, never for one
already on a shelf (David: a caption is new text, and new text is bought).
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

import pytest

from targum import figures, promote
from targum.ingest import url
from targum.models import Block, BlockKind, Document, Picture, Translation
from targum.render import render
from targum.segment import HebrewSegmenter, segment_document

LEAD = "הפועל חולון היא אלופת ישראל בכדורסל, לאחר שניצחה במשחק צמוד את מכבי תל אביב."
SECOND = "המשחק התקיים בהיכל נוקיה, מגרשה הביתי של מכבי, מול קהל של אלפי אוהדים."
THIRD = "צביקה שרף, מאמן מכבי, אמר שהוא אשם בסל האחרון והודה שחולון שיחקה טוב יותר."

PAGE = f"""<html><head><title>הפועל חולון היא אלופת המדינה בכדורסל – ויקיחדשות</title>
<meta property="og:site_name" content="ויקיחדשות"></head><body>
<header><figure><img src="/logo.png" width="300">
<figcaption>ויקיחדשות</figcaption></figure></header>
<article>
<h1>הפועל חולון היא אלופת המדינה בכדורסל</h1>
<p>30 במאי 2008</p>
<figure><img src="//upload.example.org/stadium.jpg" width="500" height="243" alt="היכל">
<figcaption>היכל הספורט יד אליהו. חולון ניצחה במגרשה הביתי של יריבתה</figcaption></figure>
<p>{LEAD}</p>
<p>{SECOND}</p>
<figure><img src="https://upload.example.org/icon.png" width="60">
<figcaption>שתפו</figcaption></figure>
<figure><img src="https://upload.example.org/sharp.jpg" width="500" height="375">
<figcaption>דריק שארפ (ארכיון). הביע אופטימיות</figcaption></figure>
<p>{THIRD}</p>
</article></body></html>"""


def test_a_title_loses_the_sites_name_and_nothing_else() -> None:
    assert url.without_site("כותרת – ויקיחדשות", "ויקיחדשות") == "כותרת"
    assert url.without_site("Headline | The Site", "The Site") == "Headline"
    assert url.without_site("ויקיחדשות", "ויקיחדשות") == "ויקיחדשות"
    assert url.without_site("כותרת – משהו אחר", "ויקיחדשות") == "כותרת – משהו אחר"
    assert url.without_site("כותרת", None) == "כותרת"
    # Where the page names no site, what follows its own headline is the site.
    assert url.without_site("כותרת – ויקיחדשות", None, "כותרת") == "כותרת"
    assert url.without_site("כותרת – ויקיחדשות", None, "אחרת") == "כותרת – ויקיחדשות"


@pytest.mark.parametrize(
    "said", ["30 במאי 2008", "4 November 2026", "November 4, 2026", "4 ноября 2026"]
)
def test_a_date_under_the_headline_is_its_dateline(said: str) -> None:
    shaped = url.with_dateline([(BlockKind.heading, 1, "כותרת"), (BlockKind.paragraph, None, said)])
    assert shaped[1][0] is BlockKind.byline


def test_a_paragraph_that_only_starts_with_a_date_is_a_paragraph() -> None:
    text = "30 במאי 2008 היה יום גדול לכדורסל הישראלי"
    shaped = url.with_dateline([(BlockKind.heading, 1, "כותרת"), (BlockKind.paragraph, None, text)])
    assert shaped[1][0] is BlockKind.paragraph


def test_a_pictures_caption_stands_before_the_paragraph_after_it() -> None:
    found = url.figures_on(PAGE, "https://he.wikinews.example/wiki/a")
    # The site's own mark is chrome, and an icon is no picture.
    assert [f.caption for f in found] == [
        "היכל הספורט יד אליהו. חולון ניצחה במגרשה הביתי של יריבתה",
        "דריק שארפ (ארכיון). הביע אופטימיות",
    ]
    assert found[0].picture.src == "https://upload.example.org/stadium.jpg"
    paragraphs = [
        (BlockKind.heading, 1, "הפועל חולון היא אלופת המדינה בכדורסל"),
        (BlockKind.byline, None, "30 במאי 2008"),
        (BlockKind.paragraph, None, LEAD),
        (BlockKind.paragraph, None, SECOND),
        (BlockKind.paragraph, None, THIRD),
    ]
    shaped, pictures = url.with_figures(paragraphs, found)
    assert [text for _, _, text in shaped] == [
        paragraphs[0][2],
        paragraphs[1][2],
        found[0].caption,
        LEAD,
        SECOND,
        found[1].caption,
        THIRD,
    ]
    assert set(pictures) == {2, 5}


def test_an_imported_article_has_its_dateline_and_its_captions(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        url, "page", lambda source: url.Fetched(text=PAGE, content_type="text/html")
    )
    document = url.UrlIngester().load("https://he.wikinews.example/wiki/a")
    assert document.title == "הפועל חולון היא אלופת המדינה בכדורסל"
    kinds = [(b.kind, b.text) for b in document.blocks]
    assert (BlockKind.byline, "30 במאי 2008") in kinds
    captioned = [b for b in document.blocks if b.picture is not None]
    assert [b.text for b in captioned] == [
        "היכל הספורט יד אליהו. חולון ניצחה במגרשה הביתי של יריבתה",
        "דריק שארפ (ארכיון). הביע אופטימיות",
    ]
    # The picture is beside the words: the text every stage reads is the words alone.
    assert "upload.example.org" not in document.body()


def test_the_ingester_keeps_its_name_so_no_shelved_article_is_read_again() -> None:
    """Under a new name a shelved article read again would come back with its captions,
    which are words to buy. Under the same name the stored text wins (`Build.ingest`)."""
    assert url.UrlIngester.name == "url/6"


def _png(width: int, height: int) -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (width, height), (200, 120, 40)).save(out, format="PNG")
    return out.getvalue()


def _with_picture(document_blocks: list[Block]) -> Document:
    document = Document(
        source="https://news.example/a", title="כותרת", language="he", blocks=document_blocks
    )
    document.content_hash = document.recompute_hash()
    return document


def test_a_picture_is_kept_beside_the_reader_once(tmp_path: Path, monkeypatch: Any) -> None:
    fetched: list[str] = []

    def fake_download(address: str, into: Path, most: int) -> None:
        fetched.append(address)
        into.write_bytes(_png(1600, 800))

    monkeypatch.setattr(url, "download", fake_download)
    document = _with_picture(
        [
            Block(id="b0000", kind=BlockKind.heading, level=1, text="כותרת"),
            Block(id="b0001", text="כיתוב", picture=Picture(src="https://x.example/p.jpg")),
        ]
    )
    assert figures.keep(document, tmp_path) == 1
    kept = tmp_path / figures.kept_path("b0001")
    from PIL import Image

    with Image.open(kept) as image:
        assert image.format == "WEBP" and max(image.size) <= 1280
    figures.keep(document, tmp_path)
    assert fetched == ["https://x.example/p.jpg"], "a kept picture is not fetched again"


def test_a_picture_that_will_not_come_leaves_its_caption(tmp_path: Path, monkeypatch: Any) -> None:
    def refused(address: str, into: Path, most: int) -> None:
        raise OSError("refused")

    monkeypatch.setattr(url, "download", refused)
    document = _with_picture(
        [Block(id="b0001", text="כיתוב", picture=Picture(src="https://x.example/p.jpg"))]
    )
    assert figures.keep(document, tmp_path) == 0


def test_the_page_carries_the_picture_over_its_caption(tmp_path: Path) -> None:
    folder = tmp_path / "targum"
    (folder / "figures").mkdir(parents=True)
    from PIL import Image

    Image.new("RGB", (640, 320)).save(folder / figures.kept_path("b0001"), format="WEBP")
    document = _with_picture(
        [
            Block(id="b0000", kind=BlockKind.heading, level=1, text="כותרת"),
            Block(id="b0001", text="כיתוב התמונה", picture=Picture(src="https://x.example/p.jpg")),
            Block(id="b0002", text="פסקה אחרי התמונה."),
        ]
    )
    segmented = segment_document(document, HebrewSegmenter())
    english = Translation(
        name="English",
        document_hash=segmented.document_hash,
        source_language="he",
        target_language="en",
        provider="test",
        segments={s.id: "English." for s in segmented.segments},
    )
    html = render(document, segmented, [english], folder / "reader", folder=folder)[0].read_text(
        encoding="utf-8"
    )
    caption = next(s for s in segmented.segments if s.block_id == "b0001")
    row = re.search(
        rf'<div class="pair caption[^"]*"[^>]*data-id="{re.escape(caption.id)}".*?</div>',
        html,
        re.S,
    )
    assert row is not None
    assert re.search(
        r'<figure class="figure"><img src="data:image/webp;base64,[^"]+" width="640" height="320"',
        row.group(0),
    )
    # Nothing from the publisher is named in the page.
    assert "x.example" not in html


def test_the_shelf_copy_leaves_the_pictures_behind() -> None:
    assert "figures" in promote.NOT_COPIED
