"""How well the forced aligner finds words in audio: synthesised, chanted, or read.

Three measurements share this file because they share the aligner, the ledger stage and
the question; they differ in where the truth comes from, and `--on` below says how.

**Synthesised speech** (`--on tts`) is targum-internal#265's acceptance 2. Word clocks
on a read-aloud page — the thing that would let a line light word by word where there is
no recording, only a voice — are held behind a number nobody had taken. This takes it.

    .venv/bin/python scripts/eval_align.py --languages he,fr,ru,it --words 40 --dry-run
    op run --env-file op.env -- .venv/bin/python scripts/eval_align.py --languages he

**It spends.** The voice is $0.03 a minute, so forty words a language across four is a
few cents — but `--dry-run` prices it first and calls nothing, which is the only honest
default for a script whose whole job is to be run by somebody else.

**Where the truth comes from, and what that costs in honesty.** A synthesiser gives no
per-word timings, so there is nothing to score against unless somebody marks the
boundaries by hand — which is what the card asks for and what a script cannot do. This
takes the other road: **each word is synthesised as its own clip and the clips are joined**,
so every boundary is known exactly, by construction, for nothing.

**What "exactly" means here, learned the hard way (2026-10-08).** The join between two
clips is exact, but it is not where either word is: every clip carries the voice's own
silence around its word. The first run scored word ends against the joins and reported
340-400 ms in every language, which was the padding. A word is now scored against where
its own clip's speech is (`spoken_spans`, read off the audio's loudness), and the join is
kept for the coarse question it can answer, whether it falls between the two words
(`seam_in_gap`). `--rescore <keep>` scores a kept run again without saying anything.

That is a real measurement and it is not the card's. Words spoken one at a time have no
coarticulation: nothing runs into the next word, and the silences are cleaner than
connected speech ever is. So **this number is an upper bound** — the aligner will not do
better on a natural line than on this. If it fails here it fails everywhere, which makes
a bad number conclusive and a good one only encouraging. A hand-marked pass on natural
lines is still worth doing before change 3 goes on, and `--keep` writes the audio and the
alignment out so that pass has something to start from.

**Three roads to a truth, and `--on` picks one** (targum-internal#225, 2026-09-27).

- `--on tts` (the default, and the only one that spends): the above.
- `--on pockettorah`: real audio already on disk, scored against timings a person made.
  PocketTorah's app lights each word as the reader chants it, and to do that its
  repository carries one label file per aliyah — a comma-separated list of the second at
  which each word begins, marked by hand in an audio editor. The 515 recordings are
  already in `downloads_root()`, fetched for the leyning. So this costs nothing but CPU:
  the labels, the word lists they index into and the aliyah table are small files read
  once from the app's repository into `~/.targum/evals/align/pockettorah`. **Evaluation
  only**, the discipline `LICENSING.md` keeps for the treebanks: the repository states no
  licence for its labels, so they are never committed, never trained on and never ship;
  the numbers they produce go to the ledger and nothing else goes anywhere.
- `--on clips`: a folder of short recordings with a sentence each, in Common Voice's own
  layout (`<folder>/<split>.tsv` naming `path` and `sentence`, clips in `<folder>/clips`).
  Joined end to end, so the seams are known exactly — the same trick as `tts`, on real
  voices. Built ahead of the data: the day the CC0 Hebrew release is fetched, pointing
  `--clips` at it is the only new step.

**What is scored on PocketTorah, and why these.** The labels give onsets and nothing else,
so what is compared is where each word *begins*:

- `onset_ms_median` and `onset_ms_mean`: how far the aligner's start of each word is from
  the hand mark, in milliseconds. The median is the typical word; the mean is dragged by
  the few that went badly, which is the reason to keep both.
- `onset_ms_lag_median`: the same, signed — positive where the aligner starts a word
  after the hand does. An error that is mostly one constant lag is a different problem
  from scatter, with a different fix, and the unsigned numbers cannot tell them apart.
  (Measured 2026-09-27: it is mostly lag, 100–400 ms depending on the aliyah, and
  constant within each one. **Most of it is the labels'.** At words that follow a pause,
  where the voice's own onset can be read off the waveform, the hand marks sit 200–420 ms
  *before* the voice, and 14–36% of them fall where the next 50 ms is still silent; the
  aligner's starts sat 15–70 ms *after* it. The labels light a word ahead of the voice,
  as a follow-along app sensibly would, so a perfect aligner still scores a lag here.
  The aligner's own share was fixed by `to_the_voice` in `targum.audio.align`.)
- `onset_within_100ms` and `onset_within_250ms`: the share of words close enough. 100 ms
  is about the grain of the hand marks themselves — a label dropped by eye on a waveform
  is rarely better — so it is as tight as this gold can honestly be read. 250 ms is about
  a syllable of chant, and a word lit a syllable early is still the word being sung.
- `right_word_lit`: the share of the recording, sampled every 10 ms from the first
  hand-marked onset to the end of the file, during which the word the aligner would light
  is the word the hand marks light. This is the reader's number: it is what a person
  following along actually sees, it weighs a long held word by how long it is held, and it
  forgives an onset error that never changes which word is lit. Both sides light a word
  from its start until the next word starts, which is the app's own rule — so the aligner
  is not marked down for silences its spans leave between words.

**Chant, not speech.** Cantillation stretches vowels far past anything a speech model
was trained on, so this is a hard case for the aligner — and the one targum ships, since
every portion's audio is this collection. It says nothing direct about read speech; that
is what the clips are for.

**What is scored on clips.** `word_in_its_clip`: the share of words whose aligned middle
falls inside the clip they were said in. Clips carry silence at both ends, so a seam is
not a word's onset and cannot be scored in milliseconds; which clip a word landed in is
the thing that is known, and a word in the wrong clip is a word lit during the wrong
sentence.

    .venv/bin/python scripts/eval_align.py --on pockettorah --aliyot Bereshit-1,Noach-2
    .venv/bin/python scripts/eval_align.py --on clips --clips ~/cv-he --split test --most 50
"""

