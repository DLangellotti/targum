"""What a shelf row says at a glance (design.md §12, 2026-09-24).

The recording's length, the rung the text needs, the playlists it is in, and a video
import's own picture.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from targum.accounts import Store
from targum.audio import manifest as manifest_module
from targum.audio.manifest import POSTER
from targum.models import Annotation, Token
from targum.serve import Library


def annotated(folder: Path, lemmas: list[str]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    tokens = [Token(start=0, end=1, surface=one, lemma=one, band=1) for one in lemmas]
    path = folder / "annotation.json"
    path.write_text(
        Annotation(
            document_hash="x",
            language="he",
            annotator="test",
            method="test",
            method_note="",
            tokens={"s1": tokens},
        ).model_dump_json(),
        encoding="utf-8",
    )
    return path


def test_a_text_of_common_words_needs_aleph(tmp_path: Path) -> None:
    common = ["של", "את", "זה", "לא", "על", "הוא", "אני", "עם"]
    level = Library._text_level(annotated(tmp_path / "easy", common * 20), "he")
    assert level == {"rung": "א", "name": "aleph", "cefr": "A1"}


def test_a_text_of_rare_words_needs_a_high_rung(tmp_path: Path) -> None:
    rare = ["קטקומבה", "פרוזדור", "אנכרוניזם", "שלפוחית"]
    level = Library._text_level(annotated(tmp_path / "hard", rare * 20), "he")
    assert level is not None and level["name"] in ("hey", "vav")


def test_no_annotation_no_level(tmp_path: Path) -> None:
    assert Library._text_level(tmp_path / "annotation.json", "he") is None


def test_a_language_with_no_ladder_has_no_level(tmp_path: Path) -> None:
    assert Library._text_level(annotated(tmp_path / "yi", ["און"] * 5), "yi") is None


def test_the_recording_length_comes_from_the_manifest(tmp_path: Path) -> None:
    folder = tmp_path / "clip"
    folder.mkdir()
    assert Library._recording_seconds(folder) == 0
    manifest_module.write(
        folder,
        manifest_module.AudioManifest(source="x", sha256="0", duration=241.6, language="he"),
    )
    assert Library._recording_seconds(folder) == 242


def test_playlists_holding_names_every_playlist_a_text_is_in(tmp_path: Path) -> None:
    store = Store(tmp_path / "words.db")
    person = store.finish_sign_in(store.start_sign_in("reader@example.com"))
    assert person is not None
    me = person[0].id
    kitchen = store.make_playlist(me, "Kitchen")
    morning = store.make_playlist(me, "Morning")
    assert kitchen and morning
    store.add_to_playlist(me, kitchen["id"], "Jonah", reader="jonah")
    store.add_to_playlist(me, morning["id"], "Jonah", reader="jonah")
    store.add_to_playlist(me, morning["id"], "Ruth", reader="ruth")
    store.drop_playlist(me, morning["id"])
    assert store.playlists_holding(me) == {"jonah": ["Kitchen"]}, "a deleted playlist is gone"
    assert store.playlists_holding(None) == {}


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")
def test_a_poster_is_one_frame_of_the_first_cut(tmp_path: Path) -> None:
    from targum.video import poster

    folder = tmp_path / "clip"
    cut = folder / "video" / "part-1.mp4"
    cut.parent.mkdir(parents=True)
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x240:rate=10",
            "-t",
            "3",
            "-pix_fmt",
            "yuv420p",
            str(cut),
        ],
        capture_output=True,
        check=True,
    )
    manifest_module.write(
        folder,
        manifest_module.AudioManifest(
            source="x",
            sha256="0",
            duration=3,
            language="he",
            parts=[
                manifest_module.ManifestPart(number=1, start=0, end=3, video="video/part-1.mp4")
            ],
        ),
    )
    assert poster.ensure(folder)
    assert (folder / POSTER).read_bytes()[:2] == b"\xff\xd8"
    assert poster.ensure(folder), "a second call keeps the one it made"


def test_a_text_with_no_video_gets_no_poster(tmp_path: Path) -> None:
    from targum.video import poster

    assert not poster.ensure(tmp_path)
