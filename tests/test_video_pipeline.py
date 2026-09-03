"""A video source runs the audio import with the pictures kept beside it."""

from __future__ import annotations

from pathlib import Path

import pytest

from targum.audio import manifest as manifest_module
from targum.audio import probe
from targum.errors import TargumError
from targum.pipeline import Build
from targum.transcribe.null import NullTranscriber

SAID = (
    "the winter that year came early and stayed long. "
    "nobody in the village remembered a colder one. "
    "the river froze from bank to bank before december."
)


class SplitsOnFullStops:
    name = "fake/1"

    def split(self, texts: list[str], language: str) -> list[list[str]]:
        return [[part.strip() + "." for part in text.split(".") if part.strip()] for text in texts]


def film(tmp_path: Path) -> Path:
    source = tmp_path / "a-winter-talk.mp4"
    source.write_bytes(b"film")
    return source


def builder(tmp_path: Path, source: Path, **extra: object) -> Build:
    options: dict[str, object] = {
        "target_language": "en",
        "source_language": "en",
        "provider_name": "null",
        "segmenter": SplitsOnFullStops(),
        "transcriber": NullTranscriber(text=SAID, language="en"),
        "out_root": tmp_path / "out",
    }
    options.update(extra)
    return Build(str(source), **options)  # type: ignore[arg-type]


# -- the probe ---------------------------------------------------------------


def test_a_video_is_accepted_only_where_the_routing_chose_video(fake_audio, tmp_path) -> None:
    """The suffix decides what a file may be, not the file: the audio door still
    refuses a film, and the video door writes down that it saw one."""
    fake_audio.video = True
    source = film(tmp_path)
    with pytest.raises(TargumError, match="could not read"):
        probe.examine(source)
    seen = probe.examine(source, allow_video=True)
    assert seen.has_video
    assert seen.codec == "mp3", "the soundtrack is still the thing described"


def test_a_silent_video_is_refused_with_the_reason(fake_audio, tmp_path, monkeypatch) -> None:
    from targum.audio import tools as tools_module

    def silent(path: object) -> dict:
        answer = fake_audio.probe(path)
        answer["streams"] = [{"codec_type": "video", "disposition": {}}]
        return answer

    monkeypatch.setattr(tools_module, "ffprobe_json", silent)
    with pytest.raises(TargumError, match="nothing to transcribe in a silent video"):
        probe.examine(film(tmp_path), allow_video=True)


def test_a_video_over_four_hours_is_refused(fake_audio, tmp_path) -> None:
    """Tighter than audio's twelve: a part of video is fifty megabytes, not two."""
    fake_audio.video = True
    fake_audio.duration = 15_000.0
    with pytest.raises(TargumError, match="over 4 hours"):
        probe.examine(film(tmp_path), allow_video=True)
    fake_audio.video = False
    plain = tmp_path / "a-winter-talk.mp3"
    plain.write_bytes(b"audio")
    heard = probe.examine(plain, allow_video=True)
    assert heard.duration == 15_000.0, "the same length of plain audio is still fine"


# -- the build ---------------------------------------------------------------


def test_a_video_build_cuts_a_sidecar_beside_each_heard_part(fake_audio, tmp_path) -> None:
    fake_audio.video = True
    fake_audio.duration = 1400.0
    build = builder(tmp_path, film(tmp_path))
    result = build.run()

    workspace = result.out_dir / "audio"
    assert (workspace / "parts" / "part-001.mp3").exists()
    assert (workspace / "parts" / "part-001.mp4").exists()
    kept = manifest_module.load(result.out_dir)
    assert kept is not None
    assert kept.parts[0].video == "audio/parts/part-001.mp4"
    assert kept.parts[0].audio == "audio/parts/part-001.mp3"
    # The two cuts share their start and end exactly, so one set of spans times both.
    sound = {(s, e) for _, s, e in fake_audio.cuts if _.startswith("part-")}
    moving = {(s, e) for _, s, e in fake_audio.video_cuts}
    assert moving == sound


def test_no_video_keeps_the_import_an_audio_one(fake_audio, tmp_path) -> None:
    """For whoever wants the talk, not the talking head."""
    fake_audio.video = True
    fake_audio.duration = 1400.0
    build = builder(tmp_path, film(tmp_path), video=False)
    result = build.run()

    assert not list((result.out_dir / "audio" / "parts").glob("*.mp4"))
    kept = manifest_module.load(result.out_dir)
    assert kept is not None
    assert kept.parts[0].video == ""
    assert kept.parts[0].transcribed