from __future__ import annotations

import argparse
import array
import bisect
import csv
import json
import statistics
import sys
import urllib.parse
import wave
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from targum import evals  # noqa: E402
from targum.audio.align import MODELS, CtcAligner  # noqa: E402
from targum.audio.align import RATE as ALIGN_RATE  # noqa: E402
from targum.audio.tools import samples  # noqa: E402
from targum.speech import (  # noqa: E402
    BYTES_PER_SECOND,
    NAME,
    PRICES,
    Clip,
    say,
    wav,
    write,
)

#: Short lines in each language the aligner has a model for. Ordinary sentences rather
#: than anything clever: what is being measured is where a word begins, and a hard word
#: measures the synthesiser instead.
LINES: dict[str, list[str]] = {
    "he": [
        "הילד הלך לבית הספר עם אחותו",
        "אמא שלי קנתה לחם וחלב בחנות",
        "מחר בבוקר נלך לים יחד",
        "הספר הזה מעניין מאוד ואני קורא אותו",
    ],
    "fr": [
        "le garçon est allé à l'école avec sa sœur",
        "ma mère a acheté du pain et du lait",
        "demain matin nous irons à la mer ensemble",
        "ce livre est très intéressant et je le lis",
    ],
    "ru": [
        "мальчик пошёл в школу вместе с сестрой",
        "моя мама купила хлеб и молоко в магазине",
        "завтра утром мы вместе пойдём на море",
        "эта книга очень интересная и я её читаю",
    ],
    "it": [
        "il ragazzo è andato a scuola con sua sorella",
        "mia madre ha comprato il pane e il latte",
        "domani mattina andremo al mare insieme",
        "questo libro è molto interessante e lo leggo",
    ],
}

#: A boundary this close to the truth is right for the purpose. A word lights when the
#: voice reaches it; fifty milliseconds early or late is not visible at reading speed,
#: and it is the tolerance the speech literature uses for the same question.
CLOSE_MS = 50.0


def words_of(language: str, most: int) -> list[str]:
    """The words to measure, in order, drawn from `LINES` until `most` are had."""
    drawn: list[str] = []
    for line in LINES.get(language, []):
        for word in line.split():
            if len(drawn) >= most:
                return drawn
            drawn.append(word)
    return drawn


