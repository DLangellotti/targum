"""Voice a scene a turn at a time, with the boundaries known rather than guessed.

The scenes' audio was made once by a `synth.py` that is gone — not in targum-internal's
backup, and its scratchpad is empty. This replaces it, and changes three things on the
way, each because the old shape cost something real.

**A turn at a time, not a scene at a time.** The old shape asked for the whole scene in
one multi-speaker request and `dialogue/write.py` then recovered the turn boundaries by
looking for silences. That has three faults. The boundaries are *inferred* from audio
rather than known. A scene whose silences do not account for every seam is written with
**no audio at all**, silently. And the unit of repair is the scene, so the audit of
2026-09-22 — forty-five changed words across twenty-eight scenes — costs twenty-eight
whole re-voices to fix forty-five lines.

Asking per turn fixes all three: the spans are exact because this put the gaps there,
nothing can fail to segment, and one line can be re-voiced on its own. It also removes
the multi-speaker collapse the bake-off found, where Kore and Puck together came back as
Kore reading both parts — a single-voice request cannot collapse into anything.

The cost is the same. It is the same seconds of speech either way, and the rate is per
second. What it buys instead is prosody: two separate requests do not hand each other a
conversation's rhythm. So each turn is given the line before it as context and told it
is answering — measurably worse than one request would be at turn-taking, and the trade
is deliberate. `write.py` still finds its seams, because the gaps written between turns
are digital silence and it is looking for 0.18s at -35dB.

**And it is told how to read the pointing.** Gemini ignores nikkud, so `עזבת` is a coin
toss between *azavta* and *azavt* — and a learner hears the wrong form in the one channel
they cannot check against the page. `pronunciation_hints` turns what the pointing knows
into an instruction the engine will take.

It spends. `--dry-run` prices it and calls nothing.

    python3 scripts/voice_scenes.py --from ~/…/dialogues --only 48-the-cleaning --dry-run
    TARGUM_TTS_KEY=… python3 scripts/voice_scenes.py --from ~/…/dialogues \\
        --into ./voiced --only 48-the-cleaning
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from targum.dialogue.checks import pronunciation_hints  # noqa: E402

MODEL = "gemini-3.1-flash-tts-preview"
#: USD per minute, the rate `speech/__init__.py` charges at.
PER_MINUTE = 0.03
#: 24 kHz mono 16-bit, which is what the API answers with.
RATE = 24000

#: The quiet written between turns. Comfortably over `write.py`'s 0.18s floor, so its
#: silence detection cannot fail to find every seam, and short enough to sound like a
#: reply rather than a pause for thought.
GAP = 0.45

#: Seconds between requests, and the first backoff step. The model is limited per
#: minute; pacing costs nothing and a 429 costs the whole scene.
#: Measured 2026-09-22: the key sustains about 3.5 requests a minute — roughly one
#: every 17 seconds — so anything faster spends the run backing off instead of
#: speaking. 15 seconds sat right on the edge and still 429'd on most turns; 21 is
#: under it with room, and pacing at the real rate is the faster of the two.
#: Anything else calling the same key steals from the same budget: a diagnostic
#: probe run beside this will make *this* fail, not the probe.
SPACING = 21.0
WAIT = 30

#: Kept short on purpose, and the length is not a style preference. Measured on
#: 2026-09-22 against one turn of 81-the-army-friend: a 497-character prompt was
#: rejected with HTTP 400 "Request contains an invalid argument" on four of five
#: identical attempts, and a 109-character one succeeded six times out of six. The
#: rejection is not a rejection — the request is well formed and the same request
#: sometimes works — so the only lever is to ask for less. The line before this turn
#: used to be included for prosody and was the first thing cut.
ASK = "Read aloud as {name}, a {who}, in conversation. Only the line, nothing else."

#: What the pointing knows and the engine will not read. Joined into one sentence
#: rather than a list, for the same reason.
GUIDE = " Read {hints}."


class Daily(RuntimeError):
    """The per-day quota is gone. Waiting will not help; tomorrow will."""


def wav(pcm: bytes) -> bytes:
    head = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
    head += struct.pack("<IHHIIHH", 16, 1, 1, RATE, RATE * 2, 2, 16) + b"data"
    return head + struct.pack("<I", len(pcm)) + pcm


def say(text: str, voice: str, key: str, prompt: str) -> bytes:
    """One turn. Returns raw PCM, not a WAV: these get joined before they get a header."""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={key}"
    )
    body = {
        "contents": [{"parts": [{"text": prompt + "\n\n" + text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }
    request = urllib.request.Request(
        url, json.dumps(body).encode("utf-8"), {"Content-Type": "application/json"}
    )
    # A scene is thirty requests and the model is rate-limited per minute, so a run
    # that simply loops gets a 429 on about the second one. Backing off is not an
    # error path here, it is the normal one: the first attempt at this scene died on
    # turn 0 with nothing written.
    for attempt in range(6):
        try:
            with urllib.request.urlopen(request, timeout=600) as answer:
                payload = json.loads(answer.read())
            part = payload["candidates"][0]["content"]["parts"][0]
            return base64.b64decode(part["inlineData"]["data"])
        except urllib.error.HTTPError as error:
            if error.code == 429:
                # A per-minute limit is worth waiting out; the per-day one is not.
                # This key allows 100 TTS requests a day, and on 2026-09-22 a run that
                # did not tell them apart spent an hour backing off 20, 40, 80, 160
                # seconds at a time against a quota five hours from resetting, looking
                # for all the world like a rate limit it could out-wait.
                detail = error.read()
                try:
                    said = json.loads(detail).get("error", {})
                    for one in said.get("details", []):
                        delay = str(one.get("retryDelay") or "")
                        if delay.endswith("s") and float(delay[:-1]) > 600:
                            raise Daily(said.get("message", "").strip()) from error
                except (ValueError, KeyError):
                    pass
            # 400 is in here because it is not always what it says: see ASK.
            detail = detail if error.code == 429 else b""
            if error.code not in (400, 429, 500, 503) or attempt == 5:
                # A bare "HTTP Error 400: Bad Request" says nothing anybody can act on,
                # and that is what the first run of this printed after eleven good turns.
                # The body says which field it disliked.
                said = ""
                try:
                    said = json.loads(detail or error.read()).get("error", {}).get("message", "")
                except Exception:  # noqa: BLE001 - the body is a courtesy, not a contract
                    pass
                raise RuntimeError(
                    f"HTTP {error.code} on this turn: {said or '(no detail)'}"
                ) from error
            wait = WAIT * (2**attempt)
            print(f"      {error.code}; waiting {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def prompt_for(scene: dict[str, Any], n: int) -> str:
    turn = scene["turns"][n]
    who = scene["cast"][turn["who"]]
    said = ASK.format(
        name=who.get("name") or turn["who"],
        who="man" if who.get("gender") == "m" else "woman",
    )
    # The addressee's gender, not the speaker's. A second-person form is about who is
    # being spoken to, and passing the speaker made the "though the cast says otherwise"
    # note fire on almost every line — scene 81 hid it by having two men in it.
    other = scene["cast"]["B" if turn["who"] == "A" else "A"]
    hints = pronunciation_hints(turn["text"], other.get("gender", ""))
    if hints:
        said += GUIDE.format(hints="; ".join(hints))
    return said


def encode(raw: Path, into: Path) -> None:
    """To mp3 at 48k mono, which is the bitrate the rest of the shelf's speech is at."""
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-i",
            str(raw),
            "-ac",
            "1",
            "-b:a",
            "48k",
            str(into),
        ],
        check=True,
    )