def test_an_untranscribed_part_gets_no_video_cut(fake_audio, tmp_path) -> None:
    """Cutting video costs minutes; a part nobody bought gets neither file."""
    fake_audio.video = True
    fake_audio.duration = 7200.0  # ten parts
    build = builder(tmp_path, film(tmp_path))
    build.run(chapters=1)

    parts = build.resolved_out / "audio" / "parts"
    assert (parts / "part-001.mp4").exists()
    assert not (parts / "part-002.mp4").exists()


def test_a_youtube_address_runs_the_import_through_the_youtube_door(
    fake_audio, tmp_path, monkeypatch
) -> None:
    """The build routes a watch page to yt-dlp, names the workspace by the video id,
    and probes what arrived as video — no other door touched."""
    from targum.video import youtube

    fetched: list[str] = []

    def pretend(url: str, into: Path) -> Path:
        fetched.append(url)
        into.mkdir(parents=True, exist_ok=True)
        target = into / "source.mp4"
        target.write_bytes(b"film")
        return target

    monkeypatch.setattr(youtube, "fetch", pretend)
    fake_audio.video = True
    fake_audio.duration = 600.0
    address = "https://www.youtube.com/watch?v=abc123"
    build = builder(tmp_path, address)  # type: ignore[arg-type] - str passes through
    result = build.run()

    assert fetched == [address]
    assert result.out_dir.name == "abc123-en", "named by the video id, not 'watch'"
    kept = manifest_module.load(result.out_dir)
    assert kept is not None
    assert kept.parts[0].video == "audio/parts/part-001.mp4"
    # The address survives the adoption that turns `source` into a local file: it is
    # the one fact the page needs to hand the video back.
    assert kept.home == address
    assert kept.source.endswith("source.mp4")


def test_a_video_from_youtube_links_home_at_the_line_and_an_upload_links_nowhere(
    fake_audio, tmp_path, monkeypatch
) -> None:
    """A YouTube-sourced reader is a study copy of a video that lives elsewhere, and
    says so with a link that opens there; an uploaded file has no elsewhere, and the
    page must not offer a door to nowhere."""
    import re

    from targum.video import youtube

    def pretend(url: str, into: Path) -> Path:
        into.mkdir(parents=True, exist_ok=True)
        target = into / "source.mp4"
        target.write_bytes(b"film")
        return target

    monkeypatch.setattr(youtube, "fetch", pretend)
    fake_audio.video = True
    fake_audio.duration = 600.0
    fetched = builder(tmp_path, "https://youtu.be/abc123?si=share").run()  # type: ignore[arg-type]
    html = fetched.pages[-1].read_text(encoding="utf-8")
    assert 'data-home href="https://www.youtube.com/watch?v=abc123"' in html, "canonical"
    assert 'rel="noreferrer noopener"' in html and 'target="_blank"' in html
    assert not re.search(r'data-home href="[^"]*[?&]t=', html), "decided at the click"
    assert '"home": "https://www.youtube.com/watch?v=abc123"' in html
    assert '"offset": 0.0' in html, "the first part begins at the start"
    assert "data-video aria-pressed" in html, "and the sidecar is still the instrument"

    (tmp_path / "up").mkdir()
    uploaded = builder(tmp_path / "up", film(tmp_path / "up")).run()
    for page in uploaded.pages:
        text = page.read_text(encoding="utf-8")
        assert "data-home href=" not in text
        assert '"home": ' not in text
    kept = manifest_module.load(uploaded.out_dir)
    assert kept is not None and kept.home == ""


def test_a_short_link_takes_its_stem_for_a_name(fake_audio, tmp_path, monkeypatch) -> None:
    from targum.video import youtube

    def pretend(url: str, into: Path) -> Path:
        into.mkdir(parents=True, exist_ok=True)
        target = into / "source.mp4"
        target.write_bytes(b"film")
        return target

    monkeypatch.setattr(youtube, "fetch", pretend)
    fake_audio.video = True
    fake_audio.duration = 600.0
    build = builder(tmp_path, "https://youtu.be/xyz789")  # type: ignore[arg-type]
    result = build.run()
    assert result.out_dir.name == "xyz789-en"


