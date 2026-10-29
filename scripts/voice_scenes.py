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
is deliberate.

**And each line is directed, timed and levelled** (targum-internal#566, David 2026-10-29:
"not much space between the lines… excited when they shouldn't be"). A cheap text model
reads the whole scene once and writes each turn a few words of direction — "calm, a little
tired" — so a line knows its mood without the line before it in the prompt, and the
default it is told to keep is ordinary conversation. The gaps vary with what happened: a
reply waits 0.6–0.9s, an answer to a question a little longer, a line that cuts in or
carries on about 0.3s. Each turn is brought to the same EBU R128 loudness before it is
joined, so no line jumps out, and the gaps carry a low room tone instead of digital
silence. The tone sits some 25dB under `write.py`'s -35dB floor, and its shortest gap is
over its 0.18s, so a shelf rebuilt from silences still finds every seam.

**And it is told how to read the pointing.** Gemini ignores nikkud, so `עזבת` is a coin
toss between *azavta* and *azavt* — and a learner hears the wrong form in the one channel
they cannot check against the page. `pronunciation_hints` turns what the pointing knows
into an instruction the engine will take.

It spends. `--dry-run` prices it and calls nothing.

    python3 scripts/voice_scenes.py --from ~/…/dialogues --only 48-the-cleaning --dry-run
    op run --env-file op.env -- python3 scripts/voice_scenes.py --from ~/…/dialogues \\
        --into ./voiced --only 48-the-cleaning --via vertex --spacing 3

It needs `ANTHROPIC_API_KEY` for the director as well as the TTS key, unless
`--no-direction` is passed.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import io
import json
import math
import os
import re
import statistics
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from targum.dialogue.checks import pronunciation_hints  # noqa: E402

MODEL = "gemini-3.1-flash-tts-preview"
#: USD per minute, the rate `speech/__init__.py` charges at.
PER_MINUTE = 0.03
#: 24 kHz mono 16-bit, which is what the API answers with.
RATE = 24000

#: The quiet between turns, which used to be a flat 0.45s and sounded like a machine
#: reading a list (David, 2026-10-29). A reply to the other speaker waits somewhere in
#: BETWEEN, drawn per seam from the scene id so a re-run lands on the same timing; an
#: answer to a question waits AFTER_QUESTION longer, because a question is thought
#: about; a line that carries on the same speaker's, or cuts in on a dash, waits SAME.
#: Every one of them is over `write.py`'s 0.18s floor.
BETWEEN = (0.6, 0.9)
AFTER_QUESTION = 0.25
SAME = 0.3

#: The room the gaps are recorded in: pink noise, band-limited, at about -60 dBFS RMS
#: (peaks near -48) once mixed. Digital silence between two voices reads as a cut; a
#: floor this low is heard as air. It runs under the whole scene, not only the gaps, so
#: the floor does not switch on and off at every seam, and it stays far under
#: `write.py`'s -35dB.
TONE = ",".join(
    [
        "anoisesrc=color=pink:sample_rate={rate}:amplitude=0.009:seed=566",
        "highpass=f=120",
        "lowpass=f=3000",
    ]
)

#: Each turn is brought to this integrated loudness before it is joined, so no line jumps
#: out. The shelf before this measured -16.4 LUFS with a true peak of +1.0 dBTP (he-06,
#: 2026-10-29), which is clipping, and its turns spread over 4.9 LU. It is done by gain,
#: with a limiter at CEILING that only touches the odd peak: by gain alone, a line with
#: one loud consonant could not be raised and he-06 t13 sat 3 LU under the rest. The
#: limiter's delay is compensated and the turn is cut back to its own sample count, so
#: the spans cannot move.
LOUDNESS = -18.0
CEILING = -2.0

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
#: The 21 seconds is the free key's ceiling. A paid key is not held to it, and --spacing
#: sets the pace for one.

