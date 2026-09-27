"""The post card: a post read as a post (targum-internal#159).

design.md §12, "A post keeps its shape" (2026-09-27): the head takes the title's place,
the pictures follow at their own shape, the caption is the text, nothing is fetched, and
the one address on the page is the link home. Hashtags, mentions and addresses stay where
they were written and are neither tapped nor counted.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from targum.ingest import post
from targum.models import (
    Annotation,
    BlockKind,
    Document,
    Segment,
    SegmentedDocument,
    Token,
    Translation,
)
from targum.render import render

Image = pytest.importorskip("PIL.Image", reason="Pillow is in the covers extra")

URL = "https://www.instagram.com/p/DdCARhLDF-P/?igsh=abc"
HOME = "https://www.instagram.com/p/DdCARhLDF-P"

#: The caption's lines, as the text path makes them: the title and byline the front
#: matter put on top, then one paragraph a line.
LINES = [
    (BlockKind.heading, 1, "שבת שלום לכולם"),
    (BlockKind.byline, None, "@aviv.bahar"),
    (BlockKind.paragraph, None, "שבת שלום לכולם"),
    (BlockKind.paragraph, None, "ראו #שבת_שלום אצל @kan_news"),
    (BlockKind.paragraph, None, "https://kan.org.il/x"),
]


def segments() -> SegmentedDocument:
    return SegmentedDocument(
        document_hash="h",
        language="he",
        segmenter="fake/1",
        segments=[
            Segment(
                id=f"{n:04d}.000-aaaaaa",
                block_id=f"b{n:07d}",
                block_index=n,
                index=0,
                kind=kind,
                level=level,
                text=text,
            )
            for n, (kind, level, text) in enumerate(LINES)
        ],
    )


def tokens_of(text: str) -> list[Token]:
    """Every run of Hebrew letters as a word — the way an annotator that took the `#`
    and the `_` off a hashtag would find the words inside it."""
    return [
        Token(start=m.start(), end=m.end(), surface=m.group(), lemma=m.group(), band=2)
        for m in re.finditer(r"[א-ת]+", text)
    ]


def a_picture(path: Path, width: int, height: int) -> Path:
    Image.new("RGB", (width, height), (200, 120, 40)).save(path, format="JPEG")
    return path


def a_post(folder: Path, *, face: bool = True, name: str = "אביב בהר") -> Path:
    """A built post's folder: the segmentation, the annotation and `post.json` with its
    pictures and the author's face kept beside it."""
    folder.mkdir(parents=True, exist_ok=True)
    segmented = segments()
    segmented.write(folder / "segments.json")
    Annotation(
        document_hash="h",
        language="he",
        annotator="fake/1",
        method="fake",
        method_note="",
        tokens={s.id: tokens_of(s.text) for s in segmented.segments},
    ).write(folder / "annotation.json")
    raw = folder / "raw"
    raw.mkdir()
    media = post.keep_pictures(
        [
            a_picture(raw / "1.jpg", 1080, 1350),
            a_picture(raw / "2.jpg", 1080, 1080),
            a_picture(raw / "3.jpg", 1080, 566),
        ],
        folder,
    )
    avatar = post.keep_avatar(a_picture(raw / "face.jpg", 150, 150), folder) if face else ""
    post.write(
        folder,
        post.Manifest(
            platform="instagram",
            author=post.Author("aviv.bahar", name, avatar),
            items=[post.Item(block_ids=[f"b{n:07d}" for n in range(len(LINES))], media=media)],
            url=URL,
            posted_at="2026-09-21T13:33:20Z",
        ),
    )
    return folder


def rendered(folder: Path, target: str = "en") -> str:
    segmented = segments()
    document = Document(
        source=str(folder / "DdCARhLDF-P.txt"),
        title="שבת שלום לכולם",
        language="he",
        blocks=[],
        content_hash="h",
    )
    translation = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language=target,
        provider="null",
        segments={s.id: f"[{target}] {s.text}" for s in segmented.segments},
    )
    annotation = Annotation.model_validate_json(
        (folder / "annotation.json").read_text(encoding="utf-8")
    )
    pages = render(document, segmented, [translation], folder / "reader", annotation, folder=folder)
    return pages[0].read_text(encoding="utf-8")


def payload(html: str) -> dict:
    found = re.search(r'id="targum-data">(.*?)</script>', html, re.S)
    assert found, "the page carries its data"
    return json.loads(found.group(1))


def test_the_head_takes_the_titles_place(tmp_path: Path) -> None:
    html = rendered(a_post(tmp_path / "post"))
    head = html[html.index('class="post-head"') :]
    assert head.index("post-face") < head.index("post-name") < head.index("post-handle")
    assert ">אביב בהר</bdi>" in head
    assert ">@aviv.bahar</bdi>" in head
    assert '<time datetime="2026-09-21" dir="auto">Monday, September 21, 2026</time>' in head
    assert '<img src="data:image/webp;base64,' in head.split("post-who")[0], "their face"
    # The head is above every row of the caption, and stands in for the title and the
    # byline, which are not drawn a second time.
    assert html.index('<section class="post"') < html.index('<div class="pair')
    assert 'data-id="0000.000-aaaaaa"' not in html and 'data-id="0001.000-aaaaaa"' not in html
    assert 'data-id="0002.000-aaaaaa"' in html


def test_the_pictures_follow_in_order_at_their_own_shape(tmp_path: Path) -> None:
    html = rendered(a_post(tmp_path / "post"))
    at = html.index('<div class="post-pictures')
    row = html[at : html.index("</section>", at)]
    assert 'aria-label="3 pictures"' in row
    shapes = re.findall(r'src="data:image/webp;base64,[^"]+" width="(\d+)" height="(\d+)"', row)
    assert shapes == [("1024", "1280"), ("1080", "1080"), ("1080", "566")], (
        "in the post's order, each as it was kept: 4:5, 1:1 and wide, never cropped"
    )


