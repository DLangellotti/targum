"""Re-voice the whole scene shelf with `voice_scenes.py`'s pipeline, inside a spend cap.

David heard he-06 voiced the new way on 2026-10-29 ("the after is much better") and
approved the whole shelf: 381 scenes, 5,198 turns, Hebrew and Russian
(targum-internal#566). `voice_scenes.py` voices a scene; this walks the shelf with it, and
adds what a run of five thousand paid requests needs that a run of fourteen does not.

- **A cap.** `--cap` dollars, $30 unless told otherwise, counted per turn as it is bought,
  director calls included, and a request cut off at its deadline counted at an average
  turn's price, since it may have been billed. The run stops at the turn that reaches it, and that turn is
  already on disk, so nothing paid for is lost and the next run picks up there.
- **The quota, as Vertex states it.** A 429's body names the limit it hit and how long to
  wait. A per-minute limit is waited out where it is and the run goes on. A limit that
  outlasts the backoff pauses the run for `--pause` seconds, then resumes the same scene.
  A per-day one, known by a PerDay quota name or a wait over ten minutes, is slept off
  until the midnight-Pacific reset, up to `--wait-daily` hours, and the run resumes; a
  third per-day refusal on the same scene stops the run. Every 429
  is kept in the progress file with the limit it named.
- **Russian.** A `ru-` scene's director is told the conversation is in Russian, and its
  lines get no Hebrew pronunciation hints. A speaker whose voice is missing, unknown, or
  of the other gender gets the shelf's usual voice for that language and gender (Leda or
  Charon for Hebrew, Kore or Orus for Russian), and the dry run lists every such change.
- **A progress file.** `--into/progress.json`, rewritten atomically after every scene and
  every bought turn: what is done, what failed and why, what was spent, the last quota
  seen, and what the run is waiting for.
- **A dry run.** Counts by language, what is left to voice, requests, an estimated cost and
  time, and every prompt that would be refused for length. It calls nothing.

A scene is done when its mp3 and seams sidecar are in `--into` and its progress entry was
made from the same words and voices. Turns already bought are reused either way.

    python scripts/voice_shelf.py --from targum-out/dialogues --into voiced-shelf --dry-run
    op run --env-file op.env -- python scripts/voice_shelf.py \\
        --from targum-out/dialogues --into voiced-shelf --cap 30

It writes only into `--into`. Putting the result on the shelf is `place_scene_voices.py`.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import voice_scenes as vs  # noqa: E402

from targum.dialogue.checks import voice_gender  # noqa: E402

CAP = 30.0
#: The shelf's usual voices, for a speaker whose own is missing, unknown or the wrong
#: gender: the pair chosen by ear for Hebrew in 2026-08, and for Russian the female and
#: male voices its scenes already use most.
VOICES = {"he": {"f": "Leda", "m": "Charon"}, "ru": {"f": "Kore", "m": "Orus"}}
#: Per-turn reads run longer than the whole-scene audio they replace: 23% on
#: 81-the-army-friend (2026-09-22), 2% on he-06 (2026-10-29). The estimate takes the worse.
SLOWER = 1.25
#: About what one director call costs: a scene in, a few words a turn out, at Haiku's rate.
DIRECTOR_EACH = 0.003
#: Seconds a request takes to come back, on top of --spacing, for the time estimate.
LATENCY = 4.0
#: When a per-minute limit is still there after `say`'s own backoff: wait this, then go on.
PAUSE = 300.0
#: How many such pauses one scene may take before it is marked failed and passed over.
PAUSES = 6
#: The longest per-day wait slept through, in hours, before the run stops instead.
WAIT_DAILY = 26.0


class CapReached(RuntimeError):
    """The spend cap is reached. The turn that reached it is on disk."""


def until_reset(at: datetime | None = None) -> float:
    """Seconds to the next midnight Pacific, when Google's per-day quotas reset."""
    pacific = ZoneInfo("America/Los_Angeles")
    here = (at or datetime.now(UTC)).astimezone(pacific)
    midnight = (here + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    return (midnight - here).total_seconds()


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def language(scene: dict[str, Any]) -> str:
    return str(scene.get("language") or ("ru" if scene["id"].startswith("ru-") else "he"))


def cast_for(scene: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """The scene with a voice for every speaker that can read them, and what was changed.

    The scene files are not touched: this is a copy, used for the requests only."""
    fixed = copy.deepcopy(scene)
    fixed["language"] = language(scene)
    usual = VOICES.get(fixed["language"], VOICES["he"])
    notes = []
    for side, who in fixed["cast"].items():
        gender = who.get("gender") if who.get("gender") in ("f", "m") else ""
        voice = str(who.get("voice") or "")
        said = voice_gender(voice) if voice else ""
        if voice and said and (not gender or said == gender):
            continue
        if not gender:
            gender = said or "f"
        why = (
            "no voice"
            if not voice
            else f"{voice} is not a known voice"
            if not said
            else f"{voice} is {said}, the speaker {gender}"
        )
        who["voice"] = usual[gender]
        notes.append(f"{scene['id']} {side}: {why}; read by {usual[gender]}")
    return fixed, notes


def scene_key(scene: dict[str, Any]) -> str:
    """The words and voices a scene was voiced from, so a done scene that has since
    changed is done again."""
    made = (
        [[t["who"], t["text"]] for t in scene["turns"]],
        {k: v.get("voice") for k, v in scene["cast"].items()},
    )
    return hashlib.sha256(json.dumps(made, ensure_ascii=False).encode()).hexdigest()[:16]


def speech_seconds(scene: dict[str, Any]) -> float:
    """Seconds of speech in the audio the scene has today, or a guess from its length."""
    total = 0.0
    for turn in scene["turns"]:
        start, end = turn.get("start"), turn.get("end")
        if isinstance(start, int | float) and isinstance(end, int | float) and end > start:
            total += end - start
        else:
            # About fourteen characters a second, pointing stripped, in either language.
            total += len(vs.POINTS.sub("", turn["text"])) / 14
    return total


class Progress:
    """`progress.json`: the run's state, written whole after every change."""

    def __init__(self, path: Path, cap: float) -> None:
        self.path = path
        self.data: dict[str, Any] = {}
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))
        before = float(self.data.get("spent_total", 0.0))
        self.data.update(
            {
                "cap": cap,
                "run_started": now(),
                "spent_this_run": 0.0,
                "spent_before": before,
                "spent_total": before,
                "current": None,
                "waiting_until": None,
                "stopped": None,
            }
        )
        self.data.setdefault("scenes", {})
        self.data.setdefault("quota", {"count_429": 0, "last": None})
        self.data.setdefault("cut_off", 0)

    @property
    def spent(self) -> float:
        return float(self.data["spent_this_run"])

    def spend(self, dollars: float) -> None:
        self.data["spent_this_run"] = round(self.spent + dollars, 6)
        self.data["spent_total"] = round(self.data["spent_before"] + self.spent, 6)
        self.save()

    def scene(self, sid: str, **fields: Any) -> None:
        self.data["scenes"][sid] = {**self.data["scenes"].get(sid, {}), **fields, "at": now()}
        self.save()

    def quota(self, quota: vs.Quota) -> None:
        seen = self.data["quota"]
        seen["count_429"] = int(seen.get("count_429", 0)) + 1
        seen["last"] = {
            "at": now(),
            "said": str(quota),
            "message": quota.message,
            "retry_after": quota.retry_after,
            "limits": quota.limits,
        }
        self.save()

    def set(self, **fields: Any) -> None:
        self.data.update(fields)
        self.save()

    def save(self) -> None:
        self.data["updated"] = now()
        vs.write_atomically(
            self.path, (json.dumps(self.data, ensure_ascii=False, indent=2) + "\n").encode()
        )

    def done(self, scene: dict[str, Any], into: Path) -> bool:
        entry = self.data["scenes"].get(scene["id"], {})
        return (
            entry.get("state") == "done"
            and entry.get("key") == scene_key(scene)
            and (into / f"{scene['id']}.mp3").exists()
            and (into / f"{scene['id']}.seams.json").exists()
        )