def test_a_failed_video_cut_degrades_to_audio_alone(fake_audio, tmp_path, monkeypatch) -> None:
    """The pictures are optional and the transcription is already paid for: one bad
    ffmpeg run costs the part its picture, never the build."""
    from targum.audio import tools as tools_module

    def refuse(source: Path, into: Path, start: float, end: float) -> None:
        raise TargumError("targum could not read this audio file.")

    fake_audio.video = True
    fake_audio.duration = 600.0
    build = builder(tmp_path, film(tmp_path))
    monkeypatch.setattr(tools_module, "cut_video", refuse)
    result = build.run()

    kept = manifest_module.load(result.out_dir)
    assert kept is not None
    assert kept.parts[0].video == ""
    assert kept.parts[0].transcribed
    assert kept.parts[0].audio == "audio/parts/part-001.mp3"


# -- the reader --------------------------------------------------------------


def test_the_page_names_its_own_part_and_never_inlines_it(fake_audio, tmp_path) -> None:
    """The sidecar rule: a relative address in the page, the bytes beside it — and only
    this page's own part, the rule that shaped the inlined audio."""
    import base64
    import re

    fake_audio.video = True
    fake_audio.duration = 1440.0  # two parts
    fake_audio.pauses = [(719.0, 721.0)]
    build = builder(tmp_path, film(tmp_path))
    result = build.run()

    pages = {page.name: page.read_text(encoding="utf-8") for page in result.pages}
    first = pages["sec-0001.html"]
    second = pages["sec-0002.html"]
    # data-src, not src: the script appends the page's own query (the serve key)
    # before the browser ever asks — a bare src would ask without it and be refused.
    assert 'data-src="video/part-001.mp4"' in first and "part-002.mp4" not in first
    assert 'data-src="video/part-002.mp4"' in second and "part-001.mp4" not in second
    assert '<video class="video-el" playsinline preload="metadata" src=' not in first
    assert base64.b64encode(b"part-001.mp4").decode("ascii") not in first, "never inlined"
    # The copies stand beside the pages, where the relative address reaches them.
    where = result.pages[-1].parent
    assert (where / "video" / "part-001.mp4").is_file()
    assert (where / "video" / "part-002.mp4").is_file()

    # And the page still fetches nothing — the same two rules test_render pins.
    for html in (first, second):
        for position in (r'src\s*=\s*["\']', r"url\(", r'<link[^>]+href\s*=\s*["\']'):
            assert not re.search(position + r"(https?:)?//", html, re.I)


def test_a_soundtrack_only_reader_offers_no_video_toggle(fake_audio, tmp_path) -> None:
    fake_audio.duration = 600.0
    source = tmp_path / "a-winter-talk.mp3"
    source.write_bytes(b"audio")
    build = builder(tmp_path, source)
    result = build.run()
    for page in result.pages:
        text = page.read_text(encoding="utf-8")
        # The script rides in every page; the markup is what must not.
        assert "data-video aria-pressed" not in text
        assert 'id="video"' not in text


def test_an_old_manifest_without_the_video_field_still_reads(tmp_path: Path) -> None:
    (tmp_path / "audio.json").write_text(
        '{"source": "talk.mp3", "sha256": "x", "duration": 60.0, "language": "en",'
        ' "parts": [{"number": 1, "start": 0.0, "end": 60.0}]}',
        encoding="utf-8",
    )
    kept = manifest_module.load(tmp_path)
    assert kept is not None
    assert kept.parts[0].video == ""


def test_whether_an_import_kept_its_pictures_is_the_manifests_word(tmp_path: Path) -> None:
    """The shelf's "video" is asked of the manifest beside the reader, not of the
    sidecar folder — the folder is a copy the build remakes, the manifest is the claim."""
    assert not manifest_module.keeps_video(tmp_path), "no manifest, no claim"
    part = manifest_module.ManifestPart(number=1, start=0.0, end=10.0, audio="a.mp3")
    manifest_module.write(
        tmp_path,
        manifest_module.AudioManifest(
            source="talk.mp3", sha256="x", duration=10.0, language="en", parts=[part]
        ),
    )
    assert not manifest_module.keeps_video(tmp_path), "sound alone is an audio import"
    part.video = "audio/parts/part-001.mp4"
    manifest_module.write(
        tmp_path,
        manifest_module.AudioManifest(
            source="talk.mp4", sha256="x", duration=10.0, language="en", parts=[part]
        ),
    )
    assert manifest_module.keeps_video(tmp_path)
