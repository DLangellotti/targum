"""A post brought by hand (targum-internal#158): typed in on the Add page, with its
pictures or its video, and kept as a post the way a pasted one is."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from test_pages_serve import prepare, reading, send, served, two_pictures

from targum.ingest import post as post_module

__all__ = ["reading", "served"]

pytest.importorskip("PIL", reason="the bring extra is not installed: uv sync --extra bring")

WORDS = "הופעות הקיץ #קיץ\n\nשורה שנייה, עם @someone בתוכה."


def bring(port: int, token: str, **told: Any) -> tuple[int, dict]:
    extra = {
        name: told.pop(name)
        for name in ("uploads", "upload", "again", "pictures", "post")
        if name in told
    }
    brought = {"platform": "instagram", "handle": "aviv.bahar", "text": WORDS, **told}
    return prepare(port, token, {"brought": brought, **extra})


def pictures_up(port: int, token: str, tmp_path: Path) -> list[str]:
    ids = []
    for n, body in enumerate(two_pictures(tmp_path)):
        status, done = send(port, token, f"slide{n}.jpg", body)
        assert status == 200, done
        ids.append(done["upload"])
    return ids


def test_a_brought_post_of_words_is_a_text_with_its_author_and_nothing_fetched(
    served, reading, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The words are the text, a line a paragraph, under front matter naming the author;
    the card's facts ride on the job, marked brought, with no link and no face."""
    from targum.video import instagram

    monkeypatch.setattr(instagram, "backup", lambda url: pytest.fail("nothing is fetched"))
    port, token, _out, library = served
    status, job = bring(port, token, handle="@aviv.bahar", name="אביב בהר")
    assert status == 200, job
    assert not job["error"] and job["stage"] in {"ready", "blocked"}, job
    assert job["title"] == "הופעות הקיץ #קיץ"
    assert job["pictures_offered"] == 0
    held = library.jobs[job["id"]]
    text = Path(held.source).read_text(encoding="utf-8")
    assert "author: @aviv.bahar" in text
    assert text.index("הופעות הקיץ") < text.index("שורה שנייה")
    said = held.options["post"]
    assert said["fetched_by"] == "brought" and said["url"] is None
    assert said["handle"] == "aviv.bahar" and said["name"] == "אביב בהר"
    assert said["avatar"] == "" and said["posted_at"] == ""
    assert "brought" not in held.options, "the form's own fields stay at the door"
    assert reading == []


def test_a_brought_post_keeps_its_pictures_unread_and_its_manifest_says_brought(
    served, reading, tmp_path: Path
) -> None:
    """Acceptance 8: `post.json` with `fetched_by: brought` and `url: null`. The
    pictures go up, are kept beside the reader in their order, and are not read."""
    port, token, _out, library = served
    status, job = bring(port, token, uploads=pictures_up(port, token, tmp_path))
    assert status == 200, job
    assert not job["error"], job
    assert job["pictures_offered"] == 2, "offered, never run"
    assert reading == [], "nothing read without the press"
    held = library.jobs[job["id"]]
    assert held.reading == 0.0

    folder = tmp_path / "reader-folder"
    folder.mkdir()
    blocks = [SimpleNamespace(id="b0000000"), SimpleNamespace(id="b0000001")]
    library.keep_post(held, folder, SimpleNamespace(blocks=blocks))  # type: ignore[arg-type]
    got = post_module.read(folder)
    assert got is not None
    assert got["fetched_by"] == "brought" and got["url"] is None
    assert got["platform"] == "instagram"
    assert got["author"] == {"handle": "aviv.bahar", "name": "", "avatar": ""}
    assert [m["path"] for m in got["items"][0]["media"]] == [
        "post/media-001.webp",
        "post/media-002.webp",
    ]
    assert [m["width"] for m in got["items"][0]["media"]] == [300, 320], "in the order chosen"