def load(source: Path, languages: list[str], only: list[str]) -> list[dict[str, Any]]:
    scenes = []
    for path in sorted(source.glob("*.json")):
        try:
            scene = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if not isinstance(scene, dict) or not scene.get("turns") or not scene.get("cast"):
            continue
        if languages and language(scene) not in languages:
            continue
        if only and scene["id"] not in only:
            continue
        scenes.append(scene)
    return scenes


def dry_run(
    scenes: list[dict[str, Any]], into: Path, progress: Progress, spacing: float, cap: float
) -> None:
    by_language: Counter[str] = Counter()
    left: list[dict[str, Any]] = []
    notes: list[str] = []
    refused: list[str] = []
    for scene in scenes:
        by_language[language(scene)] += 1
        fixed, changed = cast_for(scene)
        notes += changed
        for n in range(len(fixed["turns"])):
            try:
                vs.prompt_for(fixed, n, "x" * vs.DIRECTION_MOST)
            except vs.TooLong as long:
                refused.append(str(long))
        if not progress.done(fixed, into):
            left.append(fixed)
    turns = sum(len(s["turns"]) for s in left)
    seconds = sum(speech_seconds(s) for s in left)
    today = seconds / 60 * vs.PER_MINUTE + DIRECTOR_EACH * len(left)
    slower = seconds * SLOWER / 60 * vs.PER_MINUTE + DIRECTOR_EACH * len(left)
    hours = turns * (spacing + LATENCY) / 3600
    print(f"{len(scenes)} scenes: " + ", ".join(f"{n} {k}" for k, n in sorted(by_language.items())))
    print(f"{len(scenes) - len(left)} already voiced in {into}; {len(left)} to voice")
    print(f"{turns} turns, so {turns} TTS requests and {len(left)} director calls")
    print(f"{seconds / 60:.1f} minutes of speech today")
    print(f"estimated ${today:.2f} at today's lengths, ${slower:.2f} if reads run 25% slower")
    print(f"the cap is ${cap:.2f}: " + ("enough" if slower <= cap else "it will stop short"))
    print(f"about {hours:.1f} hours at --spacing {spacing:g}, before any 429")
    for one in notes:
        print(f"  voice: {one}")
    for one in refused:
        print(f"  REFUSED {one}")
    print("Nothing was called. Drop --dry-run to run it.")


