"""The YouTube door: a named address list, and a binary that does the fetching.

`ingest/url.py` is targum's one outbound door and stays it: everything targum fetches
itself goes through its SSRF guard, its size cap and its redirect ceiling. This module
is a second door with its own name on it, and it opens differently — nothing here
fetches anything. The URL is handed to the yt-dlp binary, which resolves YouTube's own
CDN addresses inside its own process; there is no request of ours a guard could vet,
so the guard is the allowlist below: only addresses that are plainly YouTube's are
handed over at all.

The same posture as ffmpeg — a subprocess, not a Python dependency: one dependency not
taken is one that cannot break, and yt-dlp breaks on YouTube's schedule, not ours.

On what may be fetched: what a person downloads with their own tools on their own
machine is their business; the curated library only carries what the operator is
authorized to publish. That line is policy, not code — deliberately (2026-08-31).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..errors import TargumError
from . import MAX_VIDEO_BYTES, VIDEO_HEIGHT, ytdlp_available

#: Addresses that are plainly YouTube's. A closed list, like the suffixes: the binary
#: would happily fetch a thousand other sites, and each of those is a decision nobody
#: made.
HOSTS = frozenset(
    {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
)

#: The one shape a video's home is written in. Every address in `HOSTS` names the same
#: video several ways — youtu.be, /shorts/, m. — and the reader carries exactly one,
#: because `test_render.py` allows outbound links by prefix and a prefix is one string.
WATCH = "https://www.youtube.com/watch?v="

#: Never more than the sidecar needs. The format is chosen at the download, because
#: fetching 1080p to throw three quarters of it away is paying twice.
FORMAT = f"bv*[height<={VIDEO_HEIGHT}]+ba/b[height<={VIDEO_HEIGHT}]/b"


def is_youtube(url: str) -> bool:
    """Whether this address names one YouTube video."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if host not in HOSTS:
        return False
    if host == "youtu.be":
        return len(parsed.path) > 1
    if parsed.path.startswith(("/playlist", "/feed", "/channel", "/@", "/c/", "/user/")):
        # One video at a time. A playlist is a queue of separate decisions, and a
        # channel is somebody's whole shelf.
        raise TargumError(
            "targum reads one video at a time.", "Give the address of a single video."
        )
    return parsed.path.startswith(("/watch", "/shorts/", "/live/"))


def video_id(url: str) -> str:
    """The video's own id, or "" for anything that is not one YouTube video."""
    try:
        if not is_youtube(url):
            return ""
    except TargumError:
        return ""
    parsed = urlparse(url)
    if parsed.path.startswith("/watch"):
        found = parse_qs(parsed.query).get("v") or [""]
        return found[0]
    # youtu.be/<id>, /shorts/<id>, /live/<id>: the id is the last step of the path.
    return parsed.path.rstrip("/").rsplit("/", 1)[-1]


def watch_url(url: str) -> str:
    """The canonical address of the video this one names, or "".

    What the reader links home to. One shape for every spelling, so the page's one
    outbound address is the one the allowlist pins, and so `&t=` can be appended
    without asking whether the address already carries a query.
    """
    found = video_id(url)
    return f"{WATCH}{found}" if found else ""


