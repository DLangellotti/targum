"""`post.json`: a post kept as a post beside its reader (targum-internal#158)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from targum.ingest import post

Image = pytest.importorskip("PIL.Image", reason="Pillow is in the covers extra")


def a_picture(path: Path, width: int, height: int) -> Path:
    Image.new("RGB", (width, height), (200, 120, 40)).save(path, format="JPEG")
    return path


def a_manifest(**over: Any) -> post.Manifest:
    said: dict[str, Any] = {
        "platform": "instagram",
        "author": post.Author("aviv.bahar", "אביב בהר"),
        "items": [post.Item(block_ids=["b0000000", "b0000001"])],
        "url": "https://www.instagram.com/p/DdCARhLDF-P/",
        "posted_at": "2026-09-21T13:33:20Z",
    }
    said.update(over)
    return post.Manifest(**said)


def test_a_manifest_round_trips_and_its_licence_is_always_none(tmp_path: Path) -> None:
    """A post is its author's: the three fields are "", false, false whatever was passed."""
    post.write(tmp_path, a_manifest(licence="CC0", reader_publishable=True))
    got = post.read(tmp_path)
    assert got is not None
    assert got["platform"] == "instagram" and got["fetched_by"] == "paste"
    assert got["author"] == {"handle": "aviv.bahar", "name": "אביב בהר", "avatar": ""}
    assert got["items"][0]["block_ids"] == ["b0000000", "b0000001"]
    assert (got["licence"], got["reader_publishable"], got["corpus_exportable"]) == (
        "",
        False,
        False,
    )
    assert got["fetched_at"].endswith("Z")


def test_a_platform_or_a_door_it_does_not_know_is_refused() -> None:
    with pytest.raises(ValueError):
        a_manifest(platform="reddit")
    with pytest.raises(ValueError):
        a_manifest(fetched_by="scraped")


def test_a_folder_without_one_is_a_plain_text(tmp_path: Path) -> None:
    assert post.read(tmp_path) is None
    (tmp_path / post.NAME).write_text(json.dumps({"platform": "myspace"}), encoding="utf-8")
    assert post.read(tmp_path) is None


def test_pictures_are_kept_as_webp_in_order_never_cropped(tmp_path: Path) -> None:
    """A 4:5 post stays 4:5 (§12), at a long edge of 1280 at most, and a picture that will
    not open is left out rather than failing the post."""
    tall = a_picture(tmp_path / "01.jpg", 2000, 2500)
    small = a_picture(tmp_path / "02.jpg", 600, 600)
    broken = tmp_path / "03.jpg"
    broken.write_bytes(b"not a picture")
    media = post.keep_pictures([tall, small, broken], tmp_path / "reader-folder")
    assert [m.path for m in media] == ["post/media-001.webp", "post/media-002.webp"]
    assert (media[0].width, media[0].height) == (1024, 1280)
    assert (media[1].width, media[1].height) == (600, 600), "never enlarged"
    kept = Image.open(tmp_path / "reader-folder" / media[0].path)
    assert kept.format == "WEBP"