#: Kept short on purpose, and the length is not a style preference. Measured on
#: 2026-09-22 against one turn of 81-the-army-friend: a 497-character prompt was
#: rejected with HTTP 400 "Request contains an invalid argument" on four of five
#: identical attempts, and a 109-character one succeeded six times out of six. The
#: rejection is not a rejection — the request is well formed and the same request
#: sometimes works — so the only lever is to ask for less. The line before this turn
#: used to be included for prosody and was the first thing cut.
ASK = "Read aloud as {name}, a {who}, in conversation{how}. Only the line, nothing else."
#: How the director's few words join ASK: "…in conversation, calm, a little tired."
HOW = ", {direction}"

#: What the pointing knows and the engine will not read. Joined into one sentence
#: rather than a list, for the same reason.
GUIDE = " Read {hints}."

#: No prompt longer than this goes out. The corpus ran median 73 and max 180 before the
#: director, and 180 has never failed; the cliff is somewhere past 200 and well before
#: 497. A direction that would push a prompt over is cut back to its first clause, and
#: dropped if even that does not fit: a pronunciation hint is worth more than a mood.
LONGEST = 180

#: The director. One request per scene, cached by the scene's text, so a re-run spends
#: nothing and a re-worded scene is directed again. Haiku because the job is a few words
#: per line and it is the cheapest model the laptop's key already pays for.
DIRECTOR = "claude-haiku-4-5"
#: USD per million tokens in and out, as `translate/anthropic_provider.py` prices it.
DIRECTOR_PRICE = (1.0, 5.0)
#: Part of the cache key: change it when the brief below changes, and every scene is
#: directed afresh on its next run.
DIRECTOR_VERSION = 1
#: The longest direction kept, in characters: "a little impatient, quick, clipped" fits,
#: and so does ASK with it under LONGEST on almost every line.
DIRECTION_MOST = 40
#: What a turn is read as when the director is off or said nothing usable for it.
NEUTRAL = "calm and natural"
BRIEF = """You direct two voice actors reading a short everyday conversation in Hebrew \
for a language-learning app. For each numbered turn write a stage direction of two to \
six English words: the speaker's mood, how strongly, and the pace. For example: \
"calm, a little tired", "warm, unhurried", "mildly annoyed, brisk", "relaxed, friendly".

The default is relaxed, ordinary conversation between adults. Never excited, \
enthusiastic, cheerful or emphatic unless the words plainly call for it: greetings, \
thanks, agreement and politeness are calm. Keep a speaker's mood steady from turn to \
turn unless something in the conversation changes it.

Answer with only a JSON array of {count} strings, one per turn, in order.

{title} — {gloss}

{lines}"""


#: Wall-clock seconds one request may take, from opening the connection to the last
#: byte. Not a socket timeout: urllib's `timeout=` bounds each read on its own, so an
#: answer that trickles a byte every few seconds never trips it. A turn is a few
#: seconds of speech and comes back in well under twenty; ninety is a stall, not a slow
#: answer. No deadline survives the laptop going to sleep, though: the re-voicing that
#: "hung" on 2026-10-26 was a Mac on battery entering sleep at 19:45:06, a minute into
#: the run, with the watchdog frozen beside it. Run a long voicing on power, awake.
DEADLINE = 90.0
#: The most any one socket operation may wait, so the abandoned worker of a cut-off
#: request does not outlive it by much.
STALL = 30.0
#: Cut-offs allowed on one turn before the turn fails, and the first backoff after one.
#: A stall is the door's, not the request's, so it is worth one more try, not six.
CUTOFFS = 3
CUTOFF_WAIT = 10


class Daily(RuntimeError):
    """The per-day quota is gone. Waiting will not help; tomorrow will."""


class CutOff(TimeoutError):
    """A request that ran past its wall-clock deadline and was abandoned.

    It may still be billed: the model may have spoken the whole line before the answer
    stalled on its way back. So it is reported to `say`'s `on_cutoff`, for a ledger to
    record, rather than passing as if nothing was asked."""

    def __init__(self, elapsed: float, received: int, deadline: float) -> None:
        super().__init__(
            f"cut off after {elapsed:.0f}s (deadline {deadline:.0f}s), {received} bytes in"
        )
        self.elapsed = elapsed
        self.received = received
        self.deadline = deadline