def spoken_one_by_one(words: list[str], language: str, into: Path) -> tuple[Clip, list[float]]:
    """Say each word alone, join the clips, and answer with the clip and the true
    boundaries.

    The boundary between word *n* and word *n+1* is where the *n*-th clip ended, which
    is arithmetic rather than a judgement — that is the whole point of paying for one
    clip a word rather than one a line.

    The `Clip` comes back rather than the path handed in, because `write` chooses the
    suffix: it keeps mp3 where ffmpeg is present and WAV where it is not, so the file
    that exists is not always the name that was asked for.
    """
    pcm = b""
    boundaries: list[float] = []
    for word in words:
        pcm += say(word, language=language)[44:]
        boundaries.append(len(pcm) / BYTES_PER_SECOND)
    return write(wav(pcm), into), boundaries


#: A 10 ms frame, and how far under a clip's loudest frame still counts as speech: the
#: voice's own silence is digital zero or near it, so the line is not a fine one.
FRAME_S = 0.01
SPEECH_DB = -30.0


def spoken_spans(audio: Path, seams: list[float]) -> list[tuple[float, float]]:
    """Where speech is inside each clip: the first and last 10 ms frame within 30 dB of
    the clip's loudest.

    The clips are joined end to end, so a seam is where one *clip* ends — and every clip
    carries the voice's own silence before and after the word. Scored against the seam,
    an aligner that found every word exactly was 340–400 ms "wrong" on 2026-10-08, which
    was the padding measured, not the aligner. Each clip holds one word and nothing else,
    so its speech is read off the audio alone, and that is the truth a word is scored
    against.
    """
    pcm = samples(audio, ALIGN_RATE)
    frame = max(1, int(FRAME_S * ALIGN_RATE))
    spans: list[tuple[float, float]] = []
    start = 0.0
    for seam in seams:
        low, high = int(start * ALIGN_RATE), min(len(pcm), int(seam * ALIGN_RATE))
        levels = []
        for at in range(low, high, frame):
            chunk = pcm[at : at + frame]
            levels.append((sum(x * x for x in chunk) / max(1, len(chunk))) ** 0.5)
        loudest = max(levels, default=0.0)
        line = loudest * 10 ** (SPEECH_DB / 20)
        loud = [n for n, level in enumerate(levels) if loudest and level >= line]
        if loud:
            spans.append((start + loud[0] * FRAME_S, start + (loud[-1] + 1) * FRAME_S))
        else:
            spans.append((start, seam))
        start = seam
    return spans


def scored(
    found: list[tuple[float, float, float]],
    spans: list[tuple[float, float]],
    seams: list[float] | None = None,
) -> dict[str, float]:
    """How far each aligned word's start and end are from where its speech starts and
    ends, in milliseconds, and the share whose both edges are within 50 ms.

    `seam_in_gap`, where the seams are given, is the coarse question the first scoring
    should have asked: does the aligner put each join between the two words it divides?
    """
    starts = [
        abs(begin - was) * 1000.0 for (begin, _, _), (was, _) in zip(found, spans, strict=True)
    ]
    ends = [abs(end - was) * 1000.0 for (_, end, _), (_, was) in zip(found, spans, strict=True)]
    both = [max(a, b) for a, b in zip(starts, ends, strict=True)]
    marks = {
        "onset_ms_median": round(statistics.median(starts), 1),
        "onset_ms_mean": round(statistics.fmean(starts), 1),
        "end_ms_median": round(statistics.median(ends), 1),
        "end_ms_mean": round(statistics.fmean(ends), 1),
        "within_50ms": round(sum(1 for e in both if e <= CLOSE_MS) / len(both), 4),
    }
    if seams:
        pairs = list(zip(found, found[1:], strict=False))
        inside = sum(
            1
            for seam, ((_, end, _), (begin, _, _)) in zip(seams, pairs, strict=False)
            if end - 0.02 <= seam <= begin + 0.02
        )
        marks["seam_in_gap"] = round(inside / len(pairs), 4) if pairs else 0.0
    return marks