def run(
    scenes: list[dict[str, Any]],
    into: Path,
    progress: Progress,
    tts_key: str,
    director_key: str,
    args: argparse.Namespace,
    sleep: Callable[[float], None] = time.sleep,
    direct: Callable[..., tuple[list[str], float]] = vs.direct,
    voice: Callable[..., tuple[list[list[float]], float, float]] = vs.voice,
) -> None:
    store = into / "directions"
    left = [s for s in (cast_for(s)[0] for s in scenes) if not progress.done(s, into)]
    print(f"{len(left)} scenes to voice; cap ${args.cap:.2f}", flush=True)

    def bought(seconds: float) -> None:
        progress.spend(seconds / 60 * vs.PER_MINUTE)
        if progress.spent >= args.cap:
            raise CapReached(f"${progress.spent:.2f} spent, the cap is ${args.cap:.2f}")

    current: dict[str, Any] = {}

    def cut_off(_: vs.CutOff) -> None:
        # Nothing came back to measure, but the model may have spoken the whole line
        # before the answer stalled, so it counts toward the cap at an average turn of
        # this scene, read SLOWER.
        scene_now = current["scene"]
        guess = speech_seconds(scene_now) / len(scene_now["turns"]) * SLOWER / 60 * vs.PER_MINUTE
        progress.set(
            cut_off=int(progress.data["cut_off"]) + 1,
            cut_off_estimate=round(float(progress.data.get("cut_off_estimate", 0.0)) + guess, 6),
        )
        progress.spend(guess)
        if progress.spent >= args.cap:
            raise CapReached(
                f"${progress.spent:.2f} spent (cut-offs included), cap ${args.cap:.2f}"
            )

    for count, scene in enumerate(left, 1):
        sid = scene["id"]
        if progress.spent + DIRECTOR_EACH >= args.cap:
            progress.set(stopped=f"cap: ${progress.spent:.2f} of ${args.cap:.2f}", current=None)
            print(f"\nstopped at the cap before {sid}", flush=True)
            return
        print(f"\n[{count}/{len(left)}] {sid}", flush=True)
        progress.set(current=sid)
        current["scene"] = scene
        pauses = 0
        dailies = 0
        while True:
            try:
                directions, cost = direct(scene, director_key, store) if director_key else (None, 0)
                if cost:
                    progress.spend(cost)
                spans, seconds, paid = voice(
                    scene,
                    tts_key,
                    into,
                    args.spacing,
                    args.via,
                    args.deadline,
                    cut_off,
                    directions,
                    progress.quota,
                    bought,
                )
            except CapReached as reached:
                progress.scene(sid, state="partial", reason=str(reached))
                progress.set(stopped=f"cap: {reached}", current=None)
                print(f"\nstopped: {reached}. The turns bought are kept.", flush=True)
                return
            except vs.Daily as gone:
                dailies += 1
                # A per-day limit resets at midnight Pacific, whatever retryDelay says: a
                # PerDay quota has been seen asking for 17s. So the wait is the later of
                # the two, and a second refusal right after a reset stops the run.
                wait = max(gone.quota.retry_after or 0.0, until_reset())
                if dailies > 2 or wait > args.wait_daily * 3600:
                    progress.set(stopped=f"per-day quota: {gone.quota}", current=None)
                    print(f"\nstopped: the day's quota is gone ({gone.quota})", flush=True)
                    return
                until = datetime.fromtimestamp(time.time() + wait, UTC)
                progress.set(waiting_until=until.isoformat(timespec="seconds"))
                print(f"  per-day quota ({gone.quota}); sleeping until {until:%H:%M} UTC")
                sleep(wait)
                progress.set(waiting_until=None)
                continue
            except vs.Throttled as limited:
                pauses += 1
                if pauses > PAUSES:
                    progress.scene(sid, state="failed", reason=f"throttled: {limited.quota}")
                    break
                progress.set(waiting_until=f"{args.pause:.0f}s after {now()}")
                print(f"  still limited ({limited.quota}); pausing {args.pause:.0f}s", flush=True)
                sleep(args.pause)
                progress.set(waiting_until=None)
                continue
            except (vs.CutOff, vs.TooLong, RuntimeError, OSError) as failed:
                progress.scene(sid, state="failed", reason=f"{type(failed).__name__}: {failed}")
                print(f"  failed: {failed}", flush=True)
                break
            (into / f"{sid}.spans.json").write_text(
                json.dumps(spans, indent=2) + "\n", encoding="utf-8"
            )
            vs.write_seams(into, sid, spans)
            progress.scene(
                sid,
                state="done",
                key=scene_key(scene),
                seconds=round(seconds, 2),
                bought=round(paid, 2),
                reason=None,
            )
            print(f"  {seconds:.1f}s, ${progress.spent:.2f} this run", flush=True)
            break
    progress.set(current=None, stopped="finished")
    lost = [k for k, v in progress.data["scenes"].items() if v.get("state") == "failed"]
    print(f"\nfinished: ${progress.spent:.2f} this run; {len(lost)} failed", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--from", dest="source", type=Path, required=True)
    parser.add_argument("--into", type=Path, required=True)
    parser.add_argument("--cap", type=float, default=CAP, help="dollars this run may spend")
    parser.add_argument("--language", action="append", default=[], help="he or ru; repeatable")
    parser.add_argument("--only", action="append", default=[], help="one scene id; repeatable")
    parser.add_argument("--via", choices=sorted(vs.DOORS), default="vertex")
    parser.add_argument("--spacing", type=float, default=3.0, help="seconds between requests")
    parser.add_argument("--deadline", type=float, default=vs.DEADLINE)
    parser.add_argument("--pause", type=float, default=PAUSE, help="seconds, when throttled")
    parser.add_argument("--wait-daily", type=float, default=WAIT_DAILY, help="hours at most")
    parser.add_argument("--no-direction", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    into = args.into.expanduser().resolve()
    if into == source:
        sys.exit("--into must not be where the scenes live.")
    scenes = load(source, args.language, args.only)
    if not scenes:
        sys.exit(f"No scenes in {source}.")
    progress_path = into / "progress.json"
    if args.dry_run:
        # Read, never written: a dry run leaves no trace.
        progress = Progress.__new__(Progress)
        progress.path = progress_path
        progress.data = {"scenes": {}}
        if progress_path.exists():
            progress.data = json.loads(progress_path.read_text(encoding="utf-8"))
        dry_run(scenes, into, progress, args.spacing, args.cap)
        return

    named = vs.DOORS[args.via][1]
    tts_key = os.environ.get(named, "")
    if not tts_key:
        sys.exit(f"no key: set {named}, under `op run --env-file op.env --`")
    director_key = "" if args.no_direction else os.environ.get("ANTHROPIC_API_KEY", "")
    if not args.no_direction and not director_key:
        sys.exit("no ANTHROPIC_API_KEY for the director: run under op run, or --no-direction")
    into.mkdir(parents=True, exist_ok=True)
    run(scenes, into, Progress(progress_path, args.cap), tts_key, director_key, args)


if __name__ == "__main__":
    main()