def fetch(request: urllib.request.Request, deadline: float = DEADLINE) -> bytes:
    """The whole answer to `request` within `deadline` seconds of wall clock, or `CutOff`.

    The request runs in a worker thread and this waits on it with a hard deadline. On
    expiry the worker's socket is shut down, which wakes it from any read it is stuck
    in, and the request is given up. An HTTP error comes back as an `HTTPError` whose
    body has already been read inside the deadline."""
    connections: list[http.client.HTTPConnection] = []
    stop = threading.Event()
    received = [0]
    outcome: dict[str, Any] = {}

    def tracked(kind: type[http.client.HTTPConnection]) -> Any:
        def make(host: str, **settings: Any) -> http.client.HTTPConnection:
            connection = kind(host, **settings)
            connections.append(connection)
            return connection

        return make

    class Plain(urllib.request.HTTPHandler):
        def http_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
            return self.do_open(tracked(http.client.HTTPConnection), req)

    class Secure(urllib.request.HTTPSHandler):
        def https_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
            return self.do_open(tracked(http.client.HTTPSConnection), req)

    opener = urllib.request.build_opener(Plain, Secure)

    def work() -> None:
        try:
            with opener.open(request, timeout=min(STALL, deadline)) as answer:
                chunks: list[bytes] = []
                while not stop.is_set():
                    chunk = answer.read1(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    received[0] += len(chunk)
                outcome["body"] = b"".join(chunks)
        except urllib.error.HTTPError as error:
            try:
                detail = error.read()
            except Exception:  # noqa: BLE001 - the body is a courtesy, not a contract
                detail = b""
            outcome["refused"] = (error, detail)
        except BaseException as error:  # noqa: BLE001 - handed to the caller's thread
            outcome["error"] = error

    began = time.monotonic()
    worker = threading.Thread(target=work, name="tts-request", daemon=True)
    worker.start()
    worker.join(deadline)
    if worker.is_alive():
        stop.set()
        for connection in connections:
            sock = connection.sock
            if sock is not None:
                try:
                    sock.shutdown(2)  # SHUT_RDWR: wakes a blocked recv in the worker
                except OSError:
                    pass
        raise CutOff(time.monotonic() - began, received[0], deadline)
    if "refused" in outcome:
        error, detail = outcome["refused"]
        raise urllib.error.HTTPError(
            request.full_url, error.code, error.reason, error.headers, io.BytesIO(detail)
        )
    if "error" in outcome:
        raise outcome["error"]
    body: bytes = outcome["body"]
    return body


def wav(pcm: bytes) -> bytes:
    head = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
    head += struct.pack("<IHHIIHH", 16, 1, 1, RATE, RATE * 2, 2, 16) + b"data"
    return head + struct.pack("<I", len(pcm)) + pcm


#: Two doors to the same model. The Gemini API is AI Studio's, and caps this preview model
#: at 100 requests a day on the paid tier as on the free one — measured 2026-09-26, and
#: the shelf is 2,023 requests. Vertex serves the same model and voices with no daily cap,
#: and takes the same body; its key must be bound to a service account holding Vertex AI
#: User, because Vertex will not run a model for a key that is nobody.
DOORS = {
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "TARGUM_TTS_KEY",
    ),
    "vertex": (
        "https://aiplatform.googleapis.com/v1/publishers/google/models/{model}:generateContent",
        "TARGUM_VERTEX_TTS_KEY",
    ),
}