# -- real audio against hand marks: PocketTorah (targum-internal#225) ------------------

#: The app's repository, read for its labels, its text and its aliyah table. Pinned to
#: the branch rather than a commit because the labels have not changed in years and a
#: changed label is a better gold, not a broken one; the fetched copies stay put.
POCKETTORAH_RAW = "https://raw.githubusercontent.com/rneiss/PocketTorah/master/data"

#: One aliyah from each book of the Torah, and a second from Genesis, so the number is not
#: one labeller's habit on one passage. Chosen for having labels whose count matches the
#: words, and nothing else: Shemot-1 was the first pick and has one mark more than words.
ALIYOT = ("Bereshit-1", "Noach-2", "Shemot-2", "Vayikra-1", "Bamidbar-1", "Devarim-1")

#: The grain `right_word_lit` samples at: finer than the model's 20 ms frames would be
#: pretence, coarser would round short words away.
TICK_S = 0.01

ONSET_CLOSE_MS = (100.0, 250.0)


def labels_of(text: str) -> list[float]:
    """A PocketTorah label file: the second at which each word begins, comma separated."""
    return [float(piece) for piece in text.replace("\n", ",").split(",") if piece.strip()]


def aliyah_words(book: dict[str, Any], begin: str, end: str) -> list[str]:
    """The words of one aliyah, in the app's own division, which is what its labels index.

    The app's text is the Westminster Leningrad Codex as tanach.us publishes it: a word
    is a `w`, a maqaf ends one word rather than joining two, and a `/` marks a morpheme
    boundary inside a word. The `/` comes out; everything else the aligner strips itself.
    Where the text has a ketiv, `w` is the qere — what is read aloud, and what is labelled.
    """
    chapters = [one for one in book["Tanach"]["tanach"]["book"]["c"] if one]

    def place(ref: str) -> tuple[int, int]:
        chapter, verse = ref.strip().split(":")
        return int(chapter), int(verse)

    first, last = place(begin), place(end)
    out: list[str] = []
    for number, chapter in enumerate(chapters, start=1):
        verses = chapter["v"] if isinstance(chapter["v"], list) else [chapter["v"]]
        for verse_number, verse in enumerate(verses, start=1):
            if first <= (number, verse_number) <= last:
                out.extend(word.replace("/", "") for word in verse["w"])
    return out


def onsets_scored(
    found: Sequence[tuple[float, float, float]], onsets: list[float]
) -> dict[str, float]:
    """How far each aligned start is from the hand-marked one. See the module docstring.

    `strict=True`, as in `scored`: an aligner that answered short would otherwise be
    scored on the words it managed, which reads better the worse it did.
    """
    signed = [(start - mark) * 1000.0 for (start, _, _), mark in zip(found, onsets, strict=True)]
    errors = [abs(one) for one in signed]
    marks = {
        "onset_ms_median": round(statistics.median(errors), 1),
        "onset_ms_mean": round(statistics.fmean(errors), 1),
        "onset_ms_lag_median": round(statistics.median(signed), 1),
    }
    for close in ONSET_CLOSE_MS:
        share = sum(1 for e in errors if e <= close) / len(errors)
        marks[f"onset_within_{int(close)}ms"] = round(share, 4)
    return marks


def lit_share(
    found: Sequence[tuple[float, float, float]], onsets: list[float], until: float
) -> float:
    """The share of time from the first hand onset to `until` that the same word is lit.

    Lit means begun and not yet followed: the last word whose start is at or before the
    moment. Before its first word the aligner lights nothing, which is never right here,
    because sampling starts at the first word the hand marks.
    """
    if len(found) != len(onsets):
        raise ValueError(f"{len(found)} alignments for {len(onsets)} marked words")
    if not onsets or until <= onsets[0]:
        return 0.0
    # Starts can tie (a word the model has no letters for sits at its neighbour's end),
    # and bisect over a sorted copy answers "the last one begun" either way.
    starts = sorted(start for start, _, _ in found)
    order = sorted(range(len(found)), key=lambda index: found[index][0])
    ticks = int((until - onsets[0]) / TICK_S)
    right = 0
    for tick in range(ticks):
        moment = onsets[0] + tick * TICK_S
        truth = bisect.bisect_right(onsets, moment) - 1
        at = bisect.bisect_right(starts, moment) - 1
        if at >= 0 and order[at] == truth:
            right += 1
    return round(right / ticks, 4) if ticks else 0.0