def test_a_brought_posts_pictures_are_read_only_when_the_reader_presses(
    served, reading, tmp_path: Path
) -> None:
    """The press sends the same post again by its job, and the reading is claimed and
    settled on the rails a picture brought to the box is."""
    port, token, _out, library = served
    _, first = bring(port, token, uploads=pictures_up(port, token, tmp_path))
    assert reading == []
    status, job = bring(port, token, again=first["id"], pictures=True)
    assert status == 200, job
    assert not job["error"], job
    assert len(reading) == 2 and job["pages"] == 2 and job["pictures_offered"] == 0
    held = library.jobs[job["id"]]
    assert held.reading > 0 and held.spent == held.reading, "reserved, then settled"
    text = Path(held.source).read_text(encoding="utf-8")
    assert text.index("שורה שנייה") < text.index("שׁוּרָה"), "the post's words first"
    assert held.options["post"]["fetched_by"] == "brought"


def test_a_brought_post_of_pictures_alone_says_its_words_are_in_them(
    served, reading, tmp_path: Path
) -> None:
    port, token, _out, _library = served
    status, job = bring(port, token, text="", uploads=pictures_up(port, token, tmp_path))
    assert job["stage"] == "failed" and "in its pictures" in job["error"], job
    assert job["pictures_offered"] == 2, "the refusal carries its way forward"
    assert reading == []


def test_a_link_is_kept_in_its_platforms_shape_and_names_the_platform(served) -> None:
    from targum.ingest import x as x_module

    port, token, _out, library = served
    status, job = bring(
        port,
        token,
        platform="instagram",
        link="https://twitter.com/aviv/status/1834567890123456789?s=20",
    )
    assert status == 200, job
    held = library.jobs[job["id"]]
    said = held.options["post"]
    assert said["platform"] == "x", "the link says where it was posted"
    assert said["url"] == x_module.home_url("https://x.com/aviv/status/1834567890123456789")
    assert held.options["came_from"] == said["url"]

    status, job = bring(port, token, link="https://www.instagram.com/p/DdCARhLDF-P/?igsh=abc")
    assert (
        library.jobs[job["id"]].options["post"]["url"] == "https://www.instagram.com/p/DdCARhLDF-P"
    )

    status, refused = bring(port, token, link="https://example.com/a-post")
    assert status == 400 and "isn't a post on Instagram, TikTok or X" in refused["error"]


@pytest.mark.parametrize(
    ("told", "said"),
    [
        ({"handle": ""}, "Add the handle it was posted under"),
        ({"handle": "a handle"}, "Add the handle it was posted under"),
        ({"handle": "x" * 31}, "Add the handle it was posted under"),
        ({"text": ""}, "Paste what the post says"),
        ({"text": "א" * (post_module.TEXT_MOST + 1)}, "longer than a post"),
        ({"platform": "facebook"}, "Choose where it was posted"),
    ],
)
def test_a_brought_post_is_refused_at_the_door_with_what_to_do(
    served, told: dict[str, Any], said: str
) -> None:
    port, token, _out, library = served
    status, refused = bring(port, token, **told)
    assert status == 400 and said in refused["error"], refused
    assert not library.jobs, "nothing quoted"


def test_a_post_is_its_pictures_or_one_video(served, tmp_path: Path) -> None:
    from pypdf import PdfWriter

    port, token, _out, _library = served
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    handout = tmp_path / "handout.pdf"
    with handout.open("wb") as out:
        writer.write(out)
    _, done = send(port, token, "handout.pdf", handout.read_bytes())
    status, refused = bring(port, token, upload=done["upload"])
    assert status == 400 and "pictures, or one video" in refused["error"], refused