def say(
    text: str,
    voice: str,
    key: str,
    prompt: str,
    via: str = "gemini",
    deadline: float = DEADLINE,
    on_cutoff: Callable[[CutOff], None] | None = None,
) -> bytes:
    """One turn. Returns raw PCM, not a WAV: these get joined before they get a header.

    Every request has `deadline` seconds of wall clock. One that runs past it is
    abandoned, handed to `on_cutoff` (it may have been billed), and retried after a
    backoff, at most `CUTOFFS` times before the `CutOff` is raised."""
    url = DOORS[via][0].format(model=MODEL) + f"?key={key}"
    body = {
        # Vertex requires the role; the Gemini API takes it and does not need it.
        "contents": [{"role": "user", "parts": [{"text": prompt + "\n\n" + text}]}],
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
    cutoffs = 0
    for attempt in range(6 + CUTOFFS):
        try:
            payload = json.loads(fetch(request, deadline))
            part = payload["candidates"][0]["content"]["parts"][0]
            return base64.b64decode(part["inlineData"]["data"])
        except CutOff as cut:
            cutoffs += 1
            if on_cutoff is not None:
                on_cutoff(cut)
            if cutoffs >= CUTOFFS:
                raise
            wait = CUTOFF_WAIT * (2 ** (cutoffs - 1))
            print(f"      {cut}; waiting {wait}s", flush=True)
            time.sleep(wait)
            continue
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
            if error.code not in (400, 429, 500, 503) or attempt - cutoffs == 5:
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
            wait = WAIT * (2 ** (attempt - cutoffs))
            print(f"      {error.code}; waiting {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError("unreachable")


POINTS = re.compile("[֑-ׇ]")


def tidy(direction: Any) -> str:
    """A direction as it goes into a prompt: a few lowercase words, no quotes, no full
    stop, and no longer than DIRECTION_MOST — cut at a word, not inside one."""
    if not isinstance(direction, str):
        return ""
    said = " ".join(direction.replace('"', "").replace("'", "").split()).strip(" .;:").lower()
    if len(said) > DIRECTION_MOST:
        said = said[: DIRECTION_MOST + 1].rsplit(" ", 1)[0].rstrip(" ,;")
    return said


def scene_key(scene: dict[str, Any]) -> str:
    """What the director's answer depends on, hashed: the words, their English, who says
    them, and the brief. A re-pointed scene keeps its directions, because the pointing is stripped
    before the director reads it; a re-worded one is directed again."""
    said = {
        "model": DIRECTOR,
        "version": DIRECTOR_VERSION,
        "title": scene.get("english") or scene.get("title", ""),
        "gloss": scene.get("gloss", ""),
        "cast": {k: [v.get("name", ""), v.get("gender", "")] for k, v in scene["cast"].items()},
        # The English too: `brief` sends it, so a changed gloss can change a direction.
        "turns": [
            [t["who"], POINTS.sub("", t["text"]), t.get("english", "")] for t in scene["turns"]
        ],
    }
    return hashlib.sha256(json.dumps(said, ensure_ascii=False).encode()).hexdigest()[:16]


def brief(scene: dict[str, Any]) -> str:
    """The director's whole request: the scene unpointed, with its English beside it."""
    lines = []
    for n, turn in enumerate(scene["turns"]):
        who = scene["cast"][turn["who"]]
        name = who.get("name") or turn["who"]
        gender = "man" if who.get("gender") == "m" else "woman"
        english = f" ({turn['english']})" if turn.get("english") else ""
        lines.append(f"{n + 1}. {name}, a {gender}: {POINTS.sub('', turn['text'])}{english}")
    return BRIEF.format(
        count=len(scene["turns"]),
        title=scene.get("english") or scene.get("title", ""),
        gloss=scene.get("gloss", ""),
        lines="\n".join(lines),
    )


def read_directions(answer: str, count: int) -> list[str]:
    """The model's answer as `count` directions, or ValueError. A blank one is NEUTRAL."""
    start, end = answer.find("["), answer.rfind("]")
    if start < 0 or end < start:
        raise ValueError(f"no JSON array in the director's answer: {answer[:120]!r}")
    said = json.loads(answer[start : end + 1])
    if not isinstance(said, list) or len(said) != count:
        raise ValueError(f"the director gave {len(said)} directions for {count} turns")
    return [tidy(one) or NEUTRAL for one in said]


def ask_director(text: str, key: str) -> tuple[str, float]:
    """One request to the director. Returns its text and what it cost in USD."""
    body = {
        "model": DIRECTOR,
        "max_tokens": 1024,
        "temperature": 0,
        "messages": [{"role": "user", "content": text}],
    }
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        json.dumps(body).encode("utf-8"),
        {
            "Content-Type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
    )
    payload = json.loads(fetch(request, DEADLINE))
    used = payload.get("usage", {})
    cost = (
        used.get("input_tokens", 0) * DIRECTOR_PRICE[0]
        + used.get("output_tokens", 0) * DIRECTOR_PRICE[1]
    ) / 1e6
    said = "".join(b.get("text", "") for b in payload.get("content", []) if b.get("type") == "text")
    return said, cost


def write_atomically(path: Path, data: bytes) -> None:
    """Beside the target, then renamed: a kill mid-write leaves the old file or none."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.write_bytes(data)
    temporary.replace(path)


def direct(
    scene: dict[str, Any],
    key: str,
    store: Path,
    ask: Callable[[str, str], tuple[str, float]] = ask_director,
) -> tuple[list[str], float]:
    """A direction for every turn, and what getting them cost. Read from `store` when
    this scene's words have been directed before, and written there the moment they are
    bought, so neither a re-run nor a crash later in the scene pays for them twice.

    An answer that cannot be read is asked once more; if the second cannot be read
    either, every turn is NEUTRAL, and that is stored too, marked as a fallback. Left
    unstored, the next run would direct the scene afresh, every prompt would change, and
    every turn already bought under NEUTRAL would be bought again. Delete the file to
    have the scene directed again."""
    cached = store / f"{scene['id']}.{scene_key(scene)}.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))["directions"], 0.0
    spent = 0.0
    text = brief(scene)
    for attempt in range(2):
        answer, cost = ask(text, key)
        spent += cost
        try:
            directions = read_directions(answer, len(scene["turns"]))
        except ValueError as unreadable:
            print(f"    director, attempt {attempt + 1}: {unreadable}", flush=True)
            continue
        keep(cached, directions, fallback=False)
        return directions, spent
    print(f"    director: unreadable twice; every turn is {NEUTRAL!r}, kept as such", flush=True)
    directions = [NEUTRAL] * len(scene["turns"])
    keep(cached, directions, fallback=True)
    return directions, spent


def keep(cached: Path, directions: list[str], fallback: bool) -> None:
    record = {
        "model": DIRECTOR,
        "version": DIRECTOR_VERSION,
        "fallback": fallback,
        "directions": directions,
    }
    write_atomically(cached, (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode())


class TooLong(ValueError):
    """A prompt that cannot be brought under LONGEST. It is never sent."""


#: The long-winded parts of `pronunciation_hints`' sentences and what they shrink to when
#: the whole would not fit. The forms and the sounds stay; only the explanation goes.
TERSE = [
    (' the word for "you" to a woman — not "et", the object marker', ' not "et"'),
    (", the feminine", ""),
    (", the masculine", ""),
]


def prompt_for(scene: dict[str, Any], n: int, direction: str = "") -> str:
    turn = scene["turns"][n]
    who = scene["cast"][turn["who"]]
    name = who.get("name") or turn["who"]
    gender = "man" if who.get("gender") == "m" else "woman"
    # The addressee's gender, not the speaker's. A second-person form is about who is
    # being spoken to, and passing the speaker made the "though the cast says otherwise"
    # note fire on almost every line — scene 81 hid it by having two men in it.
    other = scene["cast"]["B" if turn["who"] == "A" else "A"]
    hints = pronunciation_hints(turn["text"], other.get("gender", ""))
    guide = GUIDE.format(hints="; ".join(hints)) if hints else ""
    # The direction gives way first: cut to its first clause, then left out. Then the
    # hint is said tersely. A prompt over LONGEST is the 400 the 2026-09-22 run kept
    # hitting, so one that still does not fit is refused here, before it is sent.
    terse = guide
    for long, short in TERSE:
        terse = terse.replace(long, short)
    for how, hint in (
        (direction, guide),
        (direction.split(",")[0].strip(), guide),
        ("", guide),
        ("", terse),
    ):
        said = ASK.format(name=name, who=gender, how=HOW.format(direction=how) if how else "")
        if len(said + hint) <= LONGEST:
            return said + hint
    raise TooLong(
        f"{scene['id']} t{n}: the prompt is {len(said + terse)} characters even with no "
        f"direction and the hint said tersely; the limit is {LONGEST}. Not sent."
    )


def gap(scene: dict[str, Any], n: int) -> float:
    """Seconds of room between turn `n` and the one after it."""
    turns = scene["turns"]
    before, after = turns[n], turns[n + 1]
    said = POINTS.sub("", before["text"]).rstrip(" \"'”»)")
    if before["who"] == after["who"] or said.endswith(("—", "–", "-")):
        return SAME
    # Drawn from the seam itself, so the same scene is timed the same way every run.
    draw = int(hashlib.sha256(f"{scene['id']}#{n}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    seconds = BETWEEN[0] + (BETWEEN[1] - BETWEEN[0]) * draw
    if said.endswith("?"):
        seconds += AFTER_QUESTION
    return round(seconds, 2)


def loudness(pcm: bytes) -> tuple[float, float]:
    """Integrated loudness (LUFS) and true peak (dBTP) of one turn, by ffmpeg's EBU R128
    meter. A turn too short or too quiet to measure says -inf, and is left as it is."""
    run = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-f",
            "s16le",
            "-ar",
            str(RATE),
            "-ac",
            "1",
            "-i",
            "-",
            "-af",
            "loudnorm=print_format=json",
            "-f",
            "null",
            "-",
        ],
        input=pcm,
        capture_output=True,
        check=True,
    )
    err = run.stderr.decode("utf-8", "replace")
    said = json.loads(err[err.rindex("{") : err.rindex("}") + 1])

    def number(field: str) -> float:
        try:
            return float(said[field])
        except (KeyError, ValueError):
            return -math.inf

    return number("input_i"), number("input_tp")


def level(pcm: bytes) -> bytes:
    """One turn at LOUDNESS: a single gain, and a limiter for the peaks it would push
    over CEILING. The same number of samples comes out as went in, always."""
    integrated, _ = loudness(pcm)
    if not math.isfinite(integrated) or integrated < -60:
        return pcm
    limit = 10 ** (CEILING / 20)
    chain = (
        f"volume={LOUDNESS - integrated:.2f}dB,"
        f"alimiter=limit={limit:.4f}:level=disabled:latency=1:attack=5:release=50"
    )
    raw = ["-f", "s16le", "-ar", str(RATE), "-ac", "1"]
    run = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", *raw, "-i", "-", "-af", chain, *raw, "-"],
        input=pcm,
        capture_output=True,
        check=True,
    )
    out = run.stdout[: len(pcm)]
    return out + b"\0" * (len(pcm) - len(out))


def encode(raw: Path, into: Path, tone: bool = True) -> None:
    """To mp3 at 48k mono, which is the bitrate the rest of the shelf's speech is at, with
    the room tone laid under the whole of it."""
    mix: list[str] = []
    if tone:
        mix = [
            "-f",
            "lavfi",
            "-i",
            TONE.format(rate=RATE),
            "-filter_complex",
            "[0:a][1:a]amix=inputs=2:duration=first:normalize=0",
        ]
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(raw), *mix]
        + ["-ac", "1", "-ar", str(RATE), "-b:a", "48k", str(into)],
        check=True,
    )


def take_path(store: Path, scene: dict[str, Any], n: int, voice_: str, prompt: str) -> Path:
    """Where one turn's bought audio is kept: named by everything that made it, so a
    changed line, voice or prompt is bought again and an unchanged one never is."""
    made = json.dumps([MODEL, voice_, prompt, scene["turns"][n]["text"]], ensure_ascii=False)
    return (
        store / str(scene["id"]) / f"{n:02d}.{hashlib.sha256(made.encode()).hexdigest()[:12]}.pcm"
    )


def voice(
    scene: dict[str, Any],
    key: str,
    into: Path,
    spacing: float = SPACING,
    via: str = "gemini",
    deadline: float = DEADLINE,
    on_cutoff: Callable[[CutOff], None] | None = None,
    directions: list[str] | None = None,
) -> tuple[list[list[float]], float, float]:
    """The whole scene, one turn at a time. Returns the spans, the seconds in the scene,
    and the seconds bought this run.

    Every turn is written to `into/turns/` the moment it comes back, before the next is
    asked for, so a run that dies keeps what it paid for and the next run asks only for
    what is missing."""
    takes = into / "turns"
    pieces: list[bytes] = []
    spans: list[list[float]] = []
    at = 0.0
    bought = 0.0
    last = len(scene["turns"]) - 1
    # Every prompt first, so a TooLong stops the scene before anything in it is bought.
    prompts = [prompt_for(scene, n, directions[n] if directions else "") for n in range(last + 1)]
    for n, turn in enumerate(scene["turns"]):
        speaker = scene["cast"][turn["who"]]["voice"]
        prompt = prompts[n]
        kept = take_path(takes, scene, n, speaker, prompt)
        if kept.exists():
            pcm = kept.read_bytes()
            fresh = False
        else:
            pcm = say(turn["text"], speaker, key, prompt, via, deadline, on_cutoff)
            write_atomically(kept, pcm)
            bought += len(pcm) / (RATE * 2)
            fresh = True
        pcm = level(pcm)
        seconds = len(pcm) / (RATE * 2)
        spans.append([round(at, 2), round(at + seconds, 2)])
        pieces.append(pcm)
        at += seconds
        if n != last:
            pause = gap(scene, n)
            pieces.append(b"\0\0" * int(RATE * pause))
            at += int(RATE * pause) / RATE
        print(f"    t{n} {seconds:5.2f}s  {turn['who']}  {len(prompt)}ch  {prompt}", flush=True)
        if fresh and n != last:
            time.sleep(spacing)
    joined = b"".join(pieces)
    raw = into / f"{scene['id']}.wav"
    raw.write_bytes(wav(joined))
    encode(raw, into / f"{scene['id']}.mp3")
    return spans, len(joined) / (RATE * 2), bought


#: Format of the `<id>.seams.json` sidecar, which `dialogue/write.py` reads.
SEAMS_VERSION = 1


def write_seams(into: Path, scene_id: str, spans: list[list[float]]) -> Path:
    """The seams this run put into `<id>.mp3`, beside it, for `dialogue/write.py`.

    write.py otherwise finds seams by taking the longest N-1 silences in the file. With
    gaps as short as 0.3s that stops being safe: a pause inside a line can be longer than
    the gap between two (qa counted 103 inside-a-turn pauses over 0.57s). These spans are
    known, not guessed. The mp3's hash is in the file, so a sidecar left beside an mp3
    that was replaced afterwards is ignored and write.py listens for silences again."""
    mp3 = into / f"{scene_id}.mp3"
    record = {
        "version": SEAMS_VERSION,
        "mp3_sha256": hashlib.sha256(mp3.read_bytes()).hexdigest(),
        "turns": len(spans),
        "spans": spans,
    }
    path = into / f"{scene_id}.seams.json"
    write_atomically(path, (json.dumps(record, indent=2) + "\n").encode())
    return path


def lengths(prompts: list[str]) -> str:
    sizes = sorted(len(p) for p in prompts)
    over = sum(1 for s in sizes if s > LONGEST)
    return (
        f"median {statistics.median(sizes):.0f}, p95 {sizes[int(len(sizes) * 0.95)]}, "
        f"max {sizes[-1]}, over {LONGEST}: {over}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--from", dest="source", type=Path, required=True)
    parser.add_argument("--into", type=Path, default=Path("voiced"))
    parser.add_argument("--only", action="append", default=[], help="one scene id; repeatable")
    parser.add_argument("--key", type=Path, help="file holding the key; or TARGUM_TTS_KEY")
    parser.add_argument("--again", action="store_true", help="re-voice scenes already in --into")
    parser.add_argument(
        "--via", choices=sorted(DOORS), default="gemini", help="which door to the model"
    )
    parser.add_argument("--spacing", type=float, default=SPACING, help="seconds between requests")
    parser.add_argument(
        "--deadline", type=float, default=DEADLINE, help="wall-clock seconds per request"
    )
    parser.add_argument(
        "--no-direction", action="store_true", help="read every turn as NEUTRAL; no director"
    )
    parser.add_argument(
        "--directions", type=Path, help="where directions are cached; default --into/directions"
    )
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

    store = (args.directions or into / "directions").expanduser().resolve()
    if args.dry_run:
        # The lengths with no direction, and with the longest one allowed on every turn,
        # which is the worst the director can do to them.
        widest = "x" * DIRECTION_MOST
        bare_, worst = [], []
        refused: list[str] = []
        for s in scenes:
            for n in range(len(s["turns"])):
                try:
                    bare_.append(prompt_for(s, n))
                    worst.append(prompt_for(s, n, widest))
                except TooLong as long:
                    refused.append(str(long))
        for one in refused:
            print(f"  REFUSED {one}")
        print(f"prompt lengths, no direction: {lengths(bare_)}")
        print(f"prompt lengths, a {DIRECTION_MOST}-char direction: {lengths(worst)}")
        shortened = sum(1 for p in worst if widest not in p)
        print(f"  {shortened} of {len(worst)} turns would lose or shorten that direction")
        for scene in scenes[:1]:
            print(f"\nthe prompt for {scene['id']} t0:\n")
            print(prompt_for(scene, 0, NEUTRAL))
            print(f"\nthe gaps: {[gap(scene, n) for n in range(len(scene['turns']) - 1)]}")
        print("Nothing was called. Drop --dry-run to run it.")
        return

    named = DOORS[args.via][1]
    key = (args.key.read_text().strip() if args.key else "") or os.environ.get(named, "")
    if not key:
        sys.exit(f"no key: set {named} or pass --key <file>")
    director = "" if args.no_direction else os.environ.get("ANTHROPIC_API_KEY", "")
    if not args.no_direction and not director:
        sys.exit(
            "no ANTHROPIC_API_KEY for the director: run under "
            "`op run --env-file op.env --`, or pass --no-direction"
        )

    into.mkdir(parents=True, exist_ok=True)
    spent = 0.0
    cut: list[CutOff] = []
    voiced = 0
    for scene in scenes:
        print(f"\n{scene['id']}:", flush=True)
        directions: list[str] | None = None
        if director:
            directions, cost = direct(scene, director, store)
            spent += cost
            for n, one in enumerate(directions):
                print(f"    direction t{n}: {one}", flush=True)
        try:
            spans, seconds, bought = voice(
                scene, key, into, args.spacing, args.via, args.deadline, cut.append, directions
            )
        except (CutOff, TooLong) as stalled:
            print(f"  not voiced this run: {stalled}", file=sys.stderr)
            continue
        except Daily as gone:
            print(f"\n  the day's quota is gone: {gone}", file=sys.stderr)
            print(
                f"\n{len(scenes) - scenes.index(scene)} scenes left. Run this again "
                f"when it resets; what is voiced is skipped."
            )
            return
        spent += bought / 60 * PER_MINUTE
        voiced += 1
        # Written per scene, so a run that dies keeps what it paid for.
        (into / f"{scene['id']}.spans.json").write_text(
            json.dumps(spans, indent=2) + "\n", encoding="utf-8"
        )
        write_seams(into, scene["id"], spans)
        print(f"  {seconds:.1f}s, {bought:.1f}s of it bought, ${spent:.3f} so far", flush=True)

    print(f"\n{voiced} of {len(scenes)} scenes into {into}. This run cost ${spent:.3f}.")
    if cut:
        # Not in the figure above, because nothing came back to measure; but asked for,
        # and possibly billed, so said.
        print(f"{len(cut)} requests were cut off at {args.deadline:.0f}s and may be billed too.")
    print("The spans are exact, not detected. Nothing where the scenes live was touched.")


if __name__ == "__main__":
    main()
