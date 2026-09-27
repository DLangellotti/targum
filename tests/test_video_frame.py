"""The shape of a film, measured by the build so the page need not wait for the film.

Until a video's metadata lands the page has only the stylesheet's 16/9, so a reel stood
in a landscape frame and jumped upright a moment later (design review, 2026-09-20).
`tools.frame` reads the cut's size, the manifest keeps it, and the page carries it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from targum.audio import manifest as manifest_module
from targum.audio import tools
from targum.errors import TargumError


def _probe(monkeypatch: pytest.MonkeyPatch, streams: list[dict]) -> None:
    monkeypatch.setattr(tools, "ffprobe_json", lambda path: {"streams": streams})


def test_a_reel_is_taller_than_it_is_wide(monkeypatch: pytest.MonkeyPatch) -> None:
    _probe(
        monkeypatch,
        [
            {"codec_type": "audio", "codec_name": "aac"},
            {"codec_type": "video", "width": 480, "height": 854, "disposition": {}},
        ],
    )
    assert tools.frame(Path("part-001.mp4")) == [480, 854]


@pytest.mark.parametrize(
    "stream",
    [
        {"tags": {"rotate": "90"}},
        {"side_data_list": [{"side_data_type": "Display Matrix", "rotation": -90}]},
        {"side_data_list": [{"rotation": 270.0}]},
    ],
)
def test_a_film_the_container_says_to_turn_is_turned(
    monkeypatch: pytest.MonkeyPatch, stream: dict
) -> None:
    """A phone records upright as a landscape stream and a note saying turn it. The
    player obeys the note, so the frame has to."""
    _probe(monkeypatch, [{"codec_type": "video", "width": 854, "height": 480, **stream}])
    assert tools.frame(Path("part-001.mp4")) == [480, 854]


def test_a_film_turned_upside_down_keeps_its_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    _probe(
        monkeypatch,
        [{"codec_type": "video", "width": 854, "height": 480, "tags": {"rotate": "180"}}],
    )
    assert tools.frame(Path("part-001.mp4")) == [854, 480]


@pytest.mark.parametrize(
    "streams",
    [
        [],
        [{"codec_type": "audio"}],
        [{"codec_type": "video"}],
        [{"codec_type": "video", "width": 0, "height": 480}],
        [{"codec_type": "video", "width": "wide", "height": 480}],
        # Cover art is a picture, not a film.
        [{"codec_type": "video", "width": 600, "height": 600, "disposition": {"attached_pic": 1}}],
    ],
)
def test_what_the_probe_cannot_say_is_nothing_and_never_a_guess(
    monkeypatch: pytest.MonkeyPatch, streams: list[dict]
) -> None:
    _probe(monkeypatch, streams)
    assert tools.frame(Path("part-001.mp4")) == []


def test_a_file_that_cannot_be_probed_has_no_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    """No ffprobe on the machine, or a file it will not read: the page waits for the
    film as it always did, and the build carries on."""

    def refuse(path: Path) -> dict:
        raise TargumError(tools.UNREADABLE)

    monkeypatch.setattr(tools, "ffprobe_json", refuse)
    assert tools.frame(Path("part-001.mp4")) == []


def test_a_manifest_written_before_the_shape_was_kept_still_loads() -> None:
    old = manifest_module.ManifestPart.model_validate(
        {"number": 1, "start": 0.0, "end": 10.0, "video": "video/parts/part-001.mp4"}
    )
    assert old.frame == []
    kept = manifest_module.ManifestPart(number=1, start=0.0, end=10.0, frame=[480, 854])
    assert manifest_module.ManifestPart.model_validate_json(kept.model_dump_json()).frame == [
        480,
        854,
    ]