def _fetch(url: str, into: Path) -> Path:
    """One small file, once. Kept where the next run finds it."""
    if into.is_file() and into.stat().st_size:
        return into
    import httpx

    into.parent.mkdir(parents=True, exist_ok=True)
    answer = httpx.get(url, timeout=60.0, follow_redirects=True)
    answer.raise_for_status()
    into.write_bytes(answer.content)
    return into


def _json(path: Path) -> Any:
    # The app's JSON files open with a byte-order mark, which `json` refuses.
    return json.loads(path.read_text(encoding="utf-8-sig"))


def pockettorah_case(name: str, gold: Path) -> tuple[list[str], list[float]]:
    """The words of one aliyah and the hand onsets for them, fetched if not yet here.

    `name` is the app's, `Bereshit-1` or `Achrei Mot-3`. Only the seven aliyot are asked
    for: the maftir and the haftarah are labelled against other passages.
    """
    portion, _, number = name.rpartition("-")
    if not number.isdigit() or not 1 <= int(number) <= 7:
        raise ValueError(f"{name!r} is not a portion and an aliyah from 1 to 7")
    table = _json(_fetch(f"{POCKETTORAH_RAW}/aliyah.json", gold / "aliyah.json"))
    entry = next(
        (one for one in table["parshiot"]["parsha"] if one["_id"] == portion),
        None,
    )
    if entry is None:
        raise ValueError(f"PocketTorah has no portion called {portion!r}")
    aliyah = next(one for one in entry["fullkriyah"]["aliyah"] if one["_num"] == number)
    book_name = entry["_verse"].split()[0]
    book = _json(
        _fetch(f"{POCKETTORAH_RAW}/torah/json/{book_name}.json", gold / f"{book_name}.json")
    )
    return aliyah_words(book, aliyah["_begin"], aliyah["_end"]), labels_of(
        _labels_file(name, gold).read_text()
    )


def pockettorah_files(names: Sequence[str], gold: Path) -> list[Path]:
    """The fetched files a run over `names` read: the aliyah table, each aliyah's book and
    its labels. What the ledger row's fingerprint is taken over, since the fetch reads the
    repository's branch rather than a commit (targum-internal#351)."""
    table = _json(gold / "aliyah.json")
    books: set[str] = set()
    for name in names:
        portion = name.rpartition("-")[0]
        for entry in table["parshiot"]["parsha"]:
            if entry["_id"] == portion:
                books.add(entry["_verse"].split()[0])
    return [
        gold / "aliyah.json",
        *(gold / f"{book}.json" for book in sorted(books)),
        *(gold / "labels" / f"{name}.txt" for name in names),
    ]


def _labels_file(name: str, gold: Path) -> Path:
    """The label file for an aliyah. The repository spells some with a capital and some
    without (`Noach-2.txt`, `vayikra-1.txt`), so both are asked for before giving up —
    and not every aliyah was labelled, which is a `LookupError` the run skips past."""
    import httpx

    into = gold / "labels" / f"{name}.txt"
    for spelled in dict.fromkeys((name, name[:1].lower() + name[1:])):
        quoted = urllib.parse.quote(f"{spelled}.txt")
        try:
            return _fetch(f"{POCKETTORAH_RAW}/torah/labels/{quoted}", into)
        except httpx.HTTPStatusError as missing:
            if missing.response.status_code != 404:
                raise
    raise LookupError(f"{name}: PocketTorah has no labels for it")


def _audio_for(name: str, folder: Path) -> Path | None:
    """The mp3 on disk for an app name. The two spell portions differently
    (`Achrei Mot` and `AchreiMot`), so both go through the leyning's own flattening."""
    from targum.parasha.leyning import _flat, stems

    portion, _, number = name.rpartition("-")
    found = stems(path.name for path in folder.glob("*.mp3")).get(_flat(portion), {})
    file = found.get(int(number))
    return folder / file if file else None