def test_a_finished_post_build_writes_its_manifest_beside_the_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`Library.keep_post`, with the download stood in: the pictures the embed page named
    are kept, the caption's blocks are the item's, and the job's post says who and when."""
    from targum import serve
    from targum.video import instagram

    def pictures_into(found: Any, folder: Path) -> list[Path]:
        folder.mkdir(parents=True, exist_ok=True)
        return [
            a_picture(folder / f"{n:02d}.jpg", 1080, 1350)
            for n in range(1, len(found.pictures) + 1)
        ]

    monkeypatch.setattr(instagram, "pictures_into", pictures_into)
    folder = tmp_path / "post-folder"
    folder.mkdir()
    job = serve.Job(id="j", source="x", options={})
    job.options["post"] = {
        "platform": "instagram",
        "url": "https://www.instagram.com/p/DdCARhLDF-P/",
        "handle": "aviv.bahar",
        "name": "",
        "posted_at": "",
        "avatar": "https://a.fna.fbcdn.net/face.jpg",
        "pictures": ["https://a.fna.fbcdn.net/one.jpg", "https://a.fna.fbcdn.net/two.jpg"],
    }
    blocks = [SimpleNamespace(id="b0000000"), SimpleNamespace(id="b0000001")]
    document = SimpleNamespace(blocks=blocks)
    serve.Library.keep_post(SimpleNamespace(incidents=None), job, folder, document)  # type: ignore[arg-type]
    got = post.read(folder)
    assert got is not None
    assert got["author"]["handle"] == "aviv.bahar"
    assert got["items"][0]["block_ids"] == ["b0000000", "b0000001"]
    assert [m["path"] for m in got["items"][0]["media"]] == [
        "post/media-001.webp",
        "post/media-002.webp",
    ]
    assert got["posted_at"] == ""
    assert got["author"]["avatar"] == "post/avatar.webp", "the last fetched is the face"
    assert Image.open(folder / "post" / "avatar.webp").size == (post.AVATAR_EDGE, post.AVATAR_EDGE)


def test_a_build_that_is_not_a_post_writes_nothing(tmp_path: Path) -> None:
    from targum import serve

    job = serve.Job(id="j", source="x", options={})
    serve.Library.keep_post(
        SimpleNamespace(incidents=None), job, tmp_path, SimpleNamespace(blocks=[])
    )  # type: ignore[arg-type]
    assert post.read(tmp_path) is None


"""--- a film keeps its shape too: a reel, and a TikTok (targum-internal#158) ---"""


def a_built_reel(folder: Path) -> SimpleNamespace:
    """A reel's folder after the recording pipeline: its cut named by the audio manifest,
    and the document's title, byline, transcript and caption."""
    from targum.audio import manifest as manifest_module

    (folder / "audio" / "parts").mkdir(parents=True)
    (folder / "audio" / "parts" / "part-001.mp4").write_bytes(b"film")
    manifest_module.write(
        folder,
        manifest_module.AudioManifest(
            source=str(folder / "audio" / "source.mp4"),
            home="https://www.instagram.com/reel/DSkLv4UE196/",
            sha256="x",
            duration=49.0,
            language="he",
            parts=[
                manifest_module.ManifestPart(
                    number=1,
                    start=0.0,
                    end=49.0,
                    audio="audio/parts/part-001.mp3",
                    video="audio/parts/part-001.mp4",
                    frame=[270, 480],
                )
            ],
        ),
    )
    return SimpleNamespace(
        blocks=[
            SimpleNamespace(id="b0000000", ref=""),
            SimpleNamespace(id="b0000001", ref=""),
            SimpleNamespace(id="b0010000", ref="part 1"),
            SimpleNamespace(id="b0010001", ref="part 1:1"),
            SimpleNamespace(id="b10000000", ref="caption:1"),
        ]
    )


