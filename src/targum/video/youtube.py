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
import os
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

#: Where YouTube is fetched *from*, and on a datacenter box the only thing that works.
#:
#: What was measured on 2026-09-04, in order, all on targum.page (Hetzner AS24940,
#: Falkenstein):
#:
#: * The same video answered `yt-dlp -J` on a laptop and came back "Sign in to confirm
#:   you're not a bot" on the box. So it is the address, not the video and not the binary.
#: * A JavaScript runtime and a proof-of-origin minter were both installed. Neither
#:   helped, together or apart.
#: * Every player client — tv, tv_simply, web_safari, mweb, web_embedded, android, ios —
#:   failed, and so did `jNQXAC9IVRw` ("Me at the zoo", 2005, no restrictions), which is
#:   the control that rules out anything about the video.
#: * `-4` and `-6` both failed, so it is the whole address and not one family of it.
#:
#: YouTube has flagged the range, which is what Hetzner is known for. Nothing that runs
#: *on* the box can answer that; the fetch has to leave from somewhere else. So this is
#: the knob that matters, and every remaining option — a residential proxy, a tunnel to a
#: home line, a SOCKS exit on a machine that already works — is the same one line here.
#:
#: Not cookies. That would be a Google session living on the box, refreshed by hand,
#: fetching on behalf of strangers, with a ban as the failure mode. A proxy is an egress
#: and nothing else: no account, no identity, nothing to suspend. That is the whole
#: difference, and it is why this door is open and that one is not.
#:
#: Empty is a laptop, whose own address YouTube trusts. Anything yt-dlp understands
#: works: `socks5://127.0.0.1:1080`, `http://user:pass@host:port`.
YTDLP_PROXY_ENV = "TARGUM_YTDLP_PROXY"

#: The proof-of-origin token minter, kept because it is installed, correct, and free.
#:
#: It does not answer the block above and was never going to: a PO token answers "PO
#: token required" — missing formats, a 403 on a media URL — and the extractor never
#: reaches that stage on a flagged address. It is left wired because it costs nothing,
#: because it is the right thing to have once a working egress exists, and because
#: `preflight` can then say which of the two halves is missing.
#:
#: `bgutil-ytdlp-pot-provider` runs beside targum on the loopback and yt-dlp reaches it
#: through its own plugin. Named here rather than left to the plugin's default so that
#: the box's setting sits in `targum.env` with every other knob, and so `preflight` has
#: an address to knock on.
POT_PROVIDER_ENV = "TARGUM_POT_PROVIDER"

#: What a sentence has to be free of before a reader is shown it. yt-dlp's last line is
#: usually a fact about the video — "Private video.", "Video unavailable" — and better
#: than anything written here. Sometimes it is a note to whoever runs the binary, naming
#: flags to pass and wiki pages to read, and that is addressed to the operator: a reader
#: cannot pass `--cookies` to anything and design.md §6 does not answer questions nobody
#: asked. The tell is cheap and does not need a list of YouTube's refusals kept current.
_TO_THE_OPERATOR = (" --", "http://", "https://")

#: What still works when YouTube will not answer, in the reader's terms. A video file
#: uploads through the same door a recording does, hosted included — so "YouTube links
#: are CLI-only" would be the wrong sentence here, and so would silence.
OTHER_DOOR = "A video file uploads."


def proxy() -> str:
    """Where YouTube is fetched from, or "" for from here."""
    return os.environ.get(YTDLP_PROXY_ENV, "").strip()


def pot_provider() -> str:
    """The token minter's address, or "" where there is none."""
    return os.environ.get(POT_PROVIDER_ENV, "").strip()


def _extra_args() -> list[str]:
    """Everything this box has to add to a yt-dlp command line, and nothing where it
    has to add nothing — an unset knob must not become a flag, because a flag naming a
    proxy that is not listening is a fetch that fails on a machine where it worked."""
    args = []
    if where := proxy():
        args += ["--proxy", where]
    if provider := pot_provider():
        args += ["--extractor-args", f"youtubepot-bgutilhttp:base_url={provider}"]
    return args


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
                *_extra_args(),
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
        raise _refusal(error, "YouTube would not hand targum that video.") from error
    if not target.is_file():
        raise TargumError("yt-dlp fetched nothing it could merge to mp4.")
    if target.stat().st_size > MAX_VIDEO_BYTES:
        target.unlink()
        raise TargumError("That video is larger than 4 GB.")
    return target


def _said(error: subprocess.CalledProcessError) -> str:
    """yt-dlp's own sentence, where it is one a reader can be shown. Otherwise "".

    The binary's last line is usually the honest one — an age gate, a private video, a
    region block — and better than anything written here, so it is carried where it is
    a fact about the video. Where it is a note to whoever runs the binary it is dropped,
    because the alternative is what a reader was shown on 2026-09-04: a paragraph naming
    `--cookies-from-browser` and two GitHub wiki pages, on a page whose only other words
    are "Drop a book, an article, or a recording".
    """
    said = (error.stderr or b"").decode("utf-8", "replace").strip().splitlines()
    for line in reversed(said):
        # Only what yt-dlp itself called an error. Reading past it to the line above
        # would hand a reader a WARNING as the reason the import stopped, which is a
        # different untruth from the one being fixed.
        if not line.startswith("ERROR:"):
            continue
        sentence = line.removeprefix("ERROR:").strip()
        return sentence if not any(tell in sentence for tell in _TO_THE_OPERATOR) else ""
    return ""


def _refusal(error: subprocess.CalledProcessError, fallback: str) -> TargumError:
    """What the reader is told when yt-dlp stopped.

    The hint rides only targum's own sentence. "Private video." is already the whole
    answer and naming a second door after it answers a question nobody asked; a reader
    who has just been told something vague is the one who needs to know what else works.
    """
    sentence = _said(error)
    return TargumError(sentence) if sentence else TargumError(fallback, OTHER_DOOR)


def _run(argv: list[str], *, timeout: int) -> subprocess.CompletedProcess[bytes]:
    if not is_youtube(argv[-1]):
        raise TargumError("That address is not a YouTube video.")
    usable, hint = ytdlp_available()
    if not usable:
        raise TargumError("yt-dlp is not installed.", hint)
    # Ahead of the address, which `is_youtube` above read off the end and which yt-dlp
    # wants last of all.
    argv = [*argv[:-1], *_extra_args(), argv[-1]]
    try:
        return subprocess.run(argv, capture_output=True, check=True, timeout=timeout)
    except OSError as error:
        raise TargumError("yt-dlp is not installed.", hint) from error
    except subprocess.TimeoutExpired as error:
        raise TargumError("yt-dlp did not answer in time, so it was stopped.") from error
    except subprocess.CalledProcessError as error:
        raise _refusal(error, "YouTube would not tell targum about that video.") from error


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