def test_a_post_card_in_a_request_is_never_taken(served, tmp_path: Path) -> None:
    """What the card draws is the server's to write. One that arrived in a request could
    name any file on this disk as the post's picture, and `keep_post` would keep it."""
    port, token, _out, library = served
    secret = tmp_path / "secret"
    secret.mkdir()
    status, job = prepare(
        port,
        token,
        {
            "name": "note.txt",
            "content": "16jXlNeV15PXoiDXqdec15XXnQ==",
            "post": {"platform": "x", "handle": "h", "fetched_by": "brought", "kept": str(secret)},
        },
    )
    assert status == 200, job
    assert "post" not in library.jobs[job["id"]].options

    status, refused = bring(port, token, again="0123456789abcdef", pictures=True)
    assert status == 400 and "Bring it again" in refused["error"]


def test_a_brought_film_asks_nothing_of_instagram(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A pasted reel's face is asked of the embed page at the build; a brought one has no
    page to ask, and its disc wears the first letter."""
    from targum import serve
    from targum.video import instagram

    monkeypatch.setattr(instagram, "backup", lambda url: pytest.fail("nothing is fetched"))
    monkeypatch.setattr(serve.Library, "_film_items", staticmethod(lambda folder, document: []))
    job = serve.Job(id="j", source="clip.mp4", options={})
    job.options["post"] = {
        "platform": "instagram",
        "url": "https://www.instagram.com/p/DdCARhLDF-P/",
        "handle": "aviv.bahar",
        "name": "",
        "posted_at": "",
        "avatar": "",
        "pictures": [],
        "fetched_by": "brought",
        "kept": "",
        "film": True,
        "caption": "שורה",
    }
    serve.Library.keep_post(
        SimpleNamespace(incidents=None, _film_items=serve.Library._film_items),  # type: ignore[arg-type]
        job,
        tmp_path,
        SimpleNamespace(blocks=[]),
    )
    got = post_module.read(tmp_path)
    assert got is not None and got["fetched_by"] == "brought"
    assert got["author"]["avatar"] == ""


def test_a_brought_posts_title_is_its_first_line_or_its_author() -> None:
    text = post_module.brought_text("aviv.bahar", "")
    assert "title: Post by @aviv.bahar" in text
    long = " ".join(["מילה"] * 40)
    title = post_module.brought_text("h", long).split("\n")[1][len("title: ") :]
    assert len(title) <= post_module.TITLE_MOST and not title.endswith(" ")
    assert long.startswith(title)


def test_a_phone_photo_is_kept_upright(tmp_path: Path) -> None:
    """A phone stores a photo sideways with its turn in a tag; kept, it stands up."""
    from PIL import Image

    sideways = tmp_path / "phone.jpg"
    image = Image.new("RGB", (400, 300), "white")
    exif = image.getexif()
    exif[0x0112] = 6  # turned a quarter
    image.save(sideways, exif=exif)
    [kept] = post_module.keep_pictures([sideways], tmp_path / "reader")
    assert (kept.width, kept.height) == (300, 400)


def test_a_home_is_one_of_the_three_platforms_or_nothing() -> None:
    from targum.video import hosts

    tiktok = "https://www.tiktok.com/@kan/video/7412345678901234567"
    assert post_module.home_of(tiktok) == ("tiktok", hosts.home_url(tiktok))
    assert post_module.home_of("https://vimeo.com/76979871") is None
    assert post_module.home_of("https://www.youtube.com/watch?v=abcdefghijk") is None
    assert post_module.home_of("not a link") is None


def test_a_brought_post_without_a_link_draws_no_way_home_and_wears_its_letter(
    tmp_path: Path,
) -> None:
    """The card draws no link home where the post has no address (#158), and with no
    face the disc wears the name's first letter (§12)."""
    from targum.render.builder import post_card

    post_module.write(
        tmp_path,
        post_module.Manifest(
            platform="tiktok",
            author=post_module.Author("aviv.bahar", "אביב בהר"),
            items=[post_module.Item(block_ids=["b0000000"])],
            fetched_by="brought",
            url=None,
        ),
    )
    card, _ = post_card(tmp_path, SimpleNamespace(segments=[]), "en")  # type: ignore[arg-type]
    assert card is not None
    assert card["home"] == "" and card["avatar"] == "" and card["letter"] == "א"
    assert card["day"] == ""