def voice(scene: dict[str, Any], key: str, into: Path) -> tuple[list[list[float]], float]:
    """The whole scene, one turn at a time. Returns the spans and the seconds spoken."""
    quiet = b"\0" * int(RATE * GAP) * 2
    pieces: list[bytes] = []
    spans: list[list[float]] = []
    at = 0.0
    for n in range(len(scene["turns"])):
        turn = scene["turns"][n]
        pcm = say(turn["text"], scene["cast"][turn["who"]]["voice"], key, prompt_for(scene, n))
        seconds = len(pcm) / (RATE * 2)
        spans.append([round(at, 2), round(at + seconds, 2)])
        pieces.append(pcm)
        at += seconds
        if n != len(scene["turns"]) - 1:
            pieces.append(quiet)
            at += GAP
        print(f"    t{n} {seconds:5.2f}s  {turn['who']}", flush=True)
        time.sleep(SPACING)
    joined = b"".join(pieces)
    raw = into / f"{scene['id']}.wav"
    raw.write_bytes(wav(joined))
    encode(raw, into / f"{scene['id']}.mp3")
    return spans, len(joined) / (RATE * 2)


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--from", dest="source", type=Path, required=True)
    parser.add_argument("--into", type=Path, default=Path("voiced"))
    parser.add_argument("--only", action="append", default=[], help="one scene id; repeatable")
    parser.add_argument("--key", type=Path, help="file holding the key; or TARGUM_TTS_KEY")
    parser.add_argument("--again", action="store_true", help="re-voice scenes already in --into")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    into = args.into.expanduser().resolve()
    if into == source:
        sys.exit("--into must not be where the scenes live.")

    scenes = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(source.glob("*.json"))]
    if args.only:
        wanted = set(args.only)
        scenes = [s for s in scenes if s["id"] in wanted]
        missing = wanted - {s["id"] for s in scenes}
        if missing:
            sys.exit(f"no such scene: {', '.join(sorted(missing))}")
    if not scenes:
        sys.exit(f"No scenes in {source}.")

    # Only what is missing, which is what the old synth.py did too. At about three
    # and a half requests a minute the whole shelf is a whole night, so a run has to
    # be able to stop and be started again without paying twice.
    if not args.again:
        before = len(scenes)
        scenes = [s for s in scenes if not (into / f"{s['id']}.mp3").exists()]
        if before != len(scenes):
            print(f"{before - len(scenes)} already voiced in {into}; skipping them")
    if not scenes:
        print("Nothing to do: every scene asked for is already voiced.")
        return

    turns = sum(len(s["turns"]) for s in scenes)
    # Priced off the audio the scenes already have, which is the only honest estimate
    # before anything is generated.
    known = sum((s["turns"][-1].get("end") or 0) for s in scenes if s.get("turns"))
    print(f"{len(scenes)} scenes, {turns} turns, {turns} requests")
    print(f"they are {known / 60:.1f} minutes today, so about ${known / 60 * PER_MINUTE:.2f}")
    hinted = sum(
        1
        for s in scenes
        for n in range(len(s["turns"]))
        if pronunciation_hints(
            s["turns"][n]["text"], s["cast"][s["turns"][n]["who"]].get("gender", "")
        )
    )
    print(f"{hinted} of {turns} turns carry a pronunciation the letters do not decide")

    if args.dry_run:
        for scene in scenes[:1]:
            print(f"\nthe prompt for {scene['id']} t0:\n")
            print(prompt_for(scene, 0))
        print("Nothing was called. Drop --dry-run to run it.")
        return

    key = (args.key.read_text().strip() if args.key else "") or os.environ.get("TARGUM_TTS_KEY", "")
    if not key:
        sys.exit("no key: set TARGUM_TTS_KEY or pass --key <file>")

    into.mkdir(parents=True, exist_ok=True)
    spent = 0.0
    for scene in scenes:
        print(f"\n{scene['id']}:", flush=True)
        try:
            spans, seconds = voice(scene, key, into)
        except Daily as gone:
            print(f"\n  the day's quota is gone: {gone}", file=sys.stderr)
            print(
                f"\n{len(scenes) - scenes.index(scene)} scenes left. Run this again "
                f"when it resets; what is voiced is skipped."
            )
            return
        spent += seconds / 60 * PER_MINUTE
        # Written per scene, so a run that dies keeps what it paid for.
        (into / f"{scene['id']}.spans.json").write_text(
            json.dumps(spans, indent=2) + "\n", encoding="utf-8"
        )
        print(f"  {seconds:.1f}s, ${spent:.2f} so far", flush=True)

    print(f"\n{len(scenes)} scenes into {into}. This run cost ${spent:.2f}.")
    print("The spans are exact, not detected. Nothing where the scenes live was touched.")


if __name__ == "__main__":
    main()