def test_a_post_without_a_face_wears_its_first_letter(tmp_path: Path) -> None:
    html = rendered(a_post(tmp_path / "post", face=False, name=""))
    at = html.index('class="post-face')
    face = html[at : html.index("post-who", at)]
    assert "letter" in face and ">A</span>" in face and "<img" not in face
    # Without a name the handle is the name.
    assert 'class="post-handle alone"' in html


def test_the_one_way_home_is_the_post_and_nothing_is_fetched(tmp_path: Path) -> None:
    from test_render import OUTBOUND

    html = rendered(a_post(tmp_path / "post"))
    assert f'<a class="post-home" href="{HOME}" target="_blank" rel="noreferrer noopener"' in html
    assert ">On Instagram</a>" in html
    for position in (r'src\s*=\s*["\']', r"url\(", r'<link[^>]+href\s*=\s*["\']'):
        assert not re.search(position + r"(https?:)?//", html, re.I)
    for match in re.finditer(r"https?://[^\s\"'\\)<]+", html):
        # The caption's own address is text the author wrote, drawn as text: never a link.
        if match.group(0).startswith("https://kan.org.il"):
            assert f'href="{match.group(0)}' not in html
            continue
        assert match.group(0).startswith(OUTBOUND), match.group(0)


def test_the_link_home_is_said_in_the_readers_language(tmp_path: Path) -> None:
    html = rendered(a_post(tmp_path / "post"), target="ru")
    assert ">В Instagram</a>" in html
    assert 'aria-label="3 картинки"' in html


def test_hashtags_mentions_and_addresses_are_not_words_on_the_page(tmp_path: Path) -> None:
    """The words inside `#שבת_שלום` are not tapped or counted, and the word beside it is."""
    data = payload(rendered(a_post(tmp_path / "post")))
    words = data["words"]
    assert len(words["0002.000-aaaaaa"]) == 3, "a line of words is all words"
    line = words["0003.000-aaaaaa"]
    kept = {data["lemmas"][row[4]] for row in line}
    assert kept == {"ראו", "אצל"}, "the hashtag's letters are a name, not two words"
    assert not words.get("0004.000-aaaaaa")
    # Nor are the rows the head stands in for.
    assert "0000.000-aaaaaa" not in words and "0001.000-aaaaaa" not in words


def test_a_text_that_is_not_a_post_is_drawn_as_it_was(tmp_path: Path) -> None:
    folder = a_post(tmp_path / "post")
    (folder / post.NAME).unlink()
    html = rendered(folder)
    assert 'class="post-head"' not in html and "mode-parallel is-post" not in html
    assert 'data-id="0000.000-aaaaaa"' in html, "the title is its own row again"
    words = payload(html)["words"]
    assert len(words["0003.000-aaaaaa"]) == 4, "every word counted, as before"


def test_the_shelf_does_not_count_them_either(tmp_path: Path) -> None:
    """`coverage.lemmas` is what the known share on the shelf is measured with."""
    from targum import coverage

    folder = a_post(tmp_path / "post")
    assert set(coverage.lemmas(folder)) == {"שבת", "שלום", "לכולם", "ראו", "אצל"}
    # And the same folder without its manifest counts what the annotator found.
    (folder / post.NAME).unlink()
    assert {"שבת_", "שלום"} & set(coverage.lemmas(folder)) == {"שלום"}
    assert "kan" not in "".join(coverage.lemmas(folder))


def test_the_level_on_the_shelf_does_not_count_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum import level, serve

    folder = a_post(tmp_path / "post")
    counted: list[list[int | None]] = []

    def text_rung(running, ladder):  # type: ignore[no-untyped-def]
        counted.append(list(running))
        return None

    monkeypatch.setattr(level, "text_rung", text_rung)
    serve.Library._text_level(folder / "annotation.json", "he")
    if counted:  # only where this machine has Hebrew's frequency list
        # The title's three, the first line's three, and ראו and אצל: the hashtag's two
        # letters-runs are left out.
        assert len(counted[0]) == 8


def test_the_quote_does_not_count_them(tmp_path: Path) -> None:
    text = "שלום " * 20 + "#שבת_שלום @kan_news https://kan.org.il/שלום"
    assert post.without_unwordly(text).split() == ["שלום"] * 20


@pytest.mark.parametrize(
    ("text", "names"),
    [
        ("שבת שלום #שבת_שלום", ["#שבת_שלום"]),
        ("תודה @aviv.bahar.", ["@aviv.bahar"]),
        (
            "ראו www.ynet.co.il ו-https://kan.org.il/x?y=1",
            ["www.ynet.co.il", "https://kan.org.il/x?y=1"],
        ),
        ("#חַג שמח", ["#חַג"]),
        ("שלום עולם", []),
    ],
)
def test_what_is_a_name_and_not_a_word(text: str, names: list[str]) -> None:
    assert [text[a:b] for a, b in post.unwordly(text)] == names


def test_a_caption_keeps_its_lines() -> None:
    """Each line of the caption is its own paragraph, so a line with no full stop does
    not run into the next as one sentence."""
    from targum.ingest.base import parse_frontmatter
    from targum.video import instagram

    got = instagram.caption_text(
        instagram.Post(code="x", author="a", caption="שורה אחת\nשורה שתיים\n\n#תג")
    )
    _, body = parse_frontmatter(got)
    assert body.strip().split("\n\n") == ["שורה אחת", "שורה שתיים", "#תג"]