def fetch(url: str, into: Path) -> Path:
    """The video, fetched by yt-dlp into the workspace as `source.mp4`.

    Merged to mp4 whatever YouTube served, so the workspace holds the one container
    the rest of the pipeline expects to find as `source.*`.
    """
    if not is_youtube(url):
        raise TargumError("That address is not a YouTube video.")
    usable, hint = ytdlp_available()
    if not usable:
        raise TargumError("yt-dlp is not installed.", hint)
    into.mkdir(parents=True, exist_ok=True)
    target = into / "source.mp4"
    try:
        subprocess.run(
            [
                "yt-dlp",
                "-f",
                FORMAT,
                "--max-filesize",
                str(MAX_VIDEO_BYTES),
                "--no-playlist",
                "--merge-output-format",
                "mp4",
                # And when nothing was merged — a single-file webm was best — remux
                # it into the one container the pipeline looks for.
                "--remux-video",
                "mp4",
                # The video's own title and channel, written into the container's tags.
                # `ingest/audio.py` reads exactly those two and nothing else: without
                # them a fetched video is titled after its file, which is its id, and
                # arrives with no byline at all. A curated import under CC BY has to
                # name who made it, and this is where the name is available.
                "--embed-metadata",
                "-o",
                str(into / "source.%(ext)s"),
                url,
            ],
            capture_output=True,
            check=True,
            # Two hours: a 4 GB cap at ordinary speeds is minutes, and a stream of
            # unknown size — a live, a stall — must not record the operator's disk
            # until somebody notices.
            timeout=7200,
        )
    except OSError as error:
        raise TargumError("yt-dlp is not installed.", hint) from error
    except subprocess.TimeoutExpired as error:
        raise TargumError(
            "yt-dlp ran for two hours without finishing, so it was stopped."
        ) from error
    except subprocess.CalledProcessError as error:
        # yt-dlp's own last line is usually the honest sentence — an age gate, a
        # private video, a region block — and better than anything written here.
        said = (error.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        raise TargumError(said[-1] if said else "yt-dlp could not fetch that video.") from error
    if not target.is_file():
        raise TargumError("yt-dlp fetched nothing it could merge to mp4.")
    if target.stat().st_size > MAX_VIDEO_BYTES:
        target.unlink()
        raise TargumError("That video is larger than 4 GB.")
    return target


def _said(error: subprocess.CalledProcessError, fallback: str) -> str:
    # yt-dlp's own last line is usually the honest sentence — an age gate, a private
    # video, a region block — and better than anything written here.
    said = (error.stderr or b"").decode("utf-8", "replace").strip().splitlines()
    return said[-1] if said else fallback


def _run(argv: list[str], *, timeout: int) -> subprocess.CompletedProcess[bytes]:
    if not is_youtube(argv[-1]):
        raise TargumError("That address is not a YouTube video.")
    usable, hint = ytdlp_available()
    if not usable:
        raise TargumError("yt-dlp is not installed.", hint)
    try:
        return subprocess.run(argv, capture_output=True, check=True, timeout=timeout)
    except OSError as error:
        raise TargumError("yt-dlp is not installed.", hint) from error
    except subprocess.TimeoutExpired as error:
        raise TargumError("yt-dlp did not answer in time, so it was stopped.") from error
    except subprocess.CalledProcessError as error:
        raise TargumError(_said(error, "yt-dlp could not read that video.")) from error


def describe(url: str) -> dict[str, Any]:
    """What yt-dlp knows about the video without fetching it: `yt-dlp -J`.

    Duration, a language tag per format, which subtitle tracks somebody wrote and
    which YouTube guessed, and the licence the uploader set. This is what
    `screen.from_ytdlp` reads, and it is metadata only — a few hundred kilobytes of
    JSON, never the video.
    """
    done = _run(["yt-dlp", "-J", "--no-playlist", "--skip-download", url], timeout=120)
    try:
        answer: dict[str, Any] = json.loads(done.stdout.decode("utf-8", "replace"))
    except json.JSONDecodeError as error:
        raise TargumError("yt-dlp answered with something that is not JSON.") from error
    return answer


def fetch_subtitles(url: str, into: Path, languages: tuple[str, ...] = ("he", "iw")) -> Path:
    """The manual subtitle track in one of these languages, written into `into`.

    Manual only: `--write-auto-subs` is not passed, because a track YouTube guessed
    is not a transcript anybody checked, and the screen is looking for exactly the
    mismatch a guess would paper over. SRT first, then VTT — both parse the same.
    """
    into.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "yt-dlp",
            "--skip-download",
            "--no-playlist",
            "--write-subs",
            "--sub-langs",
            ",".join(languages),
            "--sub-format",
            "srt/vtt/best",
            "-o",
            str(into / "%(id)s.%(ext)s"),
            url,
        ],
        timeout=300,
    )
    written = sorted(p for p in into.iterdir() if p.suffix.lower() in (".srt", ".vtt"))
    if not written:
        raise TargumError(
            "That video has no subtitle track anybody wrote in " + ", ".join(languages) + "."
        )
    return written[0]
