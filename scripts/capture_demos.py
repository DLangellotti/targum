"""Short demo clips of what targum does, cut for X, Instagram and YouTube Shorts.

Four clips, one per thing worth showing: a link becoming a lesson, the vowel switch,
a word coming apart under a tap, and the conversation that answers in Hebrew. Each is
the real product driven in a real browser at phone size — nothing is mocked up, so a
clip that goes stale is a clip that tells you the screen changed.

Silent, with the words burned in, because that is how a muted feed is watched.

It needs a `targum serve` already running on this machine, and the key that serve
printed when it started:

    .venv/bin/python -m targum serve --no-open --port 8788
    uv run python scripts/capture_demos.py --key <the key it printed>

The first run signs in through the console link the serve writes to its own stdout, so
point `--log` at wherever you sent that output. The session is kept in the work
directory and reused, because sign-in links are rate-limited per address.

    --clip vowels      just one of them
    --out DIR          where the mp4s land (default: targum-out/demos)

Nothing here spends: it opens texts that are already built and never presses Continue
on the Add box. The one thing it cannot show live is a build finishing, so the first
clip cuts from the pasted link to the reader that link really did produce.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Page

# The canvas every platform takes: 9:16, and the phone sat inside it with the words
# above. Reels, Shorts and X all play this without letterboxing it a second time.
CANVAS = (1080, 1920)
PHONE = (390, 844)
VIEWPORT = {"width": PHONE[0], "height": PHONE[1]}
#: The phone drawn at this width inside the canvas, and where its top edge sits.
PHONE_W = 720
PHONE_Y = 306

#: design.md §4. Desk is the ground the phone stands on; ink and muted are the words.
DESK = "#ece7de"
INK = "#1c1a17"
MUTED = "#6b645c"
RULE = "#e2dcd1"

#: design.md §5 — the reading face is the brand, so the words on these use it.
READING = '"Iowan Old Style", "Palatino Linotype", Palatino, Georgia, "Times New Roman", serif'

EMAIL = "djvlbass@gmail.com"
SCENE = "באוטובוס-he/reader/index.html"
#: The page this reader was really built from, so the link pasted in the first clip is
#: the link that produced the page the clip cuts to, and the cut claims nothing false.
LESSON = "מגילת-העצמאות-של-מדינת-ישראל-he/reader/index.html"
LESSON_LINK = "https://he.wikisource.org/wiki/מגילת_העצמאות_של_מדינת_ישראל"

#: The switch that puts the points on and takes them off, named the same in every reader.
VOWELS = '[aria-label="Vowel points"]'


@dataclass
class Beat:
    """One line of burned-in words, and how long it holds."""

    words: str
    seconds: float
    under: str = ""


@dataclass
class Segment:
    """One recorded page. `drive` does the acting; the rest is bookkeeping."""

    name: str
    drive: Callable[[Page, Clip], None]
    lead: float = 0.0
    length: float = 0.0
    video: Path | None = None


@dataclass
class Clip:
    name: str
    beats: list[Beat]
    segments: list[Segment]
    marks: dict[str, float] = field(default_factory=dict)

    def mark(self, key: str, when: float) -> None:
        self.marks[key] = when


# ---------------------------------------------------------------- signing in


def sign_in_link(base: str, key: str, log: Path) -> str:
    """Ask for a link, then read it out of the serve's own stdout."""
    was = log.stat().st_size if log.exists() else 0
    request = urllib.request.Request(
        f"{base}/account/sign-in?k={key}",
        data=json.dumps({"email": EMAIL}).encode(),
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(request) as answer:
        answer.read()
    for _ in range(60):
        time.sleep(0.5)
        if not log.exists():
            continue
        fresh = log.read_bytes()[was:].decode("utf-8", "replace")
        found = re.search(r"(https?://\S+/account/enter\?t=\S+)", fresh)
        if found:
            return found.group(1)
    raise SystemExit(f"No sign-in link appeared in {log}. Is that where the serve's output goes?")


def session(work: Path, base: str, key: str, log: Path, browser: Any) -> Path:
    """The saved session, signing in first if there is not one that still works."""
    state = work / "session.json"
    if state.exists():
        context = browser.new_context(storage_state=str(state), viewport=VIEWPORT)
        page = context.new_page()
        page.goto(f"{base}/?k={key}", wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")
        good = page.query_selector("text=Sign in") is None
        context.close()
        if good:
            return state
        print("  the saved session has expired, signing in again")
    context = browser.new_context(viewport=VIEWPORT)
    page = context.new_page()
    page.goto(sign_in_link(base, key, log), wait_until="domcontentloaded")
    page.click("button.go")
    page.wait_for_load_state("networkidle")
    context.storage_state(path=str(state))
    context.close()
    return state


# ---------------------------------------------------------------- the acting
#
# Every one of these holds still before it does anything and holds still after, so the
# cut has clean frames at both ends and nothing important happens under a caption
# change. `beat` is the pause; it is deliberate and it is why these read as calm.


def beat(page: Page, seconds: float = 0.8) -> None:
    page.wait_for_timeout(int(seconds * 1000))


def settled(page: Page, url: str, wait: float = 2.0) -> None:
    page.goto(url, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=45_000)
    except Exception:  # noqa: BLE001 — a page that keeps a socket open is still ready
        pass
    beat(page, wait)


def drive_add(page: Page, clip: Clip) -> None:
    """The Add box, taking a link. It stops before Continue: pressing it would open a
    price, and a price is not what a sneak peek is for."""
    settled(page, page.url)
    page.click("#given")
    beat(page, 0.5)
    clip.mark("typing", time.monotonic())
    page.type("#given", LESSON_LINK, delay=55)
    beat(page, 1.6)


def drive_lesson(page: Page, clip: Clip) -> None:
    """What that link became. A modern text opens bare, because bare is how it was
    written, so the points go on here — which is the half of the caption a reader would
    otherwise have to take on trust."""
    settled(page, page.url, wait=2.0)
    clip.mark("reading", time.monotonic())
    beat(page, 2.0)
    if page.get_attribute(VOWELS, "aria-pressed") != "true":
        page.click(VOWELS)
    beat(page, 3.0)
    page.mouse.wheel(0, 260)
    beat(page, 2.4)


def drive_vowels(page: Page, clip: Clip) -> None:
    """One switch, off and back on. It holds on the pointed text first, because the
    whole point is the difference and nobody sees a difference they never saw the first
    half of. It ends pointed, which is how a text opens."""
    settled(page, page.url)
    clip.mark("holding", time.monotonic())
    beat(page, 2.2)
    page.click(VOWELS)
    beat(page, 3.0)
    page.click(VOWELS)
    beat(page, 2.4)


def drive_word(page: Page, clip: Clip) -> None:
    """A verb, tapped, and the card that rises under it."""
    settled(page, page.url)
    words = page.eval_on_selector_all(".w", "els => els.map(e => e.textContent)")
    wanted = next((i for i, w in enumerate(words) if "יוֹרֶ" in w), 0)
    clip.mark("waiting", time.monotonic())
    beat(page, 2.6)
    page.eval_on_selector_all(".w", f"els => els[{wanted}].click()")
    beat(page, 4.8)


def drive_talk(page: Page, clip: Clip) -> None:
    """The conversation, and the correction in it. It reveals what is already there
    rather than sending a turn, because a turn is a job and a job spends."""
    settled(page, page.url, wait=2.5)
    clip.mark("reading", time.monotonic())
    beat(page, 1.5)
    page.mouse.wheel(0, -500)
    beat(page, 1.4)
    page.mouse.wheel(0, -400)
    beat(page, 3.4)
    page.mouse.wheel(0, 300)
    beat(page, 2.6)


def clips(base: str, key: str) -> list[Clip]:
    return [
        Clip(
            name="paste",
            beats=[
                Beat("Paste a link to anything in Hebrew.", 4.5),
                Beat("Read it with the vowels and the English.", 6.0),
            ],
            segments=[
                Segment("add", drive_add),
                Segment("lesson", drive_lesson),
            ],
        ),
        Clip(
            name="vowels",
            beats=[
                Beat("Vowels while you are learning.", 4.0),
                Beat("Off when you are ready for them to go.", 6.0),
            ],
            segments=[Segment("scene", drive_vowels)],
        ),
        Clip(
            name="word",
            beats=[
                Beat("Hebrew packs a lot into one word.", 3.0),
                Beat("Tap it, and it comes apart.", 5.5),
            ],
            segments=[Segment("scene", drive_word)],
        ),
        Clip(
            name="talk",
            beats=[
                Beat("Write to us in Hebrew.", 3.5),
                Beat("We answer in Hebrew, and show you the fix.", 6.5),
            ],
            segments=[Segment("chat", drive_talk)],
        ),
    ]


def where(segment: Segment, base: str, key: str) -> str:
    return {
        "add": f"{base}/add?k={key}",
        "lesson": f"{base}/reader/{LESSON}?k={key}",
        "scene": f"{base}/reader/{SCENE}?k={key}",
        "chat": f"{base}/chat?k={key}",
    }[segment.name]


# ---------------------------------------------------------------- recording


def record(clip: Clip, base: str, key: str, work: Path, state: Path, browser: Any) -> None:
    """One context per segment, because Playwright writes one video per context."""
    for segment in clip.segments:
        shot = work / "raw" / f"{clip.name}-{segment.name}"
        shot.mkdir(parents=True, exist_ok=True)
        for old in shot.glob("*.webm"):
            old.unlink()
        context = browser.new_context(
            storage_state=str(state),
            viewport={"width": PHONE[0], "height": PHONE[1]},
            device_scale_factor=2,
            record_video_dir=str(shot),
            record_video_size={"width": PHONE[0] * 2, "height": PHONE[1] * 2},
        )
        page = context.new_page()
        started = time.monotonic()
        page.goto(where(segment, base, key), wait_until="domcontentloaded")
        clip.marks.clear()
        segment.drive(page, clip)
        ended = time.monotonic()
        context.close()

        # Trim to just before the first thing worth watching. The page loading is
        # recorded too and nobody needs to see it.
        first = min(clip.marks.values()) if clip.marks else started
        segment.lead = max(0.0, first - started - 0.45)
        segment.length = max(1.0, ended - started - segment.lead)
        made = sorted(shot.glob("*.webm"))
        if not made:
            raise SystemExit(f"Playwright recorded nothing for {clip.name}/{segment.name}")
        segment.video = made[0]
        print(
            f"  {clip.name}/{segment.name}: {segment.length:.1f}s"
            f" (dropped {segment.lead:.1f}s of loading)"
        )


# ---------------------------------------------------------------- the words
#
# The caption frames are drawn by the browser rather than by ffmpeg, so they are set in
# the brand's own face at the brand's own colours instead of whatever font a filter
# happens to find. Each frame is the whole canvas: desk everywhere, a rounded hole where
# the phone shows through, and the words above it.


OVERLAY = """
<!doctype html><meta charset="utf-8">
<style>
  html, body {{ margin: 0; width: {w}px; height: {h}px; background: transparent; }}
  /* The hole. Everything outside the rounded rect is filled by the spread of the
     shadow, so one element both masks the canvas and rounds the phone's corners. */
  .window {{
    position: absolute; left: {x}px; top: {y}px; width: {pw}px; height: {ph}px;
    border-radius: 30px; box-shadow: 0 0 0 9999px {desk}; border: 1px solid {rule};
    box-sizing: border-box;
  }}
  /* Above the mask, because the mask's spread paints over everything it is drawn
     after and the words would go under it. */
  .words {{
    position: absolute; left: 0; top: 0; width: {w}px; height: {y}px; z-index: 2;
    display: flex; flex-direction: column; align-items: center;
    justify-content: center; gap: 18px; padding: 0 90px; box-sizing: border-box;
    font-family: {reading}; text-align: center; text-wrap: balance;
  }}
  .line {{ font-size: 58px; line-height: 1.12; font-weight: 600; color: {ink}; margin: 0; }}
  .under {{ font-size: 34px; line-height: 1.3; color: {muted}; margin: 0; }}
</style>
<div class="window"></div>
<div class="words"><p class="line">{words}</p>{under}</div>
"""


def frames(clip: Clip, work: Path, browser: Any) -> list[Path]:
    made: list[Path] = []
    context = browser.new_context(
        viewport={"width": CANVAS[0], "height": CANVAS[1]}, device_scale_factor=1
    )
    page = context.new_page()
    phone_h = round(PHONE[1] * PHONE_W / PHONE[0])
    for number, one in enumerate(clip.beats):
        html = OVERLAY.format(
            w=CANVAS[0],
            h=CANVAS[1],
            x=(CANVAS[0] - PHONE_W) // 2,
            y=PHONE_Y,
            pw=PHONE_W,
            ph=phone_h,
            desk=DESK,
            rule=RULE,
            ink=INK,
            muted=MUTED,
            reading=READING,
            words=one.words,
            under=f'<p class="under">{one.under}</p>' if one.under else "",
        )
        page.set_content(html)
        page.wait_for_timeout(250)
        out = work / "frames" / f"{clip.name}-{number}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out), omit_background=True)
        made.append(out)
    context.close()
    return made


# ---------------------------------------------------------------- the cut


def cut(clip: Clip, overlays: list[Path], out: Path) -> Path:
    """Phone footage on a desk-coloured canvas, with the words over the top."""
    phone_h = round(PHONE[1] * PHONE_W / PHONE[0])
    x = (CANVAS[0] - PHONE_W) // 2
    total = sum(s.length for s in clip.segments)

    command: list[str] = ["ffmpeg", "-y", "-v", "error"]
    for segment in clip.segments:
        assert segment.video is not None
        command += [
            "-ss",
            f"{segment.lead:.3f}",
            "-t",
            f"{segment.length:.3f}",
            "-i",
            str(segment.video),
        ]
    for one in overlays:
        command += ["-i", str(one)]

    steps: list[str] = []
    count = len(clip.segments)
    for index in range(count):
        steps.append(
            f"[{index}:v]scale={PHONE_W}:{phone_h}:flags=lanczos,setsar=1,fps=30[p{index}]"
        )
    if count > 1:
        steps.append("".join(f"[p{i}]" for i in range(count)) + f"concat=n={count}:v=1:a=0[phone]")
    else:
        steps.append("[p0]copy[phone]")
    steps.append(f"color=c={DESK}:s={CANVAS[0]}x{CANVAS[1]}:d={total:.3f}:r=30[bg]")
    steps.append(f"[bg][phone]overlay={x}:{PHONE_Y}:shortest=1[stage]")

    # A clip with one caption per segment changes caption exactly where it cuts, and
    # the written seconds are ignored. Anything else keeps its own timing. Without this
    # the second line of a two-shot clip arrives over the tail of the first shot, which
    # reads as a caption for the wrong picture.
    aligned = len(clip.beats) == count > 1
    at = 0.0
    last = "stage"
    for number, one in enumerate(clip.beats):
        if number == len(clip.beats) - 1:
            until = total
        elif aligned:
            until = sum(s.length for s in clip.segments[: number + 1])
        else:
            until = at + one.seconds
        label = f"v{number}"
        steps.append(
            f"[{last}][{count + number}:v]overlay=0:0:"
            f"enable='between(t,{at:.3f},{until:.3f})'[{label}]"
        )
        last, at = label, until

    command += [
        "-filter_complex",
        ";".join(steps),
        "-map",
        f"[{last}]",
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "19",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-an",
        str(out),
    ]
    subprocess.run(command, check=True)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", required=True, help="the key the running serve printed")
    parser.add_argument("--base", default="http://127.0.0.1:8788")
    parser.add_argument("--log", type=Path, help="where the serve's output goes (for signing in)")
    parser.add_argument("--out", type=Path, default=Path("targum-out/demos"))
    parser.add_argument("--work", type=Path, default=Path("targum-out/demos/work"))
    parser.add_argument("--clip", action="append", help="just these, by name")
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        print("No ffmpeg on the path. brew install ffmpeg", file=sys.stderr)
        return 1
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "No Playwright. uv sync --extra browser && uv run playwright install chromium",
            file=sys.stderr,
        )
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    args.work.mkdir(parents=True, exist_ok=True)
    wanted = clips(args.base, args.key)
    if args.clip:
        wanted = [c for c in wanted if c.name in args.clip]
        if not wanted:
            print(
                f"No clip by that name. There are: {', '.join(c.name for c in clips('', ''))}",
                file=sys.stderr,
            )
            return 1

    made: list[Path] = []
    with sync_playwright() as play:
        browser = play.chromium.launch(args=["--hide-scrollbars", "--force-device-scale-factor=2"])
        state = session(args.work, args.base, args.key, args.log or Path("/dev/null"), browser)
        for clip in wanted:
            print(clip.name)
            record(clip, args.base, args.key, args.work, state, browser)
            overlays = frames(clip, args.work, browser)
            out = cut(clip, overlays, args.out / f"targum-{clip.name}.mp4")
            print(f"  -> {out}")
            made.append(out)
        browser.close()

    print(f"\n{len(made)} clip(s) in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