# -- real voices joined end to end: Common Voice's layout ------------------------------


def clip_rows(folder: Path, split: str, most: int) -> list[tuple[Path, str]]:
    """The first `most` clips of a split, in file order, as (audio, sentence).

    File order rather than a sample: Common Voice's own order is fixed per release, so
    the same release and the same `--most` is the same measurement.
    """
    table = folder / f"{split}.tsv"
    with table.open(encoding="utf-8", newline="") as rows:
        reader = csv.DictReader(rows, delimiter="\t", quoting=csv.QUOTE_NONE)
        out: list[tuple[Path, str]] = []
        for row in reader:
            if len(out) >= most:
                break
            sentence = (row.get("sentence") or "").strip()
            if sentence and row.get("path"):
                out.append((folder / "clips" / row["path"], sentence))
    return out


def joined_clips(clips: list[tuple[Path, str]], into: Path) -> list[tuple[float, float]]:
    """Every clip in one 16 kHz WAV, end to end. Answers each clip's (start, end)."""
    pcm = array.array("h")
    bounds: list[tuple[float, float]] = []
    for audio, _ in clips:
        start = len(pcm) / ALIGN_RATE
        pcm.extend(int(max(-1.0, min(1.0, x)) * 32767) for x in samples(audio, ALIGN_RATE))
        bounds.append((start, len(pcm) / ALIGN_RATE))
    with wave.open(str(into), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(ALIGN_RATE)
        out.writeframes(pcm.tobytes())
    return bounds


def in_its_clip(
    found: Sequence[tuple[float, float, float]],
    owners: list[int],
    bounds: list[tuple[float, float]],
) -> float:
    """The share of words whose aligned middle lies inside the clip they were said in."""
    right = 0
    for (start, end, _), owner in zip(found, owners, strict=True):
        middle = (start + end) / 2
        low, high = bounds[owner]
        if low <= middle < high:
            right += 1
    return round(right / len(owners), 4) if owners else 0.0


def _ready(language: str) -> CtcAligner:
    aligner = CtcAligner(language)
    usable, hint = aligner.available()
    if not usable:
        sys.exit(f"The forced aligner is not installed: {hint}")
    return aligner


def run_pockettorah(args: argparse.Namespace) -> list[evals.Row]:
    from targum.audio.tools import duration
    from targum.parasha.leyning import downloads_root

    folder = args.audio or downloads_root()
    gold = Path.home() / ".targum" / "evals" / "align" / "pockettorah"
    names = [one.strip() for one in args.aliyot.split(",") if one.strip()]
    aligner = _ready("he")
    all_found: list[tuple[float, float, float]] = []
    all_onsets: list[float] = []
    lit_ticks = 0.0
    lit_weighted = 0.0
    measured: list[str] = []
    for name in names:
        audio = _audio_for(name, folder)
        if audio is None:
            print(f"{name}: no recording in {folder} — skipped")
            continue
        try:
            words, onsets = pockettorah_case(name, gold)
        except LookupError as missing:
            print(f"{missing} — skipped")
            continue
        if len(words) != len(onsets):
            # Off by one from the first gap onward, every word after it would be scored
            # against its neighbour's mark and nothing in the numbers would show it.
            print(f"{name}: {len(words)} words and {len(onsets)} marks — skipped")
            continue
        print(f"{name}: aligning {len(words)} words…", flush=True)
        found = aligner.align(audio, words, "he")
        length = duration(audio)
        marks = onsets_scored(found, onsets)
        lit = lit_share(found, onsets, length)
        print(f"{name}: {marks} right_word_lit={lit}")
        (gold / "runs").mkdir(parents=True, exist_ok=True)
        (gold / "runs" / f"{name}.json").write_text(
            json.dumps(
                {"words": words, "onsets": onsets, "found": found, "scored": marks, "lit": lit},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        all_found.extend(found)
        all_onsets.extend(onsets)
        span = length - onsets[0]
        lit_ticks += span
        lit_weighted += lit * span
        measured.append(name)
    if not measured:
        sys.exit("Nothing was measured.")
    # Pooled over words, not averaged over aliyot, so a long aliyah counts for its length.
    marks = onsets_scored(all_found, all_onsets)
    marks["right_word_lit"] = round(lit_weighted / lit_ticks, 4)
    print(f"\nall: {marks}")
    note = evals.pinned(
        args.note or f"hand word onsets, chanted Torah: {', '.join(measured)}",
        pockettorah_files(measured, gold),
    )
    return [
        evals.Row(
            at=date.today().isoformat(),
            stage="align",
            corpus="pockettorah",
            metric=metric,
            score=score,
            n=len(all_onsets),
            system=aligner.name,
            version=aligner.model,
            note=note,
        )
        for metric, score in marks.items()
    ]


def run_clips(args: argparse.Namespace) -> list[evals.Row]:
    if not args.clips:
        sys.exit("--on clips needs --clips, the folder the release was unpacked into.")
    clips = clip_rows(args.clips, args.split, args.most)
    if not clips:
        sys.exit(f"No clips with a sentence in {args.clips / (args.split + '.tsv')}.")
    keep = args.keep or Path.home() / ".targum" / "evals" / "align"
    keep.mkdir(parents=True, exist_ok=True)
    joined = keep / f"clips-{args.language}-{args.split}-{len(clips)}.wav"
    bounds = joined_clips(clips, joined)
    words: list[str] = []
    owners: list[int] = []
    for index, (_, sentence) in enumerate(clips):
        pieces = sentence.split()
        words.extend(pieces)
        owners.extend([index] * len(pieces))
    aligner = _ready(args.language)
    print(f"aligning {len(words)} words over {bounds[-1][1]:.1f}s of {len(clips)} clips…")
    found = aligner.align(joined, words, args.language)
    score = in_its_clip(found, owners, bounds)
    print(f"word_in_its_clip: {score}")
    return [
        evals.Row(
            at=date.today().isoformat(),
            stage="align",
            corpus=args.corpus or f"clips-{args.language}-{args.split}",
            metric="word_in_its_clip",
            score=score,
            n=len(words),
            system=aligner.name,
            version=aligner.model,
            note=evals.pinned(
                args.note or f"first {len(clips)} clips of {args.split}.tsv, joined",
                [args.clips / f"{args.split}.tsv"],
            ),
        )
    ]


def run_tts(args: argparse.Namespace) -> list[evals.Row]:
    languages = [code.strip() for code in args.languages.split(",") if code.strip()]
    unknown = [code for code in languages if code not in MODELS]
    if unknown:
        sys.exit(
            f"The aligner has no model for {', '.join(unknown)}. It reads: {', '.join(MODELS)}"
        )

    drawn = {code: words_of(code, args.words) for code in languages}
    short = [code for code, words in drawn.items() if not words]
    if short:
        sys.exit(f"No lines written down for {', '.join(short)} — add them to LINES.")

    if args.dry_run:
        # A word is about half a second said alone, which is the number to price with:
        # measured against the shelf's own clips rather than guessed at.
        total = sum(len(words) for words in drawn.values()) * 0.5 / 60.0
        print(f"{'language':10} {'words':>6}")
        for code, words in drawn.items():
            print(f"{code:10} {len(words):>6}")
        print(
            f"\nabout {total:.1f} minutes of speech at ${PRICES[NAME]:.2f}/min "
            f"= about ${total * PRICES[NAME]:.2f}"
        )
        print("Nothing was called. Drop --dry-run to run it.")
        return []

    keep = args.keep or Path.home() / ".targum" / "evals" / "align"
    keep.mkdir(parents=True, exist_ok=True)
    rows: list[evals.Row] = []
    for code in languages:
        words = drawn[code]
        clip = keep / f"{code}-{len(words)}.wav"
        print(f"{code}: saying {len(words)} words one at a time…", flush=True)
        made, truth = spoken_one_by_one(words, code, clip)
        aligner = CtcAligner(code)
        usable, hint = aligner.available()
        if not usable:
            sys.exit(f"The forced aligner is not installed: {hint}")
        print(f"{code}: aligning {made.seconds:.1f}s of {made.path.suffix} …", flush=True)
        found = aligner.align(made.path, words, code)
        marks = scored(found, spoken_spans(made.path, truth), truth)
        (keep / f"{code}-{len(words)}.json").write_text(
            json.dumps(
                {"words": words, "truth": truth, "found": found, "scored": marks},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"{code}: {marks}")
        for metric, score in marks.items():
            rows.append(
                evals.Row(
                    at=date.today().isoformat(),
                    stage="align",
                    corpus=f"tts-{code}",
                    metric=metric,
                    score=score,
                    n=len(words),
                    system="ctc-forced-aligner",
                    version=MODELS[code][1],
                    note=(args.note or "one clip a word, joined; boundaries exact by construction"),
                )
            )
    print(f"\nThe audio and the alignment are in {keep}.")
    return rows


def run_rescore(args: argparse.Namespace) -> list[evals.Row]:
    """Score a kept `--on tts` run again, from its audio and its alignment: no voice is
    asked and nothing is spent. For a scoring that changed after the money was spent."""
    keep: Path = args.rescore
    rows: list[evals.Row] = []
    for kept in sorted(keep.glob("*-*.json")):
        code = kept.stem.split("-")[0]
        audio = next(
            (
                kept.with_suffix(suffix)
                for suffix in (".mp3", ".wav")
                if kept.with_suffix(suffix).is_file()
            ),
            None,
        )
        if audio is None or code not in MODELS:
            continue
        held = json.loads(kept.read_text(encoding="utf-8"))
        found = [tuple(one) for one in held["found"]]
        marks = scored(found, spoken_spans(audio, held["truth"]), held["truth"])  # type: ignore[arg-type]
        print(f"{code}: {marks}")
        for metric, score in marks.items():
            rows.append(
                evals.Row(
                    at=date.today().isoformat(),
                    stage="align",
                    corpus=f"tts-{code}",
                    metric=metric,
                    score=score,
                    n=len(held["words"]),
                    system="ctc-forced-aligner",
                    version=MODELS[code][1],
                    note=args.note or "one clip a word, joined; scored against each clip's speech",
                )
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--on",
        choices=("tts", "pockettorah", "clips"),
        default="tts",
        help="Where the truth comes from. Only tts spends.",
    )
    parser.add_argument("--languages", default="he,fr,ru,it", help="tts: comma separated.")
    parser.add_argument("--words", type=int, default=40, help="tts: how many words a language.")
    parser.add_argument(
        "--dry-run", action="store_true", help="tts: say what it would cost and call nothing."
    )
    parser.add_argument("--keep", type=Path, help="Where to leave the audio and the alignment.")
    parser.add_argument(
        "--aliyot", default=",".join(ALIYOT), help="pockettorah: the app's names, comma separated."
    )
    parser.add_argument("--audio", type=Path, help="pockettorah: the folder of the mp3s.")
    parser.add_argument("--clips", type=Path, help="clips: the folder the release unpacked to.")
    parser.add_argument("--split", default="test", help="clips: which .tsv to read.")
    parser.add_argument("--most", type=int, default=50, help="clips: how many clips.")
    parser.add_argument("--language", default="he", help="clips: the language they are in.")
    parser.add_argument("--corpus", default="", help="clips: the ledger's name for them.")
    parser.add_argument("--ledger", type=Path, help="Which ledger file.")
    parser.add_argument("--note", default="", help="What was different about this run.")
    parser.add_argument(
        "--rescore", type=Path, help="tts: score a kept run again from its files; spends nothing."
    )
    args = parser.parse_args()

    runs = {"tts": run_tts, "pockettorah": run_pockettorah, "clips": run_clips}
    rows = run_rescore(args) if args.rescore else runs[args.on](args)
    written = evals.append(rows, args.ledger or evals.DEFAULT)
    if rows:
        print(f"\nRecorded {written} rows.")


if __name__ == "__main__":
    main()
