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
    assert got["author"] == {"handle": "aviv.bahar", "name": "אביב בהר"}
    assert got["items"][0]["block_ids"] == ["b0000000", "b0000001"]
    assert (got["licence"], got["reader_publishable"], got["corpus_exportable"]) == (
        "",
        False,
        False,
    )
    assert got["fetched_at"].endswith("Z")


def test_a_platform_or_a_door_it_does_not_know_is_refused() -> None:
    with pytest.raises(ValueError):
        a_manifest(platform="facebook")
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
        return [a_picture(folder / f"{n:02d}.jpg", 1080, 1350) for n in (1, 2)]

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
        "pictures": ["https://a.fna.fbcdn.net/one.jpg", "https://a.fna.fbcdn.net/two.jpg"],
    }
    blocks = [SimpleNamespace(id="b0000000"), SimpleNamespace(id="b0000001")]
    result = SimpleNamespace(out_dir=folder, document=SimpleNamespace(blocks=blocks))
    serve.Library.keep_post(SimpleNamespace(incidents=None), job, result)  # type: ignore[arg-type]
    got = post.read(folder)
    assert got is not None
    assert got["author"]["handle"] == "aviv.bahar"
    assert got["items"][0]["block_ids"] == ["b0000000", "b0000001"]
    assert [m["path"] for m in got["items"][0]["media"]] == [
        "post/media-001.webp",
        "post/media-002.webp",
    ]
    assert got["posted_at"] == ""


def test_a_build_that_is_not_a_post_writes_nothing(tmp_path: Path) -> None:
    from targum import serve

    job = serve.Job(id="j", source="x", options={})
    result = SimpleNamespace(out_dir=tmp_path, document=SimpleNamespace(blocks=[]))
    serve.Library.keep_post(SimpleNamespace(incidents=None), job, result)  # type: ignore[arg-type]
    assert post.read(tmp_path) is None