def test_a_reels_manifest_names_its_cut_and_keeps_its_caption_apart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The clip is the transcript with the recording's own cut as its media — named, never
    copied — and the caption is a separate item (#158, rule 7). yt-dlp gives no face, so
    the embed page is asked for one; the head is the handle, the name and the day."""
    from targum import serve
    from targum.video import instagram

    folder = tmp_path / "reel"
    document = a_built_reel(folder)
    asked: list[str] = []

    def backup(url: str) -> instagram.Post:
        asked.append(url)
        return instagram.Post(
            "DSkLv4UE196",
            "kan_news",
            "caption",
            video="https://v.fbcdn.net/film.mp4",
            name="כאן חדשות",
            posted="2026-09-21T13:33:20Z",
            avatar="https://a.fna.fbcdn.net/face.jpg",
        )

    def pictures_into(found: Any, into: Path) -> list[Path]:
        into.mkdir(parents=True, exist_ok=True)
        return [a_picture(into / f"{n:02d}.jpg", 150, 150) for n in range(len(found.pictures))]

    monkeypatch.setattr(instagram, "backup", backup)
    monkeypatch.setattr(instagram, "pictures_into", pictures_into)
    job = serve.Job(id="j", source="https://www.instagram.com/reel/DSkLv4UE196/", options={})
    serve.Library._keep_film_post(
        job, platform="instagram", handle="kan_news", name="", caption="שבת שלום"
    )
    library = SimpleNamespace(incidents=None, _film_items=serve.Library._film_items)
    serve.Library.keep_post(library, job, folder, document)  # type: ignore[arg-type]

    got = post.read(folder)
    assert got is not None
    assert asked == ["https://www.instagram.com/reel/DSkLv4UE196/"]
    assert got["author"] == {
        "handle": "kan_news",
        "name": "כאן חדשות",
        "avatar": "post/avatar.webp",
    }
    assert got["posted_at"] == "2026-09-21T13:33:20Z"
    clip, caption = got["items"]
    assert clip["kind"] == "clip" and clip["block_ids"] == ["b0010000", "b0010001"]
    assert clip["media"] == [
        {
            "kind": "video",
            "path": "audio/parts/part-001.mp4",
            "width": 270,
            "height": 480,
            "alt": "",
        }
    ]
    assert caption == {"block_ids": ["b10000000"], "media": [], "kind": "caption", "author": None}
    assert sorted(p.name for p in (folder / "post").iterdir()) == ["avatar.webp"], "no copy"


def test_a_pasted_reel_keeps_what_its_head_draws_and_its_caption_for_the_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At the quote, from yt-dlp's answer: Instagram's `channel` is the handle and its
    `uploader` the name. The build is handed the caption."""
    from targum import serve
    from targum.video import instagram

    monkeypatch.setattr(
        instagram,
        "describe",
        lambda url: {
            "webpage_url": "https://www.instagram.com/reel/DSkLv4UE196/",
            "title": "שבת שלום",
            "duration": 49.4,
            "channel": "kan_news",
            "uploader": "כאן חדשות",
            "timestamp": 1790000000,
            "description": "שבת שלום\n#שבת",
            "formats": [{"acodec": "mp4a.40.5"}],
        },
    )
    monkeypatch.setattr("targum.video.ytdlp_available", lambda: (True, "yt-dlp"))
    library = serve.Library(tmp_path)
    job = serve.Job(id="a", source="https://www.instagram.com/reel/DSkLv4UE196/")
    library.prepare(job)
    assert job.stage in ("ready", "blocked"), job.error
    said = job.options["post"]
    assert (said["platform"], said["handle"]) == ("instagram", "kan_news")
    assert said["name"] == "כאן חדשות"
    assert said["posted_at"] == "2026-09-21T14:13:20Z"
    assert said["film"] is True and said["pictures"] == []
    build = library._builder(job)
    assert build.caption == "שבת שלום\n#שבת"
    assert build.beside is not None


#: The shape of `yt-dlp -J` on a public TikTok, recorded live on 2026-09-27 and trimmed to
#: the keys the door reads; the values are this test's own, not the post's.
TIKTOKED = {
    "id": "7485073076758007056",
    "title": "חידה: מה יורד בחורף? #עברית",
    "description": "חידה: מה יורד בחורף?\n#עברית #לשון",
    "uploader": "someone.teaches",
    "uploader_id": "6830258860894356486",
    "channel": "מישהו מלמד",
    "channel_id": "MS4wLjABAAAA",
    "timestamp": 1742754427,
    "duration": 11,
    "width": 1080,
    "height": 1920,
    "webpage_url": "https://www.tiktok.com/@someone.teaches/video/7485073076758007056",
    "uploader_url": "https://www.tiktok.com/@someone.teaches",
    "subtitles": {},
    "formats": [{"acodec": "aac"}],
}


def test_a_pasted_tiktok_arrives_as_a_post(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TikTok's answer is Instagram's the other way round: `uploader` is the handle and
    `channel` the name. A short link is followed at the quote, so the post's address is
    the one canonical shape the page's allowlist pins."""
    from targum import serve
    from targum.video import tiktok

    monkeypatch.setattr(tiktok, "describe", lambda url: TIKTOKED)
    monkeypatch.setattr("targum.video.ytdlp_available", lambda: (True, "yt-dlp"))
    library = serve.Library(tmp_path)
    job = serve.Job(id="a", source="https://vm.tiktok.com/ZMabc123/")
    library.prepare(job)
    assert job.stage in ("ready", "blocked"), job.error
    said = job.options["post"]
    assert (said["platform"], said["handle"], said["name"]) == (
        "tiktok",
        "someone.teaches",
        "מישהו מלמד",
    )
    assert said["url"] == "https://www.tiktok.com/@/video/7485073076758007056"
    assert said["posted_at"] == "2025-03-23T18:27:07Z"
    assert said["avatar"] == "" and said["film"] is True
    assert library._builder(job).caption == "חידה: מה יורד בחורף?\n#עברית #לשון"


#: The shape of `yt-dlp -J` on a public Facebook reel from כאן חדשות, recorded live from the
#: box on 2026-09-30 and trimmed to the keys the door reads; `title` is what `TITLED` made
#: of "2.1K views · 43 reactions | …".
FACEBOOKED = {
    "id": "28842223192082067",
    "title": "כשניקו נבון נפצע קשה בראשו במלחמה בעזה",
    "description": "כשניקו נבון נפצע קשה בראשו במלחמה בעזה\n\nNofar Moshe Ferdo",
    "uploader": "כאן חדשות",
    "uploader_id": "100064467291406",
    "timestamp": 1790758838,
    "duration": 893.016,
    "webpage_url": "https://m.facebook.com/watch/?v=28842223192082067&_rdr",
    "subtitles": {},
    "formats": [{"acodec": "aac"}],
}


def test_a_pasted_facebook_video_arrives_as_a_post(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Facebook gives the page's name and a number, and no handle a reader knows it by:
    the head carries the name alone, and the address is the film's one canonical shape."""
    from targum import serve
    from targum.video import facebook

    monkeypatch.setattr(facebook, "describe", lambda url: FACEBOOKED)
    monkeypatch.setattr("targum.video.ytdlp_available", lambda: (True, "yt-dlp"))
    library = serve.Library(tmp_path)
    job = serve.Job(id="a", source="https://www.facebook.com/reel/28842223192082067/")
    library.prepare(job)
    assert job.stage in ("ready", "blocked"), job.error
    said = job.options["post"]
    assert (said["platform"], said["handle"], said["name"]) == ("facebook", "", "כאן חדשות")
    assert said["url"] == "https://www.facebook.com/watch/?v=28842223192082067"
    assert said["posted_at"] == "2026-09-30T09:00:38Z"
    assert said["film"] is True
    assert job.title == "כשניקו נבון נפצע קשה בראשו במלחמה בעזה"
    assert library._builder(job).caption.startswith("כשניקו")


def test_a_tiktoks_manifest_asks_nothing_more_of_anybody(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No face to fetch and no embed page to ask: the manifest is written from what the
    quote kept and the recording's own cut."""
    from targum import serve
    from targum.video import instagram

    monkeypatch.setattr(instagram, "backup", lambda url: pytest.fail("not Instagram's page"))
    monkeypatch.setattr(instagram, "pictures_into", lambda *a: pytest.fail("nothing to fetch"))
    folder = tmp_path / "tiktok"
    document = a_built_reel(folder)
    job = serve.Job(id="j", source="https://www.tiktok.com/@/video/7485073076758007056")
    serve.Library._keep_film_post(
        job, platform="tiktok", handle="someone.teaches", name="מישהו מלמד", caption="חידה"
    )
    library = SimpleNamespace(incidents=None, _film_items=serve.Library._film_items)
    serve.Library.keep_post(library, job, folder, document)  # type: ignore[arg-type]
    got = post.read(folder)
    assert got is not None
    assert got["platform"] == "tiktok" and got["author"]["avatar"] == ""
    assert got["url"] == "https://www.tiktok.com/@/video/7485073076758007056"
    assert [item["kind"] for item in got["items"]] == ["clip", "caption"]
    assert got["items"][0]["media"][0]["path"] == "audio/parts/part-001.mp4"
